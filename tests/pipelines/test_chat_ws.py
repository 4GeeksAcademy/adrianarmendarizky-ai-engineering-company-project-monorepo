"""
tests/pipelines/test_chat_ws.py -- tests for the WebSocket chat
(services/api/routes/chat_ws.py, services/api/chat_service.py).

Nothing real is touched: the database is a throwaway in-memory SQLite and the
agent graph is replaced by a small fake that streams a few words, so no model
and no Qdrant are needed. The login is the real JWT check.
"""

import os
import sys
import threading
import time
from pathlib import Path

import pytest

# security.py reads these the moment it is imported (see main.py's comment).
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel, create_engine  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

import chat_service  # noqa: E402
import database  # noqa: E402
import routes.chat_ws as chat_ws  # noqa: E402
from security import create_access_token  # noqa: E402
from user_models import Role, User  # noqa: E402

SESSION = "session_abc12345"


class FakeUser(User):
    pass


def make_user(user_id=1, role=Role.MANAGER, active=True):
    return User(
        id=user_id, email=f"u{user_id}@brasaland.test", hashed_password="x",
        is_active=active, role=role, created_at="2026-01-01T00:00:00",
    )


@pytest.fixture()
def users(monkeypatch):
    """The user lookup the login check uses: three known users."""
    table = {1: make_user(1), 2: make_user(2), 3: make_user(3, active=False)}
    monkeypatch.setattr(chat_ws.svc, "get_user_by_id", lambda uid: table.get(uid))
    return table


@pytest.fixture()
def engine(monkeypatch, tmp_path):
    # A real file, so every database session gets its own connection, like in production.
    # (One shared in-memory connection used by two threads at once is what broke before.)
    engine = create_engine(
        f"sqlite:///{tmp_path / 'chat.db'}", connect_args={"check_same_thread": False}
    )
    import chat_models  # noqa: F401  (registers the tables)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    return engine


class FakeGraph:
    """Stands in for the agent graph: streams WORDS one at a time, slowly enough
    that a test can interrupt in the middle, then reports the final answer."""

    def __init__(self, words=("alpha ", "beta ", "gamma ", "delta ", "epsilon ", "zeta "), delay=0.05):
        self.words = words
        self.delay = delay
        self.questions = []

    def stream(self, graph_input, config, stream_mode):
        self.questions.append(graph_input["question"])
        assert config["configurable"]["thread_id"]  # the session id is the thread id
        assert config["configurable"]["stream_tokens"] is True
        question = graph_input["question"]
        words = self.words if "slow" in question else ("short ", "answer ")
        spoken = ""
        for word in words:
            time.sleep(self.delay)
            spoken += word
            yield "custom", {"token": word}
        yield "values", {"answer": spoken.strip()}


@pytest.fixture()
def fake_graph(monkeypatch):
    fake = FakeGraph()
    monkeypatch.setattr(chat_service, "graph", fake)
    return fake


@pytest.fixture()
def client(engine, users, fake_graph):
    app = FastAPI()
    app.include_router(chat_ws.router)
    return TestClient(app)


def token_for(user_id=1):
    return create_access_token(user_id=user_id)


def url(session=SESSION, token=None, extra=""):
    token = token if token is not None else token_for()
    return f"/ws/chat/{session}?token={token}{extra}"


def send(ws, event, data):
    ws.send_json({"event": event, "data": data})


def receive_until(ws, names, limit=60):
    """Collect events until one named in `names` arrives; returns them all."""
    seen = []
    for _ in range(limit):
        event = ws.receive_json()
        seen.append(event)
        if event["event"] in names:
            return seen
    raise AssertionError(f"never saw {names}; got {[e['event'] for e in seen]}")


# --- login ----------------------------------------------------------------

@pytest.mark.parametrize("token", [None, "", "not-a-token"])
def test_a_missing_or_bad_token_is_rejected_before_any_chat_event(client, token):
    path = f"/ws/chat/{SESSION}" + ("" if token is None else f"?token={token}")
    with client.websocket_connect(path) as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 1008


def test_a_token_for_a_deleted_or_inactive_user_is_rejected(client):
    for user_id in (3, 99):  # 3 is inactive, 99 does not exist
        with client.websocket_connect(url(token=token_for(user_id))) as ws:
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
        assert closed.value.code == 1008


