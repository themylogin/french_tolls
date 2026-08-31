# -*- coding=utf-8 -*-
"""The claim against the month's ceiling, which is the one thing here that costs.

Against a real SQLite file in a temporary directory, migrated by alembic rather
than built from the models: what a deployment runs is the revision, and a test
that built the schema another way would pass over a revision that did not.

The claim is one statement on purpose, so that two journeys answered at once
cannot both take the last request. `test_two_at_once_*` is what that is for, and
it is the reason the statement is not a read followed by a write.
"""
import asyncio

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .. import db, spending

ALEMBIC_INI = __file__.rsplit("/", 3)[0] + "/alembic.ini"


@pytest.fixture
def store(tmp_path, monkeypatch):
    """An empty, migrated store of this test's own.

    Both halves are redirected the way each is meant to be: alembic's URL through
    `set_main_option`, which is what it is for, and the application's sessions by
    handing `db` a sessionmaker of this test's own. Neither reaches inside the
    module to make it open somewhere else.
    """
    db_path = tmp_path / "database.db"

    cfg = Config(ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(db, "Session", async_sessionmaker(engine, expire_on_commit=False))
    yield
    asyncio.run(engine.dispose())


def test_a_fresh_month_has_spent_nothing(store):
    assert asyncio.run(spending.google_requests_this_month()) == 0


def test_a_claim_below_the_ceiling_is_granted(store):
    async def go():
        assert await spending.reserve_google_request(5) is True
        assert await spending.google_requests_this_month() == 1
        assert await spending.reserve_google_request(5) is True
        assert await spending.google_requests_this_month() == 2

    asyncio.run(go())


def test_a_claim_at_the_ceiling_is_refused_and_costs_nothing(store):
    async def go():
        for _ in range(3):
            await spending.reserve_google_request(3)
        assert await spending.google_requests_this_month() == 3

        assert await spending.reserve_google_request(3) is False
        # The refusal must not increment. A ceiling that counted its own
        # refusals would push the month further past it on every retry.
        assert await spending.google_requests_this_month() == 3

    asyncio.run(go())


def test_a_ceiling_of_zero_refuses_the_first_claim_of_a_month(store):
    """The case the statement's own `where` does not cover.

    On the first claim of a month there is no conflicting row, so the `where`
    never runs. Without the guard in front of it, a ceiling of zero would admit
    exactly one request per month.
    """
    async def go():
        assert await spending.reserve_google_request(0) is False
        assert await spending.google_requests_this_month() == 0
        assert await spending.reserve_google_request(-1) is False
        assert await spending.google_requests_this_month() == 0

    asyncio.run(go())


def test_two_at_once_below_the_ceiling_both_count(store):
    async def go():
        granted = await asyncio.gather(
            *(spending.reserve_google_request(10) for _ in range(10)))
        assert sum(granted) == 10
        assert await spending.google_requests_this_month() == 10

    asyncio.run(go())


def test_two_at_once_at_the_ceiling_do_not_both_take_the_last(store):
    async def go():
        granted = await asyncio.gather(
            *(spending.reserve_google_request(4) for _ in range(10)))
        assert sum(granted) == 4
        assert await spending.google_requests_this_month() == 4

    asyncio.run(go())
