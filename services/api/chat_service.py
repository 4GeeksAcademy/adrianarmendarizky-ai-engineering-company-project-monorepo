"""
chat_service.py -- the engine behind the WebSocket chat (Real-Time Systems, Part 2).

It has no WebSocket code. routes/chat_ws.py takes care of sockets and calls
this. Four jobs:

  1. Pub/sub. One in-memory channel per session, named "chat.<session_id>".
     The agent's runner PUBLISHES events to it; every WebSocket connection that
     is subscribed to that session RECEIVES them. Producer and consumers never
     touch each other, so two people watching the same chat see the same
     events, each exactly once. (In-memory, so one API process; the CONTEXT
     says that is fine for this deliverable.)
  2. Running a turn. The Manager support agent graph runs in a background
     thread with stream_mode="custom"; each piece of the answer becomes a
     token_chunk event with a rising sequence number.
  3. Interrupting. interrupt_requested sets a stop flag. The next token
     callback raises, which closes the model's stream, so no more tokens are
     produced. The words already sent are saved as an "interrupted" message,
     generation_interrupted is published, and the new input starts a new turn.
  4. History. Messages are saved in chat_messages so a client that reconnects
     with the same session_id gets the whole conversation back
     (session_snapshot).

The agent itself (agent/graph.py and its tools) is not changed.
"""

import asyncio
import logging
import re
import threading
import uuid
from sqlmodel import Session, select

import database
from agent.graph import graph
from agent.guardrails import messages as guard_messages
from agent.guardrails import telemetry as guard_telemetry
from agent.guardrails import patterns as guard_patterns
from chat_models import (
    AGENT_ID, MESSAGE_COMPLETE, MESSAGE_INTERRUPTED, STATUS_ACTIVE, STATUS_CLOSED,
    STATUS_INTERRUPTED, ChatMessage, ChatSession,
)

logger = logging.getLogger(__name__)

SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]{8,64}")  # same shape POST /agent/query uses
MAX_TEXT = 4000

# Event names (Part 2 CONTEXT, section 4).
TOKEN_CHUNK = "token_chunk"
GENERATION_INTERRUPTED = "generation_interrupted"
GENERATION_COMPLETED = "generation_completed"
SESSION_SNAPSHOT = "session_snapshot"


class _Interrupted(Exception):
    """Raised inside the token callback to stop the model mid-answer."""


# --- pub/sub --------------------------------------------------------------

class ChatBus:
    """One channel per session: chat.<session_id>. publish() works from any
    thread (the agent runs in a background thread; connections live in the
    event loop), the same hand-off the Part 1 SSE broker uses."""

    def __init__(self):
        self._lock = threading.Lock()
        self._channels: dict[str, dict[asyncio.Queue, asyncio.AbstractEventLoop]] = {}

    @staticmethod
    def channel(session_id: str) -> str:
        return f"chat.{session_id}"

    def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        with self._lock:
            self._channels.setdefault(self.channel(session_id), {})[queue] = loop
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        with self._lock:
            channel = self._channels.get(self.channel(session_id))
            if channel is not None:
                channel.pop(queue, None)
                if not channel:
                    del self._channels[self.channel(session_id)]

    def subscriber_count(self, session_id: str) -> int:
        with self._lock:
            return len(self._channels.get(self.channel(session_id), {}))

    def publish(self, session_id: str, event: dict) -> None:
        with self._lock:
            targets = list(self._channels.get(self.channel(session_id), {}).items())
        for queue, loop in targets:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:
                pass  # that connection's loop is already closed


bus = ChatBus()


# --- sessions and history --------------------------------------------------------

def new_session_id() -> str:
    return uuid.uuid4().hex


