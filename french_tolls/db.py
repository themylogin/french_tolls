# -*- coding=utf-8 -*-
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

__all__ = ["Session"]

engine = create_async_engine("sqlite+aiosqlite:////cache/database.db")


@event.listens_for(engine.sync_engine, "connect")
def _wal(connection, _record):
    cursor = connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


Session = async_sessionmaker(engine, expire_on_commit=False)
