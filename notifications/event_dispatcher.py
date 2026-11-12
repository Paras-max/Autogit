"""
In-process event dispatcher and live pub/sub hub for AutoGit AI (Phase 4).
Broadcasts real-time events to Server-Sent Event (SSE) and WebSocket subscribers.
"""

import asyncio
from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Set
from utils.logger import logger


class EventDispatcher:
    """Pub/sub event dispatcher supporting real-time streaming."""

    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._event_counter = 0

    async def subscribe(self) -> asyncio.Queue:
        """Subscribe to the live event stream."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(q)
            logger.debug(f"New event subscriber registered. Total subscribers: {len(self._subscribers)}")
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        """Unsubscribe queue from event stream."""
        async with self._lock:
            self._subscribers.discard(q)
            logger.debug(f"Event subscriber removed. Total subscribers: {len(self._subscribers)}")

    def dispatch(
        self,
        event_type: str,
        data: Dict[str, Any],
        repository_id: Any = None,
    ) -> None:
        """
        Synchronous helper to dispatch an event across all active subscriber queues.
        Safe to call from anywhere (threads, sync endpoints, event loops).
        """
        self._event_counter += 1
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "id": self._event_counter,
            "event": event_type,
            "repository_id": repository_id,
            "timestamp": now_iso,
            "data": data,
        }

        # Try to dispatch in current event loop or schedule threadsafe
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast(payload))
        except RuntimeError:
            # No running event loop in current thread
            pass

    async def dispatch_async(
        self,
        event_type: str,
        data: Dict[str, Any],
        repository_id: Any = None,
    ) -> None:
        """Async dispatch method."""
        self._event_counter += 1
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "id": self._event_counter,
            "event": event_type,
            "repository_id": repository_id,
            "timestamp": now_iso,
            "data": data,
        }
        await self._broadcast(payload)

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        """Broadcast payload to all subscribed queues."""
        async with self._lock:
            dead_queues = []
            for q in self._subscribers:
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    # Drop oldest or mark dead
                    try:
                        q.get_nowait()
                        q.put_nowait(payload)
                    except Exception:
                        dead_queues.append(q)
            for dq in dead_queues:
                self._subscribers.discard(dq)


# Global singleton instance
event_dispatcher = EventDispatcher()

