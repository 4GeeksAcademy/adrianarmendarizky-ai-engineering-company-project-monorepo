"""Login requirement on POST /knowledge/query (OWASP A01). Written before
the fix. The real RAG pipeline is replaced by a fake, so no model or
Qdrant call is made."""
import routes.knowledge as knowledge_routes


def _fake_rag(monkeypatch):
    calls = []

    def fake(question):
        calls.append(question)
        return "fake answer"

    monkeypatch.setattr(knowledge_routes, "rag_query", fake)
    return calls


def test_no_login_cannot_ask_the_knowledge_base(client, monkeypatch):
    calls = _fake_rag(monkeypatch)
    resp = client.post("/knowledge/query", json={"question": "What is Gold tier?"})
    assert resp.status_code == 401
    assert calls == []  # the pipeline was never reached


def test_a_logged_in_user_still_gets_an_answer(client, register_and_login, monkeypatch):
    _fake_rag(monkeypatch)
    user = register_and_login(email="user@example.com")
    resp = client.post("/knowledge/query", json={"question": "What is Gold tier?"}, headers=user["headers"])
    assert resp.status_code == 200
    assert resp.json()["answer"] == "fake answer"


def test_an_empty_question_is_still_rejected(client, register_and_login, monkeypatch):
    _fake_rag(monkeypatch)
    user = register_and_login(email="user@example.com")
    resp = client.post("/knowledge/query", json={"question": "   "}, headers=user["headers"])
    assert resp.status_code == 422
