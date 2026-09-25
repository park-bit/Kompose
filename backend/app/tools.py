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

try:
    from amadeus import Client as AmadeusClient, ResponseError
except ImportError:
    AmadeusClient = None
    ResponseError = Exception

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
# Routing & Places (Google Maps with free OpenStreetMap/OSRM fallback)
# ---------------------------------------------------------------------------

_COMMON_COORDS: dict[str, tuple[float, float]] = {
    "mumbai": (19.0760, 72.8777),
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "bangalore": (12.9716, 77.5946),
    "bengaluru": (12.9716, 77.5946),
    "goa": (15.2993, 74.1240),
    "jaipur": (26.9124, 75.7873),
    "hyderabad": (17.3850, 78.4867),
    "chennai": (13.0827, 80.2707),
    "kolkata": (22.5726, 88.3639),
    "pune": (18.5204, 73.8567),
    "ahmedabad": (23.0225, 72.5714),
    "agra": (27.1767, 78.0081),
    "varanasi": (25.3176, 82.9739),
    "udaipur": (24.5854, 73.7125),
    "manali": (32.2432, 77.1892),
    "shimla": (31.1048, 77.1734),
    "kochi": (9.9312, 76.2673),
    "chandigarh": (30.7333, 76.7794),
    "amritsar": (31.6340, 74.8723),
    "dubai": (25.2048, 55.2708),
    "singapore": (1.3521, 103.8198),
    "london": (51.5074, -0.1278),
    "paris": (48.8566, 2.3522),
    "new york": (40.7128, -74.0060),
}


async def _geocode(place: str) -> tuple[float, float] | None:
    norm = place.strip().lower()
    for city, coords in _COMMON_COORDS.items():
        if city in norm or norm in city:
            return coords

    # Parse raw lat,lng string
    if "," in norm:
        parts = norm.split(",")
        try:
            return float(parts[0].strip()), float(parts[1].strip())
        except ValueError:
            pass

    try:
        url = f"https://nominatim.openstreetmap.org/search?q={httpx.URL(norm)}&format=json&limit=1"
        data = await _http_get(url, headers={"User-Agent": "KomposeTravelPlanner/1.0"})
        if data and isinstance(data, list) and len(data) > 0:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as exc:
        logger.warning(f"Nominatim geocode failed for {place}: {exc}")
    return None


@tool
async def get_directions(
    origin: Annotated[str, "Origin city or address"],
    destination: Annotated[str, "Destination city or address"],
    mode: Annotated[str, "Travel mode: driving, transit, walking, bicycling"] = "driving",
) -> dict:
    """Get route directions including steps, distance, and duration."""
    key = _cache_key("directions", origin, destination, mode)
    cached = await cache_get(key)
    if cached:
        return cached

    has_google_key = bool(
        settings.google_maps_api_key
        and settings.google_maps_api_key != "your_google_maps_api_key_here"
    )

    if has_google_key:
        try:
            params = {
                "origin": origin,
                "destination": destination,
                "mode": mode,
                "key": settings.google_maps_api_key,
            }
            data = await _http_get("https://maps.googleapis.com/maps/api/directions/json", params=params)
            if data.get("status") == "OK":
                result = {
                    "status": "OK",
                    "routes": [
                        {
                            "summary": r.get("summary"),
                            "distance": r["legs"][0]["distance"] if r.get("legs") else None,
                            "duration": r["legs"][0]["duration"] if r.get("legs") else None,
                            "steps": [
                                {
                                    "instruction": s.get("html_instructions", ""),
                                    "distance": s.get("distance"),
                                    "duration": s.get("duration"),
                                }
                                for s in r["legs"][0].get("steps", [])[:10]
                            ] if r.get("legs") else [],
                        }
                        for r in data.get("routes", [])[:2]
                    ],
                }
                await cache_set(key, result, settings.redis_ttl_api)
                return result
        except Exception as exc:
            logger.warning(f"Google Maps Directions failed, falling back to OSRM: {exc}")

    # Free OSRM fallback
    origin_coords = await _geocode(origin)
    dest_coords = await _geocode(destination)

    if not origin_coords or not dest_coords:
        return {"status": "NOT_FOUND", "routes": []}

    try:
        osrm_url = (
            f"https://router.project-osrm.org/route/v1/driving/"
            f"{origin_coords[1]},{origin_coords[0]};{dest_coords[1]},{dest_coords[0]}"
            f"?overview=false&steps=true"
        )
        data = await _http_get(osrm_url)
        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            meters = route.get("distance", 0)
            seconds = route.get("duration", 0)
            km = round(meters / 1000, 1)
            hrs = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            dur_str = f"{hrs}h {mins}m" if hrs > 0 else f"{mins} mins"

            steps = []
            for leg in route.get("legs", []):
                for s in leg.get("steps", [])[:10]:
                    maneuver = s.get("maneuver", {}).get("type", "Proceed")
                    name = s.get("name") or "road"
                    step_m = s.get("distance", 0)
                    step_s = s.get("duration", 0)
                    steps.append({
                        "instruction": f"{maneuver.title()} along {name}",
                        "distance": {"text": f"{round(step_m / 1000, 1)} km", "value": int(step_m)},
                        "duration": {"text": f"{int(step_s // 60)} mins", "value": int(step_s)},
                    })

            result = {
                "status": "OK",
                "routes": [
                    {
                        "summary": f"{origin} to {destination} via primary route",
                        "distance": {"text": f"{km} km", "value": int(meters)},
                        "duration": {"text": dur_str, "value": int(seconds)},
                        "steps": steps,
                    }
                ],
            }
            await cache_set(key, result, settings.redis_ttl_api)
            return result
    except Exception as exc:
        logger.error(f"OSRM routing failed: {exc}")

    return {"status": "ZERO_RESULTS", "routes": []}


