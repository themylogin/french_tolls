# -*- coding=utf-8 -*-
"""Buy the answers the suite replays. Spends real money; run it deliberately.

    docker compose run --rm recorder

It drives each pinned journey through the same `Chat` the suite drives, so what
it records is exactly what the suite will ask -- the same handlers, the same
waypoints, the same order. A recorder that built its own requests could record
answers to questions the suite never asks and miss the ones it does.

`refine._ask_google` is wrapped rather than proxied. This is the one place where
patching is right: it is a tool, not the suite, and what it needs is to see the
body and the answer of a request it wants really sent.
"""
import asyncio
import json
import os
import sys

from .. import refine
from ..config import config
from ..refine import ROUTING_PREFERENCE
from .chat import Chat
from .google_replay import key_of
from .journeys import JOURNEYS

CASSETTES = os.environ.get(
    "GOOGLE_CASSETTES", os.path.join(os.path.dirname(__file__), "cassettes"))

# A journey that asks more than this has stopped being the journey that was
# pinned, and buying a runaway cascade is not what this is for.
PER_JOURNEY_CAP = 16


class Recorder:
    """Wraps the one paid call and keeps what it bought."""

    def __init__(self):
        self.calls = []
        self._real = refine._ask_google

    def __enter__(self):
        refine._ask_google = self._record
        return self

    def __exit__(self, *_exc):
        refine._ask_google = self._real
        return False

    async def _record(self, session, body):
        if len(self.calls) >= PER_JOURNEY_CAP:
            raise RuntimeError(
                f"{PER_JOURNEY_CAP} requests for one journey; refusing to buy more")
        answer = await self._real(session, body)
        self.calls.append({"key": key_of(body), "body": body, "response": answer})
        return answer


async def record(journey):
    os.makedirs(CASSETTES, exist_ok=True)
    with Recorder() as recorder:
        async with Chat() as chat:
            await chat.drive(journey.origin, journey.destination, choice=journey.choice)
        parts = len(chat.parts)

    path = os.path.join(CASSETTES, f"{journey.key}.json")
    with open(path, "w") as f:
        json.dump({
            "key": journey.key,
            "outcome": journey.outcome,
            "from": journey.origin_name,
            "to": journey.destination_name,
            "preference": ROUTING_PREFERENCE,
            "calls": recorder.calls,
        }, f, indent=1)

    flag = "" if (len(recorder.calls), parts) == (journey.asks, journey.parts) else \
        f"   <<< expected {journey.asks} ask(s) and {journey.parts} part(s)"
    print(f"  {journey.key:<26} {len(recorder.calls)} ask(s), {parts} part(s)"
          f" -> {os.path.basename(path)}{flag}")
    return len(recorder.calls)


async def main(keys):
    if config.google_routes_endpoint.startswith(("http://127.0.0.1", "http://localhost")):
        raise SystemExit(
            "GOOGLE_ROUTES_ENDPOINT points at the replay server, so there is "
            "nothing to record. Unset it to buy real answers.")

    wanted = [j for j in JOURNEYS if not keys or j.key in keys]
    print(f"recording {len(wanted)} journey(s) at {ROUTING_PREFERENCE}\n")
    spent = 0
    for journey in wanted:
        spent += await record(journey)
    print(f"\n{spent} paid request(s) spent")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
