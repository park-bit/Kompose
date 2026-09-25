"""
LangGraph travel planning agent.

Graph flow:
  user_input -> slot_extractor -> clarify? (conditional) -> parallel_fetch -> optimizer -> price_trend -> respond

The orchestrator LLM (Gemini) uses function calling to invoke tools in the
parallel_fetch node. Tools run concurrently via asyncio.gather.
"""
import asyncio
import json
import logging
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from app.config import get_settings
from app.tools import ALL_TOOLS
from app.price_trend import PriceTrendPredictor

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class TravelState(TypedDict):
    messages: Annotated[list, add_messages]
    # Extracted slots
    origin: str | None
    destination: str | None
    travel_date: str | None
    budget: float | None
    mode_preference: str | None
    adults: int | None
    children: int | None
    car_type: str | None
    # Fetched data
    flights: list | None
    hotels: list | None
    budget_hotels: list | None
    directions: dict | None
    car_cost: dict | None
    train_fares: dict | None
    bus_fares: dict | None
    weather: dict | None
    flight_price_analysis: dict | None
    # Computed outputs
    roadmap: dict | None
    price_signal: dict | None
    clarification_needed: bool


# ---------------------------------------------------------------------------
# LLM setup
# ---------------------------------------------------------------------------

def _build_llm():
    return ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.llm_api_key,
        temperature=0.1,
    )


# ---------------------------------------------------------------------------
# Node: slot extractor
# ---------------------------------------------------------------------------

async def slot_extractor(state: TravelState) -> dict:
    import datetime
    llm = _build_llm()
    today_str = datetime.date.today().isoformat()

    slot_system = f"""You are a travel planning assistant.
Today's date is {today_str}.

Extract the following travel slots from the conversation:
- origin: departure city/place
- destination: arrival city/place
- travel_date: departure date (ISO format YYYY-MM-DD; if a date range is given, use the start/departure date)
- budget: numeric budget in INR (or null)
- mode_preference: travel mode (flight, train, bus, car, mixed, train_bus, bus_car, flight_car, flight_train, or null if not explicitly mentioned)
- adults: number of adults (integer, default 1)
- children: number of children (integer, default 0)
- car_type: vehicle model type: hatchback / sedan / suv / ev (or null)

Respond with ONLY a valid JSON object with these keys. Use null for missing or unspecified values.
Do not add any explanation."""

    last_human = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
    )

    recent_msgs = state.get("messages", [])[-6:]
    conversation_lines = []
    for m in recent_msgs:
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        conversation_lines.append(f"{role}: {m.content}")
    conversation_text = "\n".join(conversation_lines) if conversation_lines else last_human

    response = await llm.ainvoke([
        SystemMessage(content=slot_system),
        HumanMessage(content=f"Conversation:\n{conversation_text}\n\nExtract travel slots as JSON:"),
    ])

    raw_text = response.content.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        slots = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse slot JSON: %s", raw_text)
        slots = {}

    adults_val = slots.get("adults") or state.get("adults") or 1
    try:
        adults_val = int(adults_val)
    except (ValueError, TypeError):
        adults_val = 1

    children_val = slots.get("children") or state.get("children") or 0
    try:
        children_val = int(children_val)
    except (ValueError, TypeError):
        children_val = 0

    car_type_val = (slots.get("car_type") or state.get("car_type") or "sedan").lower()

    budget_val = slots.get("budget") if slots.get("budget") is not None else state.get("budget")
    if budget_val is not None:
        try:
            budget_val = float(budget_val)
        except (ValueError, TypeError):
            budget_val = None

    mode_pref_val = (slots.get("mode_preference") or state.get("mode_preference") or "mixed").lower()

    resolved_origin = slots.get("origin") or state.get("origin")
    resolved_destination = slots.get("destination") or state.get("destination")
    resolved_travel_date = slots.get("travel_date") or state.get("travel_date")

    needs_clarification = not resolved_origin or not resolved_destination or not resolved_travel_date

    return {
        "origin": resolved_origin,
        "destination": resolved_destination,
        "travel_date": resolved_travel_date,
        "budget": budget_val,
        "mode_preference": mode_pref_val,
        "adults": max(1, adults_val),
        "children": max(0, children_val),
        "car_type": car_type_val,
        "clarification_needed": needs_clarification,
    }