def test_a_badly_shaped_session_id_is_rejected(client):
    with client.websocket_connect(url(session="short")) as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 1008


def test_another_users_session_cannot_be_joined(client):
    with client.websocket_connect(url()) as ws:
        ws.receive_json()  # user 1 owns the session now
    with client.websocket_connect(url(token=token_for(2))) as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 1008


# --- the event contract ------------------------------------------------------

def test_a_question_streams_token_chunks_then_generation_completed(client):
    with client.websocket_connect(url()) as ws:
        first = ws.receive_json()
        assert first["event"] == "session_snapshot"
        assert first["data"] == {
            "session_id": SESSION, "status": "active", "generating": False, "messages": [],
        }

        send(ws, "user_message", {"text": "hello"})
        events = receive_until(ws, {"generation_completed"})

    chunks = [e for e in events if e["event"] == "token_chunk"]
    assert [c["data"]["token"] for c in chunks] == ["short ", "answer "]
    assert [c["data"]["sequence"] for c in chunks] == [1, 2]  # rising sequence numbers
    assert all(c["data"]["session_id"] == SESSION for c in chunks)
    done = events[-1]
    assert done["event"] == "generation_completed"
    assert done["data"]["session_id"] == SESSION
    assert done["data"]["message_id"].startswith("msg_")


def test_unknown_events_and_bad_json_get_an_error_not_a_crash(client):
    with client.websocket_connect(url()) as ws:
        ws.receive_json()
        send(ws, "nonsense", {})
        assert ws.receive_json()["event"] == "error"
        ws.send_text("this is not json")
        assert ws.receive_json()["event"] == "error"


# --- interrupting -----------------------------------------------------------------

def test_interrupt_stops_the_old_answer_marks_it_interrupted_and_starts_a_new_turn(client, fake_graph):
    with client.websocket_connect(url()) as ws:
        ws.receive_json()
        send(ws, "user_message", {"text": "slow question"})
        first_chunk = receive_until(ws, {"token_chunk"})[-1]
        assert first_chunk["data"]["sequence"] == 1

        send(ws, "interrupt_requested", {"new_input": "quick question"})
        events = receive_until(ws, {"generation_completed"})

        # reconnect to read the saved thread
    with client.websocket_connect(url()) as ws:
        snapshot = ws.receive_json()

    names = [e["event"] for e in events]
    assert "generation_interrupted" in names
    interrupted = next(e for e in events if e["event"] == "generation_interrupted")
    assert interrupted["data"]["status"] == "interrupted"

    # No token from the OLD answer after the interruption: only the new turn's two chunks.
    after = names[names.index("generation_interrupted") + 1:]
    new_tokens = [e["data"]["token"] for e in events if e["event"] == "token_chunk"
                  and events.index(e) > names.index("generation_interrupted")]
    assert new_tokens == ["short ", "answer "]
    assert after[-1] == "generation_completed"

    # The next response is a new turn that reflects the new input.
    assert fake_graph.questions == ["slow question", "quick question"]

    messages = snapshot["data"]["messages"]
    assert [(m["role"], m["status"]) for m in messages] == [
        ("user", "complete"), ("assistant", "interrupted"),
        ("user", "complete"), ("assistant", "complete"),
    ]
    assert messages[1]["text"].strip() != ""  # the partial message was kept
    assert len(messages[1]["text"]) < len("alpha beta gamma delta epsilon zeta ")  # and it is partial
    assert messages[3]["text"] == "short answer"


def test_interrupting_with_nothing_running_is_an_error_message(client):
    with client.websocket_connect(url()) as ws:
        ws.receive_json()
        send(ws, "interrupt_requested", {"new_input": "anything"})
        assert ws.receive_json()["event"] == "error"


def test_a_second_question_while_answering_is_refused_until_interrupted(client):
    with client.websocket_connect(url()) as ws:
        ws.receive_json()
        send(ws, "user_message", {"text": "slow question"})
        receive_until(ws, {"token_chunk"})
        send(ws, "user_message", {"text": "another"})
        events = receive_until(ws, {"error"})
        assert events[-1]["event"] == "error"
        send(ws, "interrupt_requested", {"new_input": ""})  # stop it; no new question
        receive_until(ws, {"generation_interrupted"})


