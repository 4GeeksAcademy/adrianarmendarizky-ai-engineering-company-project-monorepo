"""
sse_broker.py -- hands out "new RFP ticket" messages to every connected
dashboard (Real-Time Systems, Part 1).

Each browser that opens the SSE stream gets its own queue. When a ticket
is registered, publish() puts the message in every queue, and each
connection's stream picks it up from its own queue.
"""

import asyncio


class RfpTicketBroker:
    def __init__(self):
        self._queues: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._queues.discard(queue)

    def publish(self, message: dict) -> None:
        for queue in list(self._queues):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # A client that stopped reading. It is not worth blocking
                # everyone else; it will catch up when it reconnects.
                pass


broker = RfpTicketBroker()