def get_or_create_session(session_id: str, user_id: int, location_id: str | None) -> ChatSession | None:
    """The session for this id, created on first use. Returns None when the id
    already belongs to a different user (a chat is private to the manager who
    started it)."""
    with Session(database.engine) as db:
        session = db.get(ChatSession, session_id)
        if session is None:
            session = ChatSession(
                session_id=session_id, agent_id=AGENT_ID, user_id=user_id, location_id=location_id,
            )
            db.add(session)
            db.commit()
            db.refresh(session)
        elif session.user_id != user_id:
            return None
        return session


def _set_status(session_id: str, status: str) -> None:
    with Session(database.engine) as db:
        session = db.get(ChatSession, session_id)
        if session is not None:
            session.status = status
            db.add(session)
            db.commit()


def close_session(session_id: str) -> None:
    _set_status(session_id, STATUS_CLOSED)


def _save_message(session_id: str, role: str, text: str, status: str = MESSAGE_COMPLETE) -> str:
    message_id = f"msg_{uuid.uuid4().hex[:12]}"
    with Session(database.engine) as db:
        db.add(ChatMessage(
            message_id=message_id, session_id=session_id, role=role, text=text, status=status,
        ))
        db.commit()
    return message_id


def snapshot_event(session_id: str) -> dict:
    """The whole conversation so far: what a reconnecting client is sent."""
    with Session(database.engine) as db:
        rows = db.exec(
            select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
        ).all()
        session = db.get(ChatSession, session_id)
        status = session.status if session is not None else STATUS_ACTIVE
        return {
            "event": SESSION_SNAPSHOT,
            "data": {
                "session_id": session_id,
                "status": status,
                # True while an answer is being written right now. A client that reconnects
                # uses this to know whether to wait for one or to go back to normal.
                "generating": is_generating(session_id),
                "messages": [
                    {
                        "message_id": row.message_id, "role": row.role, "text": row.text,
                        "status": row.status, "created_at": row.created_at.isoformat() + "Z",
                    }
                    for row in rows
                ],
            },
        }


# --- running a turn ------------------------------------------------------------

class _Turn:
    """One answer being generated for one session."""

    def __init__(self):
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None


_turns: dict[str, _Turn] = {}
_turns_lock = threading.Lock()


def is_generating(session_id: str) -> bool:
    with _turns_lock:
        turn = _turns.get(session_id)
        return turn is not None and turn.thread is not None and turn.thread.is_alive()


def _publish_chunk(session_id: str, token: str, sequence: int) -> None:
    bus.publish(session_id, {
        "event": TOKEN_CHUNK,
        "data": {"session_id": session_id, "token": token, "sequence": sequence},
    })


