# -*- coding=utf-8 -*-
from sqlalchemy import Integer, JSON, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Autocomplete", "Base", "GoogleRequest"]


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