# ---------------------------------------------------------------------------
# Node: clarify
# ---------------------------------------------------------------------------

async def clarify(state: TravelState) -> dict:
    missing = []
    if not state.get("origin"):
        missing.append("departure city")
    if not state.get("destination"):
        missing.append("destination")
    if not state.get("travel_date"):
        missing.append("travel date")

    question = f"Could you please tell me your {' and '.join(missing)}?"
    return {
        "messages": [AIMessage(content=question)],
        "clarification_needed": True,
    }


def should_clarify(state: TravelState) -> str:
    if state.get("clarification_needed"):
        return "clarify"
    return "parallel_fetch"


# ---------------------------------------------------------------------------
# Node: parallel data fetch
# ---------------------------------------------------------------------------

async def parallel_fetch(state: TravelState) -> dict:
    origin = state.get("origin") or "Mumbai"
    destination = state.get("destination") or "Delhi"
    travel_date = state.get("travel_date") or "2025-12-01"
    mode = state.get("mode_preference") or "mixed"
    adults = state.get("adults") or 1
    children = state.get("children") or 0
    total_passengers = max(1, adults + children)
    car_type = state.get("car_type") or "sedan"

    from app.tools import (
        get_directions, compare_travel_modes, search_flights,
        get_flight_price_analysis, search_hotels, scrape_budget_listings,
        get_weather_forecast, get_airport_iata,
        calculate_car_cost, calculate_train_fares, calculate_bus_fares,
    )

    # Resolve IATA codes for flights
    async def safe(coro):
        try:
            return await coro
        except Exception as exc:
            logger.warning("Tool error: %s", exc)
            return None

    origin_iata_task = safe(get_airport_iata.ainvoke({"city_name": origin}))
    dest_iata_task = safe(get_airport_iata.ainvoke({"city_name": destination}))

    origin_iata_res, dest_iata_res = await asyncio.gather(origin_iata_task, dest_iata_task)
    origin_iata = (origin_iata_res or {}).get("top_iata") or "BOM"
    dest_iata = (dest_iata_res or {}).get("top_iata") or "DEL"

    # Fetch directions first to get distance for car, train & bus calculations
    directions = await safe(get_directions.ainvoke({
        "origin": origin,
        "destination": destination,
        "mode": "driving" if mode == "car" else "transit"
    }))

    distance_km = 800.0  # default estimate if route missing
    if directions and directions.get("routes"):
        r0 = directions["routes"][0]
        dist_val = r0.get("distance", {}).get("value")
        if dist_val:
            distance_km = dist_val / 1000.0

    (
        flights,
        flight_analysis,
        hotels,
        budget_hotels,
        weather,
        car_cost,
        train_fares,
        bus_fares,
    ) = await asyncio.gather(
        safe(search_flights.ainvoke({"origin_iata": origin_iata, "destination_iata": dest_iata, "departure_date": travel_date, "adults": adults})),
        safe(get_flight_price_analysis.ainvoke({"origin_iata": origin_iata, "destination_iata": dest_iata, "departure_date": travel_date})),
        safe(search_hotels.ainvoke({"city_code": dest_iata, "check_in": travel_date, "check_out": travel_date, "adults": adults})),
        safe(scrape_budget_listings.ainvoke({"destination": destination, "check_in": travel_date})),
        safe(get_weather_forecast.ainvoke({"city": destination, "travel_date": travel_date})),
        safe(calculate_car_cost.ainvoke({"distance_km": distance_km, "car_type": car_type, "passengers": total_passengers})),
        safe(calculate_train_fares.ainvoke({"origin": origin, "destination": destination, "distance_km": distance_km, "adults": adults, "children": children})),
        safe(calculate_bus_fares.ainvoke({"origin": origin, "destination": destination, "distance_km": distance_km, "passengers": total_passengers})),
    )

    return {
        "directions": directions,
        "flights": flights or [],
        "flight_price_analysis": flight_analysis or {},
        "hotels": hotels or [],
        "budget_hotels": budget_hotels or [],
        "weather": weather or {},
        "car_cost": car_cost,
        "train_fares": train_fares,
        "bus_fares": bus_fares,
    }


