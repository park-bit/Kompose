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
    # Fetched data
    flights: list | None
    hotels: list | None
    budget_hotels: list | None
    directions: list | None
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

SLOT_SYSTEM = """You are a travel planning assistant. Extract the following slots from the user message:
- origin: departure city/place
- destination: arrival city/place
- travel_date: date of travel (ISO format YYYY-MM-DD if determinable)
- budget: numeric budget in INR (or null)
- mode_preference: one of car/train/flight/mixed (or null)

Respond with ONLY a valid JSON object with these keys. Use null for missing values.
Do not add any explanation."""


async def slot_extractor(state: TravelState) -> dict:
    llm = _build_llm()
    last_human = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
    )

    response = await llm.ainvoke([
        SystemMessage(content=SLOT_SYSTEM),
        HumanMessage(content=last_human),
    ])

    try:
        slots = json.loads(response.content.strip().strip("```json").strip("```"))
    except json.JSONDecodeError:
        slots = {}

    return {
        "origin": slots.get("origin") or state.get("origin"),
        "destination": slots.get("destination") or state.get("destination"),
        "travel_date": slots.get("travel_date") or state.get("travel_date"),
        "budget": slots.get("budget") or state.get("budget"),
        "mode_preference": slots.get("mode_preference") or state.get("mode_preference"),
        "clarification_needed": not slots.get("destination") or not slots.get("travel_date"),
    }


# ---------------------------------------------------------------------------
# Node: clarify
# ---------------------------------------------------------------------------

async def clarify(state: TravelState) -> dict:
    missing = []
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
    origin = state.get("origin", "Mumbai")
    destination = state.get("destination", "Delhi")
    travel_date = state.get("travel_date", "2025-12-01")
    mode = state.get("mode_preference", "mixed")

    from app.tools import (
        get_directions, compare_travel_modes, search_flights,
        get_flight_price_analysis, search_hotels, scrape_budget_listings,
        get_weather_forecast, get_airport_iata,
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
    origin_iata = (origin_iata_res or {}).get("top_iata", "BOM")
    dest_iata = (dest_iata_res or {}).get("top_iata", "DEL")

    (
        directions,
        flights,
        flight_analysis,
        hotels,
        budget_hotels,
        weather,
    ) = await asyncio.gather(
        safe(get_directions.ainvoke({"origin": origin, "destination": destination, "mode": "driving" if mode == "car" else "transit"})),
        safe(search_flights.ainvoke({"origin_iata": origin_iata, "destination_iata": dest_iata, "departure_date": travel_date})),
        safe(get_flight_price_analysis.ainvoke({"origin_iata": origin_iata, "destination_iata": dest_iata, "departure_date": travel_date})),
        safe(search_hotels.ainvoke({"city_code": dest_iata, "check_in": travel_date, "check_out": travel_date})),
        safe(scrape_budget_listings.ainvoke({"destination": destination, "check_in": travel_date})),
        safe(get_weather_forecast.ainvoke({"city": destination, "travel_date": travel_date})),
    )

    return {
        "directions": directions,
        "flights": flights or [],
        "flight_price_analysis": flight_analysis or {},
        "hotels": hotels or [],
        "budget_hotels": budget_hotels or [],
        "weather": weather or {},
    }


# ---------------------------------------------------------------------------
# Node: budget optimizer
# ---------------------------------------------------------------------------

async def budget_optimizer(state: TravelState) -> dict:
    budget = state.get("budget")
    flights = state.get("flights") or []
    hotels = state.get("hotels") or []
    budget_hotels = state.get("budget_hotels") or []

    # Filter flights within budget (if budget known)
    if budget:
        affordable_flights = [f for f in flights if _price_float(f.get("price_total")) <= budget * 0.5]
        if not affordable_flights:
            affordable_flights = flights  # show all, flag over budget
    else:
        affordable_flights = flights

    cheapest_flight = min(flights, key=lambda f: _price_float(f.get("price_total")), default=None)
    cheapest_hotel = min(hotels, key=lambda h: _price_float(h.get("price_per_night")), default=None)
    cheapest_budget = min(budget_hotels, key=lambda h: _price_float(h.get("price_starting_from")), default=None)

    # Build roadmap
    legs = []
    daily_cost = {}

    if cheapest_flight:
        legs.append({
            "mode": "flight",
            "from": state.get("origin"),
            "to": state.get("destination"),
            "departure": cheapest_flight.get("segments", [{}])[0].get("departure") if cheapest_flight.get("segments") else None,
            "cost": cheapest_flight.get("price_total"),
            "currency": cheapest_flight.get("currency", "INR"),
            "bookable": True,
            "source": "Amadeus",
        })

    if cheapest_hotel:
        legs.append({
            "mode": "hotel",
            "name": cheapest_hotel.get("hotel_name"),
            "city": cheapest_hotel.get("city"),
            "price_per_night": cheapest_hotel.get("price_per_night"),
            "currency": cheapest_hotel.get("currency", "INR"),
            "bookable": True,
            "source": "Amadeus",
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

    # Day-by-day cost estimate
    travel_date = state.get("travel_date", "")
    daily_cost[travel_date] = {
        "transport": _price_float(cheapest_flight.get("price_total")) if cheapest_flight else 0,
        "hotel": _price_float(cheapest_hotel.get("price_per_night")) if cheapest_hotel else 0,
        "food_estimate": 800,  # rough daily food estimate INR
        "total": (
            _price_float(cheapest_flight.get("price_total") if cheapest_flight else 0)
            + _price_float(cheapest_hotel.get("price_per_night") if cheapest_hotel else 0)
            + 800
        ),
    }

    total_estimate = sum(d["total"] for d in daily_cost.values())
    over_budget = budget and total_estimate > budget

    roadmap = {
        "origin": state.get("origin"),
        "destination": state.get("destination"),
        "travel_date": state.get("travel_date"),
        "budget": budget,
        "legs": legs,
        "daily_cost": daily_cost,
        "total_estimate": total_estimate,
        "over_budget": over_budget,
        "weather": state.get("weather"),
        "all_flights": affordable_flights[:5],
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
    if _predictor is None:
        _predictor = PriceTrendPredictor(settings.price_model_path)
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
        if cheapest and travel_date:
            price = _price_float(cheapest.get("price_total"))
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
