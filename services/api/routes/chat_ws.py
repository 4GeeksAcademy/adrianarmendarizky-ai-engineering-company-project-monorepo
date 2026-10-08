"""
routes/chat_ws.py -- WebSocket chat with the Manager support agent
(Real-Time Systems, Part 2).

  WS /ws/chat/{session_id}?token=<jwt>[&location_id=<id>]

Same JWT as the rest of the backoffice API, sent as ?token= (a browser's
WebSocket cannot set an Authorization header). It is checked BEFORE any chat
event: a missing or bad token closes the socket (code 1008) right away.

The session_id names a conversation. The first time it is used the session is
created for that manager; after that only that manager can join it. On every
connect the server first sends a session_snapshot with the whole conversation
so far, so a reconnect restores the thread instead of starting empty.

Messages the browser sends (JSON, {"event": ..., "data": {...}}):
  user_message         {"text": "..."}                a new question
  interrupt_requested  {"new_input": "..."}           stop the answer, ask this instead

Events the server sends: session_snapshot, token_chunk, generation_interrupted,
generation_completed (see chat_service.py for the rest).

This file only handles the socket. The agent, the pub/sub and the history live
in chat_service.py; the agent itself is unchanged.
"""

import asyncio
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError

import chat_service
import user_service as svc
from security import decode_access_token
from user_models import Role

router = APIRouter(tags=["chat"])

POLICY_VIOLATION = 1008  # the standard WebSocket close code for "not allowed"
MEMORY_ROLES = (Role.MANAGER, Role.ADMIN)  # same rule as routes/agent.py


def _user_from_token(token: str | None):
    """The same checks get_current_user runs for an HTTP request, plus is_active."""
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except JWTError:
        return None
    user_id = payload.get("sub")
    if user_id is None:
        return None
    user = svc.get_user_by_id(int(user_id))
    if user is None or not user.is_active:
        return None
    return user


async def _send_events(websocket: WebSocket, queue: asyncio.Queue) -> None:
    """Everything published on this session's channel goes to this browser."""
    while True:
        event = await queue.get()
        await websocket.send_text(json.dumps(event))


async def _send_error(websocket: WebSocket, message: str) -> None:
    await websocket.send_text(json.dumps({"event": "error", "data": {"message": message}}))


@router.websocket("/ws/chat/{session_id}")
async def chat_socket(
    websocket: WebSocket,
    session_id: str,
    token: str | None = Query(default=None),
    location_id: str | None = Query(default=None),
):
    # 1. Login, before any chat event. (accept first, then close with a code,
    #    so the browser can read the close code.)
    await websocket.accept()
    user = _user_from_token(token)
    if user is None:
        await websocket.close(code=POLICY_VIOLATION, reason="unauthorized")
        return

    # 2. The conversation: a valid id, and one that belongs to this manager.
    if not chat_service.SESSION_ID_RE.fullmatch(session_id):
        await websocket.close(code=POLICY_VIOLATION, reason="invalid session_id")
        return
    session = await asyncio.to_thread(
        chat_service.get_or_create_session, session_id, user.id, location_id
    )
    if session is None:
        await websocket.close(code=POLICY_VIOLATION, reason="session belongs to another user")
        return

    is_memory_user = user.role in MEMORY_ROLES

    # 3. Subscribe BEFORE sending the snapshot, so nothing published in between is lost.
    queue = chat_service.bus.subscribe(session_id)
    sender = asyncio.create_task(_send_events(websocket, queue))
    try:
        snapshot = await asyncio.to_thread(chat_service.snapshot_event, session_id)
        await websocket.send_text(json.dumps(snapshot))

        # 4. What the browser sends.
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
                event = message["event"]
                data = message.get("data") or {}
            except (ValueError, KeyError, TypeError):
                await _send_error(websocket, "Messages must be JSON like {\"event\": ..., \"data\": {...}}.")
                continue

            if event == "user_message":
                text = str(data.get("text", ""))
                started = await asyncio.to_thread(
                    chat_service.start_turn, session_id, text, user.id, is_memory_user
                )
                if not started:
                    await _send_error(
                        websocket, "Nothing to send, or the agent is still answering. Interrupt it first."
                    )
            elif event == "interrupt_requested":
                new_input = str(data.get("new_input", ""))
                stopped = await asyncio.to_thread(
                    chat_service.request_interrupt, session_id, new_input, user.id, is_memory_user
                )
                if not stopped:
                    await _send_error(websocket, "There is no answer in progress to interrupt.")
            else:
                await _send_error(websocket, f"Unknown event: {event!r}")
    except WebSocketDisconnect:
        pass  # the browser went away; a running answer carries on and is saved
    finally:
        sender.cancel()
        chat_service.bus.unsubscribe(session_id, queue)
