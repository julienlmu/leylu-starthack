"""Fan-out of events to every open SSE connection (`GET /api/stream`)."""

import asyncio
import json
from collections.abc import AsyncIterator

PING_SECONDS = 15


class Broadcaster:
    def __init__(self) -> None:
        self.queues: set[asyncio.Queue] = set()

    def publish(self, event: dict) -> None:
        for q in list(self.queues):
            q.put_nowait(event)

    async def sse(self, ping_s: float = PING_SECONDS) -> AsyncIterator[str]:
        """One `data: <Event JSON>` message per event, and a `: ping` comment when idle."""
        q: asyncio.Queue = asyncio.Queue()
        self.queues.add(q)
        try:
            yield ": connected\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=ping_s)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            self.queues.discard(q)
