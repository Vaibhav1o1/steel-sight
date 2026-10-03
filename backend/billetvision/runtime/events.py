from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventBus:
    """A thread-safe publisher for WebSocket messages."""

    def __init__(self) -> None:
        # We hold queues or callbacks here.
        # Since the WebSocket router isn't built yet, we'll just allow
        # basic async queue registration.
        self._queues: list[asyncio.Queue[dict[str, Any]]] = []

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Subscribe to events."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        if q in self._queues:
            self._queues.remove(q)

    def publish(self, event: dict[str, Any], loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Publish an event to all subscribers."""
        if not self._queues:
            return

        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

        for q in self._queues:
            if loop and loop.is_running():
                loop.call_soon_threadsafe(q.put_nowait, event)
            else:
                # If no loop is running, we just put_nowait (for tests)
                q.put_nowait(event)