# --- reconnecting ------------------------------------------------------------------

def test_reconnecting_with_the_same_session_id_restores_the_thread(client):
    with client.websocket_connect(url()) as ws:
        ws.receive_json()
        send(ws, "user_message", {"text": "first question"})
        receive_until(ws, {"generation_completed"})

    with client.websocket_connect(url()) as ws:  # the connection dropped and came back
        snapshot = ws.receive_json()
        assert snapshot["event"] == "session_snapshot"
        messages = snapshot["data"]["messages"]
        assert [(m["role"], m["text"]) for m in messages] == [
            ("user", "first question"), ("assistant", "short answer"),
        ]
        # and the conversation carries on in the same thread
        send(ws, "user_message", {"text": "second question"})
        receive_until(ws, {"generation_completed"})

    with client.websocket_connect(url()) as ws:
        assert len(ws.receive_json()["data"]["messages"]) == 4


# --- more than one connection on a session -----------------------------------------------

def test_two_connections_on_one_session_each_get_every_event_once(client):
    with client.websocket_connect(url()) as watcher, client.websocket_connect(url()) as chatter:
        watcher.receive_json()
        chatter.receive_json()
        send(chatter, "user_message", {"text": "hello"})
        from_chatter = receive_until(chatter, {"generation_completed"})
        from_watcher = receive_until(watcher, {"generation_completed"})

    def tokens(events):
        return [e["data"]["token"] for e in events if e["event"] == "token_chunk"]

    assert tokens(from_chatter) == tokens(from_watcher) == ["short ", "answer "]


def test_closing_a_connection_removes_its_subscription(client):
    with client.websocket_connect(url()) as ws:
        ws.receive_json()
        assert chat_service.bus.subscriber_count(SESSION) == 1
    deadline = time.time() + 2
    while chat_service.bus.subscriber_count(SESSION) and time.time() < deadline:
        time.sleep(0.02)
    assert chat_service.bus.subscriber_count(SESSION) == 0


# --- the output guard, applied to the live text ----------------------------------------------

def test_a_blocked_answer_is_replaced_and_the_replacement_is_what_gets_saved(client, monkeypatch):
    class LeakyGraph(FakeGraph):
        def stream(self, graph_input, config, stream_mode):
            yield "custom", {"token": "fine so far "}
            yield "custom", {"token": "LEAKED"}
            yield "values", {"answer": "fine so far LEAKED"}

    monkeypatch.setattr(chat_service, "graph", LeakyGraph())
    monkeypatch.setattr(
        chat_service.guard_patterns, "check_output",
        lambda text: ["leaked_system_prompt"] if "LEAKED" in text else [],
    )
    with client.websocket_connect(url()) as ws:
        ws.receive_json()
        send(ws, "user_message", {"text": "hello"})
        events = receive_until(ws, {"generation_completed"})
    names = [e["event"] for e in events]
    assert "output_blocked" in names
    blocked = next(e for e in events if e["event"] == "output_blocked")
    assert "can't share that" in blocked["data"]["replacement"]
    # the blocked token itself was never sent
    assert [e["data"]["token"] for e in events if e["event"] == "token_chunk"] == ["fine so far "]
    with client.websocket_connect(url()) as ws:
        saved = ws.receive_json()["data"]["messages"]
    assert saved[-1]["text"] == blocked["data"]["replacement"]


# --- is an answer in progress? (what a reconnecting page needs to know) -------------------

def test_the_snapshot_says_whether_an_answer_is_in_progress(client, fake_graph):
    fake_graph.delay = 0.3  # slow enough that the answer is still running when we join
    with client.websocket_connect(url()) as chatter:
        chatter.receive_json()
        send(chatter, "user_message", {"text": "slow question"})
        receive_until(chatter, {"token_chunk"})
        # Someone joins (or reconnects) while the answer is still being written.
        with client.websocket_connect(url()) as late:
            assert late.receive_json()["data"]["generating"] is True
        send(chatter, "interrupt_requested", {"new_input": ""})
        receive_until(chatter, {"generation_interrupted"})

    deadline = time.time() + 2
    while chat_service.is_generating(SESSION) and time.time() < deadline:
        time.sleep(0.02)
    with client.websocket_connect(url()) as again:
        assert again.receive_json()["data"]["generating"] is False
