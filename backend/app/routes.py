from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage
import uuid
import json

from app.database import get_db
from app.models import ConversationMessage, TripQuery
from app.agent import travel_graph

router = APIRouter(prefix="/api", tags=["travel"])


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    origin: str | None = None
    destination: str | None = None
    travel_date: str | None = None
    budget: float | None = None
    mode_preference: str | None = None
    adults: int | None = 1
    children: int | None = 0
    car_type: str | None = "sedan"


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    roadmap: dict | None = None
    price_signal: dict | None = None
    clarification_needed: bool = False


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    session_id = req.session_id or str(uuid.uuid4())

    # Persist user message
    db.add(ConversationMessage(session_id=session_id, role="user", content=req.message))
    await db.flush()

    # Build initial state
    initial_state = {
        "messages": [HumanMessage(content=req.message)],
        "origin": req.origin,
        "destination": req.destination,
        "travel_date": req.travel_date,
        "budget": req.budget,
        "mode_preference": req.mode_preference,
        "adults": req.adults or 1,
        "children": req.children or 0,
        "car_type": req.car_type or "sedan",
        "flights": None,
        "hotels": None,
        "budget_hotels": None,
        "directions": None,
        "car_cost": None,
        "train_fares": None,
        "weather": None,
        "flight_price_analysis": None,
        "roadmap": None,
        "price_signal": None,
        "clarification_needed": False,
    }

    # Run graph
    result = await travel_graph.ainvoke(initial_state)

    # Extract assistant reply
    from langchain_core.messages import AIMessage
    reply = next(
        (m.content for m in reversed(result["messages"]) if isinstance(m, AIMessage)),
        "I'm working on your travel plan.",
    )

    # Persist assistant message
    db.add(ConversationMessage(session_id=session_id, role="assistant", content=reply))

    # Persist trip query if slots resolved
    if result.get("origin") and result.get("destination"):
        db.add(TripQuery(
            session_id=session_id,
            origin=result.get("origin"),
            destination=result.get("destination"),
            travel_date=result.get("travel_date"),
            budget=result.get("budget"),
            mode_preference=result.get("mode_preference"),
        ))

    # Store historical fare data for model training
    await _store_fare_records(db, result)

    return ChatResponse(
        session_id=session_id,
        reply=reply,
        roadmap=result.get("roadmap"),
        price_signal=result.get("price_signal"),
        clarification_needed=result.get("clarification_needed", False),
    )


@router.get("/session/{session_id}/history")
async def get_history(session_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    stmt = select(ConversationMessage).where(
        ConversationMessage.session_id == session_id
    ).order_by(ConversationMessage.created_at)
    result = await db.execute(stmt)
    messages = result.scalars().all()
    return [{"role": m.role, "content": m.content, "created_at": str(m.created_at)} for m in messages]


async def _store_fare_records(db: AsyncSession, state: dict):
    """Persist fare observations for future model training."""
    from app.models import FareRecord
    from datetime import date as dt_date
    import datetime

    travel_date = state.get("travel_date", "")
    query_date = str(dt_date.today())
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    route_key = f"{origin[:3].upper()}-{destination[:3].upper()}"

    try:
        travel_dt = datetime.datetime.strptime(travel_date, "%Y-%m-%d").date()
        days_to_departure = (travel_dt - dt_date.today()).days
        day_of_week = travel_dt.weekday()
    except Exception:
        days_to_departure = -1
        day_of_week = -1

    for flight in (state.get("flights") or [])[:3]:
        price = float(flight.get("price_total") or 0)
        if price > 0:
            db.add(FareRecord(
                route_key=route_key,
                mode="flight",
                price=price,
                currency=flight.get("currency", "INR"),
                travel_date=travel_date,
                query_date=query_date,
                days_to_departure=days_to_departure,
                day_of_week=day_of_week,
                source="amadeus",
            ))
