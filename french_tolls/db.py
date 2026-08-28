# -*- coding=utf-8 -*-
"""The one store: cached answers, refinements, autocomplete, and what was spent.

Four tables in one SQLite file rather than a mixture of JSON files and a
separate database. The count of what has been spent has to be transactional
against the record of what the money bought — two stores cannot be made to agree
about that — and one store is also one thing to find, to inspect, and to back up.

The calls here block, and this is an async application. They are milliseconds
against a route search of hundreds of them, so they run inline. If the service
ever becomes busy enough for that to matter, the fix is to put them behind
`loop.run_in_executor`; nothing else about this module would change.
"""
from contextlib import contextmanager
import datetime
import json
import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

__all__ = [
    "connect",
    "current_month",
    "path",
    "read_answer",
    "read_refinement",
    "reserve_google_request",
    "requests_this_month",
    "write_answer",
    "write_refinement",
]

CACHE_DIR = os.environ.get("CACHE_DIR", "/cache")
DB_NAME = "database.db"

# What this file was called when it held nothing but the autocomplete cache.
# Renamed on first open, keeping its rows: the answers in it cost a paid
# LocationIQ request each.
LEGACY_NAME = "autocomplete.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS autocomplete (
    q        TEXT PRIMARY KEY,
    response TEXT NOT NULL
);

-- One row per calendar month. Incremented before each paid Google request, so
-- it can overstate and never understate: a request that failed has still been
-- made and may still have been billed.
CREATE TABLE IF NOT EXISTS google_requests (
    year_month TEXT PRIMARY KEY,
    count      INTEGER NOT NULL DEFAULT 0
);

-- A computed journey, keyed by the two points and nothing else. A rebuilt
-- pipeline is therefore a hit rather than a miss, and the cache has to be
-- purged by hand after one. Nothing here detects a stale answer, and a stale
-- toll total looks exactly like a correct one.
CREATE TABLE IF NOT EXISTS routes (
    from_lon    REAL NOT NULL,
    from_lat    REAL NOT NULL,
    to_lon      REAL NOT NULL,
    to_lat      REAL NOT NULL,
    answer      TEXT NOT NULL,
    stored_at   TEXT NOT NULL,
    PRIMARY KEY (from_lon, from_lat, to_lon, to_lat)
);

