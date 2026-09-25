"""
LangGraph agent tools. Each tool is wrapped with Redis caching and tenacity retry.
All external API calls go through these tools — the LLM invokes them via function calling.
"""
import asyncio
import hashlib
import json
import logging
from typing import Annotated, Any

import httpx
from amadeus import Client as AmadeusClient, ResponseError
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.cache import cache_get, cache_set
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cache_key(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, default=str)
    return "tp:" + hashlib.sha256(raw.encode()).hexdigest()[:32]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
)
async def _http_get(url: str, params: dict | None = None, headers: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


def _amadeus_client() -> AmadeusClient:
    return AmadeusClient(
        client_id=settings.amadeus_client_id,
        client_secret=settings.amadeus_client_secret,
        hostname=settings.amadeus_hostname,
    )


# ---------------------------------------------------------------------------
# Google Maps tools
# ---------------------------------------------------------------------------

@tool
async def get_directions(
    origin: Annotated[str, "Origin city or address"],
    destination: Annotated[str, "Destination city or address"],
    mode: Annotated[str, "Travel mode: driving, transit, walking, bicycling"] = "driving",
) -> dict:
    """Get route directions including steps, distance, and duration from Google Maps."""
    key = _cache_key("directions", origin, destination, mode)
    cached = await cache_get(key)
    if cached:
        return cached

    params = {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "key": settings.google_maps_api_key,
    }
    data = await _http_get("https://maps.googleapis.com/maps/api/directions/json", params=params)
    result = {
        "status": data.get("status"),
        "routes": [
            {
                "summary": r.get("summary"),
                "distance": r["legs"][0]["distance"] if r.get("legs") else None,
                "duration": r["legs"][0]["duration"] if r.get("legs") else None,
                "steps": [
                    {"instruction": s.get("html_instructions", ""), "distance": s.get("distance"), "duration": s.get("duration")}
                    for s in r["legs"][0].get("steps", [])[:10]
                ] if r.get("legs") else [],
            }
            for r in data.get("routes", [])[:2]
        ],
    }
    await cache_set(key, result, settings.redis_ttl_api)
    return result


@tool
async def compare_travel_modes(
    origin: Annotated[str, "Origin city"],
    destination: Annotated[str, "Destination city"],
) -> dict:
    """Use Distance Matrix API to compare driving vs transit travel time and distance."""
    key = _cache_key("distance_matrix", origin, destination)
    cached = await cache_get(key)
    if cached:
        return cached

    modes = ["driving", "transit"]
    results = {}
    for mode in modes:
        params = {
            "origins": origin,
            "destinations": destination,
            "mode": mode,
            "key": settings.google_maps_api_key,
        }
        try:
            data = await _http_get("https://maps.googleapis.com/maps/api/distancematrix/json", params=params)
            row = data.get("rows", [{}])[0]
            element = row.get("elements", [{}])[0]
            results[mode] = {
                "status": element.get("status"),
                "distance": element.get("distance"),
                "duration": element.get("duration"),
            }
        except Exception as exc:
            results[mode] = {"error": str(exc)}

    await cache_set(key, results, settings.redis_ttl_api)
    return results


@tool
async def get_places_along_route(
    location: Annotated[str, "Lat,lng string e.g. '19.0760,72.8777' or city name"],
    place_type: Annotated[str, "Google place type: restaurant, gas_station, lodging, tourist_attraction"] = "restaurant",
    radius_m: Annotated[int, "Search radius in meters"] = 5000,
) -> list[dict]:
    """Search Points of Interest, rest stops, fuel stops, or restaurants near a location."""
    key = _cache_key("places", location, place_type, radius_m)
    cached = await cache_get(key)
    if cached:
        return cached

    params = {
        "location": location,
        "radius": radius_m,
        "type": place_type,
        "key": settings.google_maps_api_key,
    }
    data = await _http_get("https://maps.googleapis.com/maps/api/place/nearbysearch/json", params=params)
    places = [
        {
            "name": p.get("name"),
            "rating": p.get("rating"),
            "vicinity": p.get("vicinity"),
            "types": p.get("types", [])[:3],
            "open_now": p.get("opening_hours", {}).get("open_now"),
        }
        for p in data.get("results", [])[:8]
    ]
    await cache_set(key, places, settings.redis_ttl_api)
    return places


# ---------------------------------------------------------------------------
# Amadeus flight tools
# ---------------------------------------------------------------------------

@tool
async def search_flights(
    origin_iata: Annotated[str, "IATA code of origin airport, e.g. BOM"],
    destination_iata: Annotated[str, "IATA code of destination airport, e.g. DEL"],
    departure_date: Annotated[str, "Date in YYYY-MM-DD format"],
    adults: Annotated[int, "Number of adult passengers"] = 1,
    max_results: Annotated[int, "Maximum flight offers to return"] = 5,
) -> list[dict]:
    """Search live flight offers via Amadeus Flight Offers Search API."""
    key = _cache_key("flights", origin_iata, destination_iata, departure_date, adults)
    cached = await cache_get(key)
    if cached:
        return cached

    try:
        amadeus = _amadeus_client()
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin_iata,
            destinationLocationCode=destination_iata,
            departureDate=departure_date,
            adults=adults,
            max=max_results,
        )
        offers = []
        for offer in response.data[:max_results]:
            itinerary = offer.get("itineraries", [{}])[0]
            segments = itinerary.get("segments", [])
            price = offer.get("price", {})
            offers.append({
                "id": offer.get("id"),
                "price_total": price.get("grandTotal"),
                "currency": price.get("currency"),
                "duration": itinerary.get("duration"),
                "stops": len(segments) - 1,
                "segments": [
                    {
                        "from": s["departure"]["iataCode"],
                        "to": s["arrival"]["iataCode"],
                        "departure": s["departure"]["at"],
                        "arrival": s["arrival"]["at"],
                        "carrier": s["carrierCode"],
                        "flight_number": s["number"],
                    }
                    for s in segments
                ],
                "source": "amadeus",
                "bookable": True,
            })
        await cache_set(key, offers, settings.redis_ttl_api)
        return offers
    except ResponseError as exc:
        logger.error("Amadeus flight search error: %s", exc)
        return [{"error": str(exc)}]


