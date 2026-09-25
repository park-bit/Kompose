from sqlalchemy import Column, String, Float, DateTime, Integer, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class TripQuery(Base):
    __tablename__ = "trip_queries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(64), nullable=False, index=True)
    origin = Column(String(256))
    destination = Column(String(256))
    travel_date = Column(String(32))
    budget = Column(Float, nullable=True)
    mode_preference = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FareRecord(Base):
    """Historical fare data for price trend model training."""
    __tablename__ = "fare_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    route_key = Column(String(64), nullable=False, index=True)  # e.g. "BOM-DEL"
    mode = Column(String(16))                                    # flight/train/bus
    price = Column(Float, nullable=False)
    currency = Column(String(8), default="INR")
    travel_date = Column(String(32))
    query_date = Column(String(32))
    days_to_departure = Column(Integer)
    day_of_week = Column(Integer)                                # 0=Monday
    source = Column(String(32))                                  # amadeus/apify/etc
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class HotelRecord(Base):
    """Historical hotel price data for price trend model training."""
    __tablename__ = "hotel_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    city = Column(String(128), nullable=False, index=True)
    hotel_name = Column(String(256))
    price_per_night = Column(Float)
    currency = Column(String(8), default="INR")
    check_in_date = Column(String(32))
    query_date = Column(String(32))
    days_to_checkin = Column(Integer)
    day_of_week = Column(Integer)
    stars = Column(Integer, nullable=True)
    source = Column(String(32))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    role = Column(String(16))   # user / assistant / tool
    content = Column(Text)
    extra = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