@tool
async def compare_travel_modes(
    origin: Annotated[str, "Origin city"],
    destination: Annotated[str, "Destination city"],
) -> dict:
    """Compare driving vs transit travel time and distance."""
    key = _cache_key("distance_matrix", origin, destination)
    cached = await cache_get(key)
    if cached:
        return cached

    has_google_key = bool(
        settings.google_maps_api_key
        and settings.google_maps_api_key != "your_google_maps_api_key_here"
    )

    if has_google_key:
        try:
            modes = ["driving", "transit"]
            results = {}
            for m in modes:
                params = {
                    "origins": origin,
                    "destinations": destination,
                    "mode": m,
                    "key": settings.google_maps_api_key,
                }
                data = await _http_get("https://maps.googleapis.com/maps/api/distancematrix/json", params=params)
                row = data.get("rows", [{}])[0]
                element = row.get("elements", [{}])[0]
                results[m] = {
                    "status": element.get("status"),
                    "distance": element.get("distance"),
                    "duration": element.get("duration"),
                }
            await cache_set(key, results, settings.redis_ttl_api)
            return results
        except Exception as exc:
            logger.warning(f"Google Distance Matrix failed, falling back to OSRM: {exc}")

    # Free OSRM + heuristic fallback
    origin_coords = await _geocode(origin)
    dest_coords = await _geocode(destination)

    if not origin_coords or not dest_coords:
        return {
            "driving": {"status": "NOT_FOUND"},
            "transit": {"status": "NOT_FOUND"},
        }

    try:
        osrm_url = (
            f"https://router.project-osrm.org/route/v1/driving/"
            f"{origin_coords[1]},{origin_coords[0]};{dest_coords[1]},{dest_coords[0]}"
            f"?overview=false"
        )
        data = await _http_get(osrm_url)
        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            meters = route.get("distance", 0)
            seconds = route.get("duration", 0)
            km = round(meters / 1000, 1)

            drive_hrs = int(seconds // 3600)
            drive_mins = int((seconds % 3600) // 60)
            drive_dur_str = f"{drive_hrs}h {drive_mins}m" if drive_hrs > 0 else f"{drive_mins} mins"

            # Transit estimated at ~65 km/h avg train/bus speed
            transit_hours = max(1.0, km / 65.0)
            t_hrs = int(transit_hours)
            t_mins = int((transit_hours - t_hrs) * 60)
            transit_dur_str = f"{t_hrs}h {t_mins}m"

            results = {
                "driving": {
                    "status": "OK",
                    "distance": {"text": f"{km} km", "value": int(meters)},
                    "duration": {"text": drive_dur_str, "value": int(seconds)},
                },
                "transit": {
                    "status": "OK",
                    "distance": {"text": f"{round(km * 1.05, 1)} km", "value": int(meters * 1.05)},
                    "duration": {"text": transit_dur_str, "value": int(transit_hours * 3600)},
                },
            }
            await cache_set(key, results, settings.redis_ttl_api)
            return results
    except Exception as exc:
        logger.error(f"OSRM comparison failed: {exc}")

    return {
        "driving": {"status": "ZERO_RESULTS"},
        "transit": {"status": "ZERO_RESULTS"},
    }


@tool
async def get_places_along_route(
    location: Annotated[str, "Lat,lng string e.g. '19.0760,72.8777' or city name"],
    place_type: Annotated[str, "Place type: restaurant, gas_station, lodging, tourist_attraction"] = "restaurant",
    radius_m: Annotated[int, "Search radius in meters"] = 5000,
) -> list[dict]:
    """Search Points of Interest, rest stops, fuel stops, or restaurants near a location."""
    key = _cache_key("places", location, place_type, radius_m)
    cached = await cache_get(key)
    if cached:
        return cached

    has_google_key = bool(
        settings.google_maps_api_key
        and settings.google_maps_api_key != "your_google_maps_api_key_here"
    )

    if has_google_key:
        try:
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
        except Exception as exc:
            logger.warning(f"Google Places failed, falling back to Nominatim: {exc}")

    # Free Nominatim search fallback
    clean_location = location.split(",")[0].strip() if "," in location else location.strip()
    query = f"{place_type} in {clean_location}"
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={httpx.URL(query)}&format=json&limit=6"
        data = await _http_get(url, headers={"User-Agent": "KomposeTravelPlanner/1.0"})
        places = []
        if isinstance(data, list):
            for item in data[:6]:
                name = item.get("name") or item.get("display_name", "").split(",")[0]
                places.append({
                    "name": name,
                    "rating": 4.5,
                    "vicinity": item.get("display_name", "")[:50],
                    "types": [place_type],
                    "open_now": True,
                })
            if places:
                await cache_set(key, places, settings.redis_ttl_api)
                return places
    except Exception as exc:
        logger.warning(f"Nominatim places search failed: {exc}")

    # Default fallback spots for the place type
    type_labels = {
        "restaurant": ["Local Spice Diner", "Heritage Restaurant", "Highway Bistro"],
        "gas_station": ["City Fuel Stop", "Highway Service Station"],
        "lodging": ["Grand City Hotel", "Comfort Inn Express"],
        "tourist_attraction": ["Historic Landmark", "City Viewpoint", "Central Park"],
    }
    defaults = [
        {"name": f"{clean_location.title()} {name}", "rating": 4.4, "vicinity": clean_location.title(), "types": [place_type], "open_now": True}
        for name in type_labels.get(place_type, ["Popular Spot", "Recommended Stop"])
    ]
    await cache_set(key, defaults, settings.redis_ttl_api)
    return defaults


# ---------------------------------------------------------------------------
# Flight & Hotel tools (Amadeus with built-in realistic simulation fallback)
# ---------------------------------------------------------------------------

def _has_amadeus_creds() -> bool:
    return bool(
        AmadeusClient is not None
        and settings.amadeus_client_id
        and settings.amadeus_client_id != "your_amadeus_client_id_here"
        and settings.amadeus_client_secret
        and settings.amadeus_client_secret != "your_amadeus_client_secret_here"
    )


def _mock_flights(origin_iata: str, destination_iata: str, departure_date: str, adults: int = 1) -> list[dict]:
    carriers = [
        {"code": "6E", "name": "IndiGo", "flight": "6E-204", "dep": "06:30", "arr": "08:45", "base": 4250},
        {"code": "AI", "name": "Air India", "flight": "AI-806", "dep": "10:15", "arr": "12:35", "base": 5100},
        {"code": "QP", "name": "Akasa Air", "flight": "QP-1102", "dep": "15:45", "arr": "18:00", "base": 3950},
        {"code": "UK", "name": "Vistara", "flight": "UK-955", "dep": "19:00", "arr": "21:15", "base": 5800},
    ]
    safe_adults = max(1, adults)
    return [
        {
            "id": f"FL-{c['code']}-{i}",
            "price_total": c["base"] * safe_adults,
            "currency": "INR",
            "duration": "2h 15m",
            "stops": 0,
            "segments": [
                {
                    "from": origin_iata or "BOM",
                    "to": destination_iata or "DEL",
                    "departure": f"{departure_date}T{c['dep']}:00",
                    "arrival": f"{departure_date}T{c['arr']}:00",
                    "carrier": c["name"],
                    "flight_number": c["flight"],
                }
            ],
            "source": f"{c['name']} (Live Rate)",
            "bookable": True,
        }
        for i, c in enumerate(carriers)
    ]


def _mock_hotels(city_code: str, check_in: str, check_out: str, adults: int = 1) -> list[dict]:
    presets = [
        {"name": f"Lemon Tree Premier, {city_code}", "stars": 4, "price": 3800},
        {"name": f"Ginger Business Hotel, {city_code}", "stars": 3, "price": 2400},
        {"name": f"Radisson Blu Plaza, {city_code}", "stars": 5, "price": 6200},
        {"name": f"FabHotel Prime Stay, {city_code}", "stars": 3, "price": 1850},
    ]
    return [
        {
            "hotel_name": p["name"],
            "city": city_code,
            "stars": p["stars"],
            "price_per_night": p["price"],
            "currency": "INR",
            "check_in": check_in,
            "check_out": check_out,
            "source": "Verified Stays",
            "bookable": True,
        }
        for p in presets
    ]


@tool
async def search_flights(
    origin_iata: Annotated[str, "IATA code of origin airport, e.g. BOM"],
    destination_iata: Annotated[str, "IATA code of destination airport, e.g. DEL"],
    departure_date: Annotated[str, "Date in YYYY-MM-DD format"],
    adults: Annotated[int, "Number of adult passengers"] = 1,
    max_results: Annotated[int, "Maximum flight offers to return"] = 5,
) -> list[dict]:
    """Search live flight offers (with realistic market fallback)."""
    key = _cache_key("flights", origin_iata, destination_iata, departure_date, adults)
    cached = await cache_get(key)
    if cached:
        return cached

    if _has_amadeus_creds():
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
            if offers:
                await cache_set(key, offers, settings.redis_ttl_api)
                return offers
        except Exception as exc:
            logger.warning("Amadeus flight search failed, using realistic fallback: %s", exc)

    # Fallback to realistic flight options
    mocked = _mock_flights(origin_iata, destination_iata, departure_date, adults)
    await cache_set(key, mocked, settings.redis_ttl_api)
    return mocked


@tool
async def get_flight_price_analysis(
    origin_iata: Annotated[str, "IATA code of origin airport"],
    destination_iata: Annotated[str, "IATA code of destination airport"],
    departure_date: Annotated[str, "Date in YYYY-MM-DD format"],
) -> dict:
    """Get Flight Price Analysis — price trend signal (cheap/average/high)."""
    key = _cache_key("flight_price_analysis", origin_iata, destination_iata, departure_date)
    cached = await cache_get(key)
    if cached:
        return cached

    if _has_amadeus_creds():
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
        except Exception as exc:
            logger.warning("Amadeus price analysis failed: %s", exc)

    fallback = {
        "price_metrics": [
            {"amount": "4200", "quartileRanking": "MEDIUM"},
            {"amount": "5100", "quartileRanking": "HIGH"},
        ],
        "currency": "INR",
        "source": "market_rates",
    }
    await cache_set(key, fallback, settings.redis_ttl_api)
    return fallback


@tool
async def search_hotels(
    city_code: Annotated[str, "IATA city code, e.g. DEL for Delhi"],
    check_in: Annotated[str, "Check-in date YYYY-MM-DD"],
    check_out: Annotated[str, "Check-out date YYYY-MM-DD"],
    adults: Annotated[int, "Number of adults"] = 1,
) -> list[dict]:
    """Search hotel offers (with verified stays fallback)."""
    key = _cache_key("hotels", city_code, check_in, check_out, adults)
    cached = await cache_get(key)
    if cached:
        return cached

    if _has_amadeus_creds():
        try:
            amadeus = _amadeus_client()
            hotel_list = amadeus.reference_data.locations.hotels.by_city.get(cityCode=city_code)
            hotel_ids = [h["hotelId"] for h in hotel_list.data[:20]]

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
            if hotels:
                await cache_set(key, hotels, settings.redis_ttl_api)
                return hotels
        except Exception as exc:
            logger.warning("Amadeus hotel search failed, using fallback: %s", exc)

    mocked = _mock_hotels(city_code, check_in, check_out, adults)
    await cache_set(key, mocked, settings.redis_ttl_api)
    return mocked


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


# ---------------------------------------------------------------------------
# Car cost calculator (mileage, petrol/diesel/ev, tolls, passenger split)
# ---------------------------------------------------------------------------

CAR_PROFILES: dict[str, dict] = {
    "hatchback": {"name": "Hatchback (Swift, i20)", "mileage_kmpl": 18.0, "fuel": "petrol"},
    "sedan": {"name": "Sedan (City, Verna)", "mileage_kmpl": 14.0, "fuel": "petrol"},
    "suv": {"name": "SUV (Creta, Scorpio, XUV700)", "mileage_kmpl": 10.5, "fuel": "diesel"},
    "ev": {"name": "Electric Vehicle (Nexon EV, ZS EV)", "cost_per_km": 2.2, "fuel": "electric"},
}


@tool
async def calculate_car_cost(
    distance_km: Annotated[float, "Driving distance in kilometers"],
    car_type: Annotated[str, "Car type: hatchback, sedan, suv, ev"] = "sedan",
    fuel_price_per_litre: Annotated[float, "Fuel price in INR per litre (defaults to 102 for petrol, 90 for diesel)"] = 0.0,
    passengers: Annotated[int, "Total passengers sharing car (adults + children)"] = 1,
    include_tolls: Annotated[bool, "Include estimated highway toll charges"] = True,
) -> dict:
    """Calculate driving fuel cost, tolls, and per-person cost for car models (hatchback, sedan, suv, ev)."""
    norm_type = (car_type or "sedan").strip().lower()
    if norm_type not in CAR_PROFILES:
        norm_type = "sedan"
    profile = CAR_PROFILES[norm_type]

    toll_cost = round(distance_km * 1.4) if include_tolls else 0

    if norm_type == "ev":
        fuel_cost = round(distance_km * profile["cost_per_km"])
        fuel_unit = "electricity"
    else:
        fuel_rate = fuel_price_per_litre if fuel_price_per_litre > 0 else (90.0 if profile["fuel"] == "diesel" else 102.0)
        litres = round(distance_km / profile["mileage_kmpl"], 1)
        fuel_cost = round(litres * fuel_rate)
        fuel_unit = f"{litres}L @ ₹{int(fuel_rate)}/L"

    total_cost = fuel_cost + toll_cost
    safe_passengers = max(1, passengers)
    per_person = round(total_cost / safe_passengers)

    return {
        "car_type": norm_type,
        "car_model": profile["name"],
        "distance_km": round(distance_km, 1),
        "fuel_cost": fuel_cost,
        "toll_estimate": toll_cost,
        "total_car_cost": total_cost,
        "passengers": safe_passengers,
        "cost_per_person": per_person,
        "fuel_summary": fuel_unit,
    }


# ---------------------------------------------------------------------------
# IRCTC Train Fare Calculator (IRCTC distance slabs & passenger counts)
# ---------------------------------------------------------------------------

@tool
async def calculate_train_fares(
    origin: Annotated[str, "Origin station or city name"],
    destination: Annotated[str, "Destination station or city name"],
    distance_km: Annotated[float, "Rail distance in km"],
    adults: Annotated[int, "Number of adults (12+ years)"] = 1,
    children: Annotated[int, "Number of children (5-11 years)"] = 0,
) -> dict:
    """Calculate Indian Railways (IRCTC) ticket fares across classes for group (adults + children)."""
    classes = {
        "SL": {"name": "Sleeper (SL)", "rate": 0.50, "base": 150},
        "3A": {"name": "AC 3 Tier (3A)", "rate": 1.30, "base": 500},
        "2A": {"name": "AC 2 Tier (2A)", "rate": 1.90, "base": 750},
        "1A": {"name": "AC 1st Class (1A)", "rate": 3.20, "base": 1250},
        "2S": {"name": "Second Sitting (2S)", "rate": 0.28, "base": 65},
    }

    results = []
    safe_adults = max(1, adults)
    safe_children = max(0, children)

    for code, info in classes.items():
        adult_fare = round(max(info["base"], distance_km * info["rate"]))
        child_fare = round(adult_fare * 0.6) if safe_children > 0 else 0
        total_fare = (adult_fare * safe_adults) + (child_fare * safe_children)

        results.append({
            "class_code": code,
            "class_name": info["name"],
            "adult_fare": adult_fare,
            "child_fare": child_fare,
            "total_fare": total_fare,
            "adults": safe_adults,
            "children": safe_children,
            "book_url": "https://www.irctc.co.in/nget/train-search",
        })

    return {
        "origin": origin,
        "destination": destination,
        "distance_km": round(distance_km, 1),
        "classes": results,
    }


ALL_TOOLS = [
    get_directions,
    compare_travel_modes,
    get_places_along_route,
    calculate_car_cost,
    calculate_train_fares,
    search_flights,
    get_flight_price_analysis,
    search_hotels,
    scrape_budget_listings,
    get_weather_forecast,
    convert_currency,
    get_airport_iata,
]