@tool
async def get_flight_price_analysis(
    origin_iata: Annotated[str, "IATA code of origin airport"],
    destination_iata: Annotated[str, "IATA code of destination airport"],
    departure_date: Annotated[str, "Date in YYYY-MM-DD format"],
) -> dict:
    """Get Amadeus Flight Price Analysis — price trend signal (cheap/average/high)."""
    key = _cache_key("flight_price_analysis", origin_iata, destination_iata, departure_date)
    cached = await cache_get(key)
    if cached:
        return cached

    try:
        amadeus = _amadeus_client()
        response = amadeus.analytics.itinerary_price_metrics.get(
            originIataCode=origin_iata,
            destinationIataCode=destination_iata,
            departureDate=departure_date,
        )
        data = response.data[0] if response.data else {}
        result = {
            "price_metrics": data.get("priceMetrics", []),
            "currency": data.get("currencyCode"),
            "source": "amadeus",
        }
        await cache_set(key, result, settings.redis_ttl_api)
        return result
    except ResponseError as exc:
        logger.error("Amadeus price analysis error: %s", exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Amadeus hotel tool
# ---------------------------------------------------------------------------

@tool
async def search_hotels(
    city_code: Annotated[str, "IATA city code, e.g. DEL for Delhi"],
    check_in: Annotated[str, "Check-in date YYYY-MM-DD"],
    check_out: Annotated[str, "Check-out date YYYY-MM-DD"],
    adults: Annotated[int, "Number of adults"] = 1,
) -> list[dict]:
    """Search hotel offers via Amadeus Hotel Search API. Returns real bookable data."""
    key = _cache_key("hotels", city_code, check_in, check_out, adults)
    cached = await cache_get(key)
    if cached:
        return cached

    try:
        amadeus = _amadeus_client()
        # Step 1: get hotel IDs for city
        hotel_list = amadeus.reference_data.locations.hotels.by_city.get(cityCode=city_code)
        hotel_ids = [h["hotelId"] for h in hotel_list.data[:20]]

        # Step 2: get offers for those hotels
        offers_resp = amadeus.shopping.hotel_offers_search.get(
            hotelIds=",".join(hotel_ids[:10]),
            checkInDate=check_in,
            checkOutDate=check_out,
            adults=adults,
        )
        hotels = []
        for item in offers_resp.data[:6]:
            hotel = item.get("hotel", {})
            offer = item.get("offers", [{}])[0]
            price = offer.get("price", {})
            hotels.append({
                "hotel_name": hotel.get("name"),
                "city": hotel.get("cityCode"),
                "stars": hotel.get("rating"),
                "price_per_night": price.get("total"),
                "currency": price.get("currency"),
                "check_in": check_in,
                "check_out": check_out,
                "source": "amadeus",
                "bookable": True,
            })
        await cache_set(key, hotels, settings.redis_ttl_api)
        return hotels
    except ResponseError as exc:
        logger.error("Amadeus hotel search error: %s", exc)
        return [{"error": str(exc)}]


# ---------------------------------------------------------------------------
# Apify scrape tool (MMT/Goibibo + OYO budget listings)
# ---------------------------------------------------------------------------

@tool
async def scrape_budget_listings(
    destination: Annotated[str, "Destination city name"],
    check_in: Annotated[str, "Check-in date YYYY-MM-DD"],
) -> list[dict]:
    """
    Fetch budget hotel/accommodation listings from MakeMyTrip/Goibibo and OYO via Apify.
    Returns display-only data with outbound links. No booking is performed on their behalf.
    Prices shown as 'starting from X — check current price' with source link.
    """
    key = _cache_key("apify_budget", destination, check_in)
    cached = await cache_get(key)
    if cached:
        return cached

    # Apify actor: apify/booking-scraper or custom actor for MMT/OYO
    # We use a lightweight approach: actor run with small result set
    apify_url = "https://api.apify.com/v2/acts/maxcopell~booking-scraper/runs"
    headers = {"Authorization": f"Bearer {settings.apify_api_token}"}
    payload = {
        "startUrls": [{"url": f"https://www.makemytrip.com/hotels/hotel-listing/?checkin={check_in}&checkout={check_in}&city={destination}"}],
        "maxResults": 8,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Start run
            run_resp = await client.post(apify_url, json=payload, headers=headers)
            run_resp.raise_for_status()
            run_id = run_resp.json()["data"]["id"]

            # Poll for completion (max 25s)
            for _ in range(5):
                await asyncio.sleep(5)
                status_resp = await client.get(
                    f"https://api.apify.com/v2/actor-runs/{run_id}",
                    headers=headers,
                )
                status = status_resp.json()["data"]["status"]
                if status in ("SUCCEEDED", "FAILED", "ABORTED"):
                    break

            # Fetch dataset
            dataset_resp = await client.get(
                f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items",
                headers=headers,
            )
            items = dataset_resp.json()

        listings = []
        for item in items[:8]:
            listings.append({
                "name": item.get("name", "Unknown Property"),
                "price_starting_from": item.get("price"),
                "currency": "INR",
                "rating": item.get("rating"),
                "source": "MakeMyTrip (via Apify)",
                "source_url": item.get("url", "https://www.makemytrip.com"),
                "disclaimer": "Starting price only. Check current rate and availability at source before booking.",
                "bookable": False,
            })
        await cache_set(key, listings, settings.redis_ttl_scrape)
        return listings

    except Exception as exc:
        logger.warning("Apify scrape failed: %s", exc)
        # Graceful fallback — return empty, don't break the whole plan
        return []


# ---------------------------------------------------------------------------
# Weather tool
# ---------------------------------------------------------------------------

@tool
async def get_weather_forecast(
    city: Annotated[str, "City name"],
    travel_date: Annotated[str, "Date in YYYY-MM-DD format"],
) -> dict:
    """Get weather forecast for the travel date using OpenWeatherMap."""
    key = _cache_key("weather", city, travel_date)
    cached = await cache_get(key)
    if cached:
        return cached

    params = {
        "q": city,
        "appid": settings.openweather_api_key,
        "units": "metric",
        "cnt": 8,
    }
    try:
        data = await _http_get("https://api.openweathermap.org/data/2.5/forecast", params=params)
        # Find forecast closest to travel date
        forecasts = data.get("list", [])
        target_prefix = travel_date  # YYYY-MM-DD
        matched = [f for f in forecasts if f.get("dt_txt", "").startswith(target_prefix)]
        if not matched and forecasts:
            matched = [forecasts[0]]

        result = {
            "city": data.get("city", {}).get("name", city),
            "forecasts": [
                {
                    "time": f.get("dt_txt"),
                    "temp_c": f["main"]["temp"],
                    "feels_like": f["main"]["feels_like"],
                    "description": f["weather"][0]["description"] if f.get("weather") else "",
                    "humidity": f["main"]["humidity"],
                    "wind_kph": round(f["wind"]["speed"] * 3.6, 1),
                }
                for f in matched[:4]
            ],
        }
        await cache_set(key, result, settings.redis_ttl_api)
        return result
    except Exception as exc:
        logger.warning("Weather API error: %s", exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Currency conversion tool
# ---------------------------------------------------------------------------

@tool
async def convert_currency(
    amount: Annotated[float, "Amount to convert"],
    from_currency: Annotated[str, "Source currency code, e.g. USD"],
    to_currency: Annotated[str, "Target currency code, e.g. INR"],
) -> dict:
    """Convert currency using exchangerate-api.com. Used for cross-border trip budgeting."""
    key = _cache_key("fx", from_currency, to_currency)
    cached = await cache_get(key)
    rates = cached

    if not rates:
        url = f"https://v6.exchangerate-api.com/v6/{settings.exchangerate_api_key}/latest/{from_currency}"
        try:
            data = await _http_get(url)
            rates = data.get("conversion_rates", {})
            await cache_set(key, rates, settings.redis_ttl_api)
        except Exception as exc:
            return {"error": str(exc)}

    rate = rates.get(to_currency)
    if not rate:
        return {"error": f"Rate for {to_currency} not found"}

    return {
        "from_currency": from_currency,
        "to_currency": to_currency,
        "amount": amount,
        "converted": round(amount * rate, 2),
        "rate": rate,
    }


# ---------------------------------------------------------------------------
# Airport IATA lookup helper
# ---------------------------------------------------------------------------

@tool
async def get_airport_iata(
    city_name: Annotated[str, "City name to look up IATA airport code for"],
) -> dict:
    """Resolve a city name to its IATA airport code via Amadeus reference data."""
    key = _cache_key("iata", city_name)
    cached = await cache_get(key)
    if cached:
        return cached

    try:
        amadeus = _amadeus_client()
        response = amadeus.reference_data.locations.get(
            keyword=city_name,
            subType="AIRPORT,CITY",
        )
        locations = [
            {"iata": loc["iataCode"], "name": loc["name"], "type": loc["subType"]}
            for loc in response.data[:3]
        ]
        result = {"locations": locations, "top_iata": locations[0]["iata"] if locations else None}
        await cache_set(key, result, settings.redis_ttl_api)
        return result
    except ResponseError as exc:
        return {"error": str(exc)}


ALL_TOOLS = [
    get_directions,
    compare_travel_modes,
    get_places_along_route,
    search_flights,
    get_flight_price_analysis,
    search_hotels,
    scrape_budget_listings,
    get_weather_forecast,
    convert_currency,
    get_airport_iata,
]
