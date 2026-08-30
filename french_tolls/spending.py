# -*- coding=utf-8 -*-
import datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from . import db
from .models import GoogleRequest

__all__ = ["google_requests_this_month", "reserve_google_request"]


def _current_month():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")


async def google_requests_this_month():
    async with db.Session() as session:
        count = await session.scalar(
            select(GoogleRequest.count).where(
                GoogleRequest.year_month == _current_month()))

    return count or 0


async def reserve_google_request(ceiling):
    if ceiling <= 0:
        return False

    # One statement, and that is the point of it.
    #
    # The read and the write used to be a SELECT and an INSERT inside an explicit
    # BEGIN IMMEDIATE, so the guarantee that two journeys answered at once cannot
    # both claim the last request rested on the transaction being IMMEDIATE. A
    # single statement is atomic whatever the transaction mode, so correctness
    # stops depending on how a connection was configured somewhere else.
    #
    # The `where` is what refuses at the ceiling: the update is skipped, the
    # conflicting insert is a no-op, and nothing comes back. Below the ceiling it
    # returns the new count, and that row is the claim.
    claim = (
        insert(GoogleRequest)
        .values(year_month=_current_month(), count=1)
        .on_conflict_do_update(
            index_elements=[GoogleRequest.year_month],
            set_={"count": GoogleRequest.count + 1},
            where=GoogleRequest.count < ceiling,
        )
        .returning(GoogleRequest.count)
    )

    async with db.Session() as session:
        claimed = await session.scalar(claim)
        await session.commit()

    return claimed is not None
