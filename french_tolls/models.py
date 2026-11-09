# -*- coding=utf-8 -*-
import datetime

from sqlalchemy import DateTime, Float, Integer, JSON, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Autocomplete", "Base", "Car", "GasStation", "GasStationArea", "GoogleRequest"]


class Base(DeclarativeBase):
    pass


class Autocomplete(Base):
    """What LocationIQ answered for a query, kept because the answer was paid for."""

    __tablename__ = "autocomplete"

    q: Mapped[str] = mapped_column(Text, primary_key=True)
    response: Mapped[list] = mapped_column(JSON, nullable=False)


class GoogleRequest(Base):
    """One row per calendar month, counting what has been spent against Google."""

    __tablename__ = "google_requests"

    year_month: Mapped[str] = mapped_column(Text, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


class GasStation(Base):
    """A station of prix-carburants.gouv.fr, kept so that a run reads only the stale pages."""

    __tablename__ = "gas_station"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[list] = mapped_column(JSON, nullable=False)
    services: Mapped[list] = mapped_column(JSON, nullable=False)
    prices: Mapped[list] = mapped_column(JSON, nullable=False)
    # Naive UTC. SQLite keeps no offset and compares these values as text.
    last_updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)


class GasStationArea(Base):
    """The R*Tree index of the station positions.

    Triggers on `gas_station` write it. Code that writes it directly makes it
    disagree with the table.
    """

    __tablename__ = "gas_station_area"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    min_latitude: Mapped[float] = mapped_column(Float)
    max_latitude: Mapped[float] = mapped_column(Float)
    min_longitude: Mapped[float] = mapped_column(Float)
    max_longitude: Mapped[float] = mapped_column(Float)


class Car(Base):
    __tablename__ = "car"

    telegram_user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    fuel_type: Mapped[str] = mapped_column(Text, nullable=False)
    tank_volume: Mapped[int] = mapped_column(Integer, nullable=False)
    consume_80: Mapped[float] = mapped_column(Float, nullable=False)
    consume_130: Mapped[float] = mapped_column(Float, nullable=False)
    gauge_steps: Mapped[int] = mapped_column(Integer, nullable=False, server_default="16")
    reserve: Mapped[float] = mapped_column(Float, nullable=False, server_default="5")
    reserve_km: Mapped[float] = mapped_column(Float, nullable=False, server_default="50")