def _run_turn(session_id: str, question: str, user_id: int, is_memory_user: bool, turn: _Turn) -> None:
    """Runs in a background thread: streams the graph's answer, then saves it."""
    streamed: list[str] = []
    sequence = 0
    final_answer: str | None = None
    language = guard_patterns.guess_language(question)

    graph_input: dict = {"question": question}
    if is_memory_user:
        graph_input |= {"user_id": str(user_id), "session_id": session_id}
    # The session id is also the LangGraph thread id (Part 2 CONTEXT, section 3).
    config = {"configurable": {"thread_id": session_id, "stream_tokens": True}}

    try:
        for mode, payload in graph.stream(graph_input, config, stream_mode=["custom", "values"]):
            if mode == "values":
                final_answer = payload.get("answer") or final_answer
                continue
            token = payload.get("token", "")
            if not token:
                continue
            if turn.stop.is_set():
                raise _Interrupted()
            # The output guard on the live text: same check the graph's last step runs.
            live = "".join(streamed) + token
            # An answer that has only just started can be empty or just a newline. That is
            # not a reason to block it, so the "empty_answer" rule is left to the graph's
            # own output guard, which sees the finished answer.
            reasons = [r for r in guard_patterns.check_output(live) if r != "empty_answer"]
            if reasons:
                logger.warning("chat output blocked (session_id=%s): %s", session_id, reasons)
                for reason in reasons:
                    try:
                        guard_telemetry.log_event("content", reason)
                    except Exception:
                        logger.exception("could not log the guardrail event")
                blocked = guard_messages.say("output_blocked", language)
                final_answer = blocked
                streamed_text = "".join(streamed)
                bus.publish(session_id, {
                    "event": "output_blocked",
                    "data": {"session_id": session_id, "replacement": blocked},
                })
                _finish_completed(session_id, blocked, streamed_text)
                return
            streamed.append(token)
            sequence += 1
            _publish_chunk(session_id, token, sequence)
    except _Interrupted:
        _finish_interrupted(session_id, "".join(streamed))
        return
    except Exception:
        # The real error is logged by the graph; the client only gets a short message.
        import logging
        logging.getLogger(__name__).exception("chat turn failed (session_id=%s)", session_id)
        bus.publish(session_id, {
            "event": "generation_failed",
            "data": {"session_id": session_id, "message": "The agent could not complete this request."},
        })
        _set_status(session_id, STATUS_ACTIVE)
        return

    if turn.stop.is_set():  # interrupted after the last token, before we finished
        _finish_interrupted(session_id, "".join(streamed))
        return

    streamed_text = "".join(streamed)
    answer = final_answer if final_answer is not None else streamed_text
    # The graph's last steps can add text after the streamed part (for example a
    # memory message); send what was not streamed so the chat shows the full answer.
    if answer.startswith(streamed_text) and len(answer) > len(streamed_text):
        sequence += 1
        _publish_chunk(session_id, answer[len(streamed_text):], sequence)
    _finish_completed(session_id, answer, streamed_text)


def _finish_completed(session_id: str, answer: str, streamed_text: str) -> None:
    message_id = _save_message(session_id, "assistant", answer[:MAX_TEXT], MESSAGE_COMPLETE)
    _set_status(session_id, STATUS_ACTIVE)
    bus.publish(session_id, {
        "event": GENERATION_COMPLETED,
        "data": {"session_id": session_id, "message_id": message_id},
    })


def _finish_interrupted(session_id: str, partial: str) -> None:
    message_id = _save_message(session_id, "assistant", partial[:MAX_TEXT], MESSAGE_INTERRUPTED)
    _set_status(session_id, STATUS_INTERRUPTED)
    bus.publish(session_id, {
        "event": GENERATION_INTERRUPTED,
        "data": {"session_id": session_id, "message_id": message_id, "status": "interrupted"},
    })


def start_turn(session_id: str, text: str, user_id: int, is_memory_user: bool) -> bool:
    """A new user message. Saves it and starts answering in the background.
    Returns False when the session is already answering (the client should
    interrupt first)."""
    text = text.strip()[:MAX_TEXT]
    if not text:
        return False
    with _turns_lock:
        current = _turns.get(session_id)
        if current is not None and current.thread is not None and current.thread.is_alive():
            return False
        turn = _Turn()
        _turns[session_id] = turn
    _save_message(session_id, "user", text)
    _set_status(session_id, STATUS_ACTIVE)
    turn.thread = threading.Thread(
        target=_run_turn, args=(session_id, text, user_id, is_memory_user, turn), daemon=True,
    )
    turn.thread.start()
    return True


def request_interrupt(session_id: str, new_input: str, user_id: int, is_memory_user: bool,
                      wait_seconds: float = 15.0) -> bool:
    """Stop the answer in progress, then answer new_input as a new turn.

    Blocks until the old turn has stopped (use from a worker thread, not the
    event loop). Returns False when there was nothing to interrupt."""
    with _turns_lock:
        turn = _turns.get(session_id)
    if turn is None or turn.thread is None or not turn.thread.is_alive():
        return False
    turn.stop.set()
    turn.thread.join(timeout=wait_seconds)
    if turn.thread.is_alive():
        return False
    if new_input.strip():
        start_turn(session_id, new_input, user_id, is_memory_user)
    return True
