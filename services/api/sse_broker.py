"""
sse_broker.py -- hands out "new RFP ticket" messages to every connected
dashboard (Real-Time Systems, Part 1).

Each browser that opens the SSE stream gets its own queue. publish() puts the
message in every queue, and each connection's stream picks it up from its own.

publish() can be called from ANY thread. The RFP pipeline runs in a background
thread, but each queue belongs to the event loop that serves its connection,
and asyncio queues are not safe to touch from another thread. So publish()
asks each connection's loop to do the put (call_soon_threadsafe).
"""

import asyncio
import threading


class RfpTicketBroker:
    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers: dict[asyncio.Queue, asyncio.AbstractEventLoop | None] = {}

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None  # not called from inside an event loop (some tests)
        with self._lock:
            self._subscribers[queue] = loop
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.pop(queue, None)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    @staticmethod
    def _put(queue: asyncio.Queue, message: dict) -> None:
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            # A client that stopped reading. It is not worth blocking
            # everyone else; it will catch up when it reconnects.
            pass

    def publish(self, message: dict) -> None:
        with self._lock:
            targets = list(self._subscribers.items())
        for queue, loop in targets:
            if loop is None:
                self._put(queue, message)
                continue
            try:
                loop.call_soon_threadsafe(self._put, queue, message)
            except RuntimeError:
                pass  # that connection's event loop is already closed


broker = RfpTicketBroker()