-- What Google said about a journey, bought once. Same key as the answer: a
-- refinement describes a particular optimal route, so it is stale exactly when
-- that route is, and the two are purged together.
CREATE TABLE IF NOT EXISTS refinements (
    from_lon    REAL NOT NULL,
    from_lat    REAL NOT NULL,
    to_lon      REAL NOT NULL,
    to_lat      REAL NOT NULL,
    refinement  TEXT NOT NULL,
    stored_at   TEXT NOT NULL,
    PRIMARY KEY (from_lon, from_lat, to_lon, to_lat)
);
"""

_initialised = False


def path():
    return os.path.join(CACHE_DIR, DB_NAME)


def _rename_legacy():
    """Carry the autocomplete cache over to the new name, once."""
    legacy = os.path.join(CACHE_DIR, LEGACY_NAME)
    target = path()
    if os.path.exists(legacy) and not os.path.exists(target):
        os.replace(legacy, target)
        logger.info("renamed %s to %s, keeping its rows", legacy, target)
        # SQLite's side files belong to the database, not to the name.
        for suffix in ("-wal", "-shm"):
            if os.path.exists(legacy + suffix):
                os.replace(legacy + suffix, target + suffix)


def _adopt_legacy_table(connection):
    """Move the old autocomplete rows into the table this now reads.

    The file used to hold one table called `cache`. Renaming the file keeps
    those rows on disk but out of reach, and each of them cost a paid LocationIQ
    request, so they are carried across rather than abandoned.
    """
    legacy = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cache'").fetchone()
    if not legacy:
        return

    moved = connection.execute(
        "INSERT OR IGNORE INTO autocomplete (q, response) SELECT q, response FROM cache"
    ).rowcount
    connection.execute("DROP TABLE cache")
    logger.info("carried %d autocomplete rows over from the legacy table", moved)


def _drop_fingerprinted(connection):
    """Drop the two cache tables that were keyed by a data fingerprint.

    `CREATE TABLE IF NOT EXISTS` will not alter a table that is already there, so
    a database written under the old schema would keep a column the statements
    below do not mention: every read would miss and every write would fail on it.

    Dropped rather than migrated. Collapsing several fingerprints of one journey
    to one row needs a rule for which survives, and the code to apply it runs
    once and is read forever. The cost is the refinements, which were paid for;
    they are bought again lazily, within the ceiling that already bounds
    spending.

    The condition is false ever after, so this happens once without a version
    table to carry.
    """
    for table in ("routes", "refinements"):
        columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
        if any(c[1] == "fingerprint" for c in columns):
            connection.execute(f"DROP TABLE {table}")
            logger.info("dropped %s: it was keyed by a data fingerprint", table)


@contextmanager
def connect():
    """A connection to the store, with the schema in place."""
    global _initialised

    os.makedirs(CACHE_DIR, exist_ok=True)
    if not _initialised:
        _rename_legacy()

    connection = sqlite3.connect(path(), timeout=30.0)
    try:
        if not _initialised:
            # WAL so a reader and a writer do not block one another: the redirect
            # and the API can both be in flight, and the evaluation may be
            # reading at the same time.
            connection.execute("PRAGMA journal_mode=WAL")
            # Before the schema: the two cache tables have to be gone by the time
            # the `CREATE TABLE IF NOT EXISTS` below would decline to change them.
            _drop_fingerprinted(connection)
            connection.executescript(SCHEMA)
            _adopt_legacy_table(connection)
            connection.commit()
            _initialised = True
        yield connection
    finally:
        connection.close()


def current_month():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _key(from_, to):
    return (float(from_[0]), float(from_[1]), float(to[0]), float(to[1]))


def read_answer(from_, to):
    with connect() as c:
        row = c.execute(
            "SELECT answer FROM routes WHERE from_lon=? AND from_lat=? "
            "AND to_lon=? AND to_lat=?", _key(from_, to)).fetchone()
    return json.loads(row[0]) if row else None


def write_answer(from_, to, answer):
    try:
        with connect() as c:
            c.execute(
                "INSERT OR REPLACE INTO routes "
                "(from_lon, from_lat, to_lon, to_lat, answer, stored_at) "
                "VALUES (?,?,?,?,?,?)", (*_key(from_, to),
                                         json.dumps(answer), _now()))
            c.commit()
    except sqlite3.Error as e:
        # A cache that cannot be written is not a failed journey.
        logger.warning("could not store answer: %s", e)


def read_refinement(from_, to):
    with connect() as c:
        row = c.execute(
            "SELECT refinement FROM refinements WHERE from_lon=? "
            "AND from_lat=? AND to_lon=? AND to_lat=?", _key(from_, to)).fetchone()
    return json.loads(row[0]) if row else None


def write_refinement(from_, to, refinement):
    try:
        with connect() as c:
            c.execute(
                "INSERT OR REPLACE INTO refinements "
                "(from_lon, from_lat, to_lon, to_lat, refinement, stored_at) "
                "VALUES (?,?,?,?,?,?)", (*_key(from_, to),
                                         json.dumps(refinement), _now()))
            c.commit()
    except sqlite3.Error as e:
        logger.warning("could not store refinement: %s", e)


def requests_this_month():
    with connect() as c:
        row = c.execute("SELECT count FROM google_requests WHERE year_month=?",
                        (current_month(),)).fetchone()
    return row[0] if row else 0


def reserve_google_request(ceiling):
    """Claim one paid request against this month, or refuse.

    Returns True when the caller may make the request. The increment is
    committed here, before the request is issued, so a request whose answer
    never arrives is still counted: it has been made, and may still have been
    billed.

    The read and the write are one immediate transaction, so two journeys
    answered at once cannot both see the same value and write it back.
    """
    if ceiling <= 0:
        return False

    with connect() as c:
        try:
            c.execute("BEGIN IMMEDIATE")
            month = current_month()
            row = c.execute("SELECT count FROM google_requests WHERE year_month=?",
                            (month,)).fetchone()
            used = row[0] if row else 0
            if used >= ceiling:
                c.rollback()
                return False

            c.execute(
                "INSERT INTO google_requests (year_month, count) VALUES (?, 1) "
                "ON CONFLICT(year_month) DO UPDATE SET count = count + 1", (month,))
            c.commit()
            return True
        except sqlite3.Error as e:
            c.rollback()
            logger.warning("could not reserve a google request: %s", e)
            return False
