"""
chat_models.py -- tables for the WebSocket chat (Real-Time Systems, Part 2).

ChatSession follows the Part 2 CONTEXT: session_id, agent_id, user_id,
location_id, status (active / interrupted / closed), created_at. The
session_id is the same conversation id POST /agent/query already uses
(8-64 letters, digits, - or _), and it is also the LangGraph thread_id for
the chat's runs.

ChatMessage keeps the conversation history, one row per message, so a
reconnecting client can get the whole thread back (the session_snapshot
event). An assistant message that was cut short is saved with status
"interrupted" and keeps the words that had already been sent.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel

STATUS_ACTIVE = "active"
STATUS_INTERRUPTED = "interrupted"
STATUS_CLOSED = "closed"

MESSAGE_COMPLETE = "complete"
MESSAGE_INTERRUPTED = "interrupted"

AGENT_ID = "manager_support"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_sessions"

    session_id: str = Field(primary_key=True)
    agent_id: str = Field(default=AGENT_ID)
    user_id: int = Field(index=True)  # the manager chatting (users.id)
    location_id: Optional[str] = None  # e.g. "medellin_downtown"; optional, sent by the client
    status: str = Field(default=STATUS_ACTIVE)
    created_at: datetime = Field(default_factory=_now)


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: Optional[int] = Field(default=None, primary_key=True)  # keeps the order
    message_id: str = Field(index=True)  # e.g. "msg_3f9a1c..."
    session_id: str = Field(foreign_key="chat_sessions.session_id", index=True)
    role: str  # "user" or "assistant"
    text: str = ""
    status: str = Field(default=MESSAGE_COMPLETE)  # "complete" or "interrupted"
    created_at: datetime = Field(default_factory=_now)