# ---------------------------------------------------------------------------
# Node: budget optimizer
# ---------------------------------------------------------------------------

async def budget_optimizer(state: TravelState) -> dict:
    budget = state.get("budget")
    flights = state.get("flights") or []
    hotels = state.get("hotels") or []
    budget_hotels = state.get("budget_hotels") or []
    car_cost = state.get("car_cost")
    train_fares = state.get("train_fares")
    bus_fares = state.get("bus_fares")
    adults = state.get("adults") or 1
    children = state.get("children") or 0
    total_passengers = max(1, adults + children)
    rooms_needed = max(1, (total_passengers + 1) // 2)

    # Filter flights within budget (if budget known)
    if budget:
        affordable_flights = [f for f in flights if _price_float(f.get("price_total")) <= budget * 0.5]
        if not affordable_flights:
            affordable_flights = flights
    else:
        affordable_flights = flights

    cheapest_flight = min(flights, key=lambda f: _price_float(f.get("price_total")), default=None)
    cheapest_hotel = min(hotels, key=lambda h: _price_float(h.get("price_per_night")), default=None)
    cheapest_budget = min(budget_hotels, key=lambda h: _price_float(h.get("price_starting_from")), default=None)

    mode_pref = (state.get("mode_preference") or "mixed").lower()
    valid_modes = {"mixed", "flight", "train", "bus", "car", "train_bus", "bus_car", "flight_car", "flight_train"}
    if mode_pref not in valid_modes:
        mode_pref = "mixed"

    include_flight = mode_pref in ("mixed", "flight", "flight_car", "flight_train")
    include_train = mode_pref in ("mixed", "train", "train_bus", "flight_train")
    include_bus = mode_pref in ("mixed", "bus", "train_bus", "bus_car")
    include_car = mode_pref in ("mixed", "car", "flight_car", "bus_car")

    # Build roadmap legs
    legs = []
    daily_cost = {}

    if include_flight and cheapest_flight:
        legs.append({
            "mode": "flight",
            "from": state.get("origin"),
            "to": state.get("destination"),
            "departure": cheapest_flight.get("segments", [{}])[0].get("departure") if cheapest_flight.get("segments") else None,
            "cost": cheapest_flight.get("price_total"),
            "currency": cheapest_flight.get("currency", "INR"),
            "bookable": True,
            "source": "Amadeus",
            "disclaimer": f"For {adults} adult(s)",
        })

    # Train option (IRCTC)
    if include_train and train_fares and train_fares.get("classes"):
        chosen_train = next((c for c in train_fares["classes"] if c["class_code"] in ("3A", "SL")), train_fares["classes"][0])
        legs.append({
            "mode": "train",
            "from": state.get("origin"),
            "to": state.get("destination"),
            "name": f"IRCTC Train ({chosen_train['class_name']})",
            "cost": chosen_train["total_fare"],
            "currency": "INR",
            "bookable": True,
            "source": "IRCTC",
            "source_url": chosen_train.get("book_url"),
            "disclaimer": f"Total for {adults} adult(s)" + (f", {children} child(ren)" if children else ""),
        })

    # Bus option
    if include_bus and bus_fares and bus_fares.get("options"):
        chosen_bus = next((b for b in bus_fares["options"] if b["bus_type"] == "AC_SLEEPER"), bus_fares["options"][0])
        legs.append({
            "mode": "bus",
            "from": state.get("origin"),
            "to": state.get("destination"),
            "name": f"Intercity Bus ({chosen_bus['type_name']})",
            "cost": chosen_bus["total_fare"],
            "currency": "INR",
            "bookable": True,
            "source": "Bus Booking",
            "source_url": chosen_bus.get("book_url"),
            "disclaimer": f"Est. {chosen_bus['duration_est']} · Total for {total_passengers} passenger(s)",
        })

    # Car option (Fuel + Tolls)
    if include_car and car_cost:
        legs.append({
            "mode": "car",
            "from": state.get("origin"),
            "to": state.get("destination"),
            "name": f"Driving: {car_cost['car_model']}",
            "cost": car_cost["total_car_cost"],
            "currency": "INR",
            "bookable": False,
            "source": "Fuel & Tolls",
            "disclaimer": f"₹{car_cost['cost_per_person']}/person ({car_cost['fuel_summary']}, ₹{car_cost['toll_estimate']} tolls)",
        })

    if cheapest_hotel:
        hotel_night_price = _price_float(cheapest_hotel.get("price_per_night"))
        legs.append({
            "mode": "hotel",
            "name": cheapest_hotel.get("hotel_name"),
            "city": cheapest_hotel.get("city"),
            "price_per_night": hotel_night_price * rooms_needed,
            "currency": cheapest_hotel.get("currency", "INR"),
            "bookable": True,
            "source": "Amadeus",
            "disclaimer": f"{rooms_needed} room(s) for {total_passengers} guest(s)",
        })

    if cheapest_budget:
        legs.append({
            "mode": "budget_hotel",
            "name": cheapest_budget.get("name"),
            "price_starting_from": cheapest_budget.get("price_starting_from"),
            "currency": "INR",
            "bookable": False,
            "source": cheapest_budget.get("source"),
            "source_url": cheapest_budget.get("source_url"),
            "disclaimer": cheapest_budget.get("disclaimer"),
        })

    # TensorFlow Multi-modal Option Scoring
    from app.travel_ranker import TravelRankerTF
    ranker = TravelRankerTF()
    dist_km = 800.0
    if state.get("directions") and state.get("directions", {}).get("routes"):
        dist_val = state["directions"]["routes"][0].get("distance", {}).get("value")
        if dist_val:
            dist_km = dist_val / 1000.0

    scored_candidates = []
    for leg in legs:
        m = leg.get("mode")
        if m in ("flight", "train", "bus", "car"):
            cost_val = _price_float(leg.get("cost"))
            dur = max(1.5, dist_km / (500.0 if m == "flight" else (60.0 if m == "train" else (45.0 if m == "bus" else 55.0))))
            leg_score = ranker.score_option(
                mode=m,
                cost=cost_val,
                duration_hrs=dur,
                distance_km=dist_km,
                passengers=total_passengers,
                budget=budget,
            )
            leg["ai_score"] = leg_score
            scored_candidates.append(leg)

    if scored_candidates:
        best_leg = max(scored_candidates, key=lambda l: l.get("ai_score", 0.0))
        best_leg["recommended"] = True
        best_leg["recommendation_tag"] = "AI Top Pick"

    # Day-by-day cost estimate
    travel_date = state.get("travel_date", "")
    hotel_daily = (_price_float(cheapest_hotel.get("price_per_night")) if cheapest_hotel else 0) * rooms_needed

    transport_candidates = []
    if include_flight and cheapest_flight:
        transport_candidates.append(_price_float(cheapest_flight.get("price_total")))
    if include_train and train_fares and train_fares.get("classes"):
        chosen_train = next((c for c in train_fares["classes"] if c["class_code"] in ("3A", "SL")), train_fares["classes"][0])
        transport_candidates.append(float(chosen_train.get("total_fare", 0)))
    if include_bus and bus_fares and bus_fares.get("options"):
        chosen_bus = next((b for b in bus_fares["options"] if b["bus_type"] == "AC_SLEEPER"), bus_fares["options"][0])
        transport_candidates.append(float(chosen_bus.get("total_fare", 0)))
    if include_car and car_cost:
        transport_candidates.append(float(car_cost.get("total_car_cost", 0)))

    transport_daily = min(transport_candidates) if transport_candidates else 0.0
    food_daily = (adults * 800) + (children * 450)

    daily_cost[travel_date] = {
        "transport": transport_daily,
        "hotel": hotel_daily,
        "food_estimate": food_daily,
        "total": transport_daily + hotel_daily + food_daily,
    }

    total_estimate = sum(d["total"] for d in daily_cost.values())
    over_budget = budget and total_estimate > budget

    roadmap = {
        "origin": state.get("origin"),
        "destination": state.get("destination"),
        "travel_date": state.get("travel_date"),
        "budget": budget,
        "mode_preference": mode_pref,
        "legs": legs,
        "daily_cost": daily_cost,
        "total_estimate": total_estimate,
        "over_budget": over_budget,
        "weather": state.get("weather"),
        "passengers": {
            "adults": adults,
            "children": children,
            "total": total_passengers,
            "rooms_needed": rooms_needed,
        },
        "car_cost": car_cost,
        "train_fares": train_fares,
        "bus_fares": bus_fares,
        "all_flights": affordable_flights[:5] if include_flight else [],
        "all_hotels": hotels[:5],
        "budget_hotels": budget_hotels[:5],
    }

    return {"roadmap": roadmap}


def _price_float(val) -> float:
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Node: price trend signal
# ---------------------------------------------------------------------------

_predictor: PriceTrendPredictor | None = None


def _get_predictor() -> PriceTrendPredictor:
    global _predictor
    import os
    from app.price_trend import PriceTrendPredictor
    if _predictor is None or _predictor.model is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_path = os.path.join(base_dir, "models", "price_trend_model.keras")
        _predictor = PriceTrendPredictor(model_path)
    return _predictor


async def price_trend_node(state: TravelState) -> dict:
    roadmap = state.get("roadmap") or {}
    flight_analysis = state.get("flight_price_analysis") or {}

    signal = {"signal": "unknown", "confidence": 0.0, "note": "Insufficient data for price prediction."}

    try:
        predictor = _get_predictor()
        travel_date = state.get("travel_date")
        cheapest = min(
            (f for f in state.get("flights") or [] if f.get("price_total")),
            key=lambda f: _price_float(f.get("price_total")),
            default=None,
        )
        if travel_date:
            price = _price_float(cheapest.get("price_total")) if cheapest else 5000.0
            signal = predictor.predict(price=price, travel_date=travel_date)
    except Exception as exc:
        logger.warning("Price trend prediction failed: %s", exc)
        signal["note"] = f"Price trend model unavailable: {exc}. Amadeus price metrics: {flight_analysis.get('price_metrics', [])}"

    signal["disclaimer"] = (
        "This is an estimate based on historical patterns. It is not a guarantee. "
        "Prices may change at any time."
    )

    return {"price_signal": signal}


# ---------------------------------------------------------------------------
# Node: respond
# ---------------------------------------------------------------------------

async def respond(state: TravelState) -> dict:
    roadmap = state.get("roadmap") or {}
    price_signal = state.get("price_signal") or {}

    summary_parts = [
        f"Here is your travel plan from **{roadmap.get('origin')}** to **{roadmap.get('destination')}** on **{roadmap.get('travel_date')}**.",
    ]

    if roadmap.get("over_budget"):
        summary_parts.append(
            f"Note: The estimated total of **₹{roadmap.get('total_estimate', 0):,.0f}** exceeds your budget of **₹{roadmap.get('budget', 0):,.0f}**. "
            "The cheapest viable options are highlighted."
        )

    signal = price_signal.get("signal", "unknown")
    if signal == "book_now":
        summary_parts.append("Price trend advisory: Prices appear to be rising. Consider booking soon.")
    elif signal == "wait":
        summary_parts.append("Price trend advisory: Prices may drop closer to the date. You could wait a few days.")

    summary_parts.append(price_signal.get("disclaimer", ""))

    content = "\n\n".join(summary_parts)
    return {"messages": [AIMessage(content=content)]}


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def build_graph():
    graph = StateGraph(TravelState)

    graph.add_node("slot_extractor", slot_extractor)
    graph.add_node("clarify", clarify)
    graph.add_node("parallel_fetch", parallel_fetch)
    graph.add_node("budget_optimizer", budget_optimizer)
    graph.add_node("price_trend", price_trend_node)
    graph.add_node("respond", respond)

    graph.set_entry_point("slot_extractor")
    graph.add_conditional_edges("slot_extractor", should_clarify, {"clarify": "clarify", "parallel_fetch": "parallel_fetch"})
    graph.add_edge("clarify", END)
    graph.add_edge("parallel_fetch", "budget_optimizer")
    graph.add_edge("budget_optimizer", "price_trend")
    graph.add_edge("price_trend", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


travel_graph = build_graph()
