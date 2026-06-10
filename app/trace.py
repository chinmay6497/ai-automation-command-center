"""In-process pub/sub bus so the UI can watch agent reasoning live over SSE."""
import asyncio
import json
from collections import defaultdict

from . import db


class TraceBus:
    """Fan-out of trace events: persisted to SQLite and pushed to any live SSE subscribers."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        # "*" channel receives every event (used by the global activity feed)

    def subscribe(self, item_id: str = "*") -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers[item_id].append(q)
        return q

    def unsubscribe(self, item_id: str, q: asyncio.Queue) -> None:
        try:
            self._subscribers[item_id].remove(q)
        except ValueError:
            pass

    def emit(self, item_id: str, agent: str, title: str, detail: str = "") -> None:
        event = db.add_trace(item_id, agent, title, detail)
        payload = json.dumps(event)
        for channel in (item_id, "*"):
            for q in self._subscribers.get(channel, []):
                q.put_nowait(payload)

    def done(self, item_id: str) -> None:
        for channel in (item_id, "*"):
            for q in self._subscribers.get(channel, []):
                q.put_nowait(json.dumps({"item_id": item_id, "type": "done"}))


bus = TraceBus()
