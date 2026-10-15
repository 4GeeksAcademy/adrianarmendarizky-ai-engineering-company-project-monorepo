"""CORS settings (OWASP A05). Written before the fix."""


def _preflight(client, origin):
    return client.options(
        "/suppliers",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


def test_an_outside_website_is_not_allowed(client):
    resp = _preflight(client, "https://attacker.example")
    assert resp.headers.get("access-control-allow-origin") is None


def test_someone_elses_codespace_is_not_allowed(client):
    resp = _preflight(client, "https://other-person-3000.app.github.dev")
    assert resp.headers.get("access-control-allow-origin") is None


def test_the_local_frontends_are_still_allowed(client):
    for port in (3000, 3001, 3002):
        origin = f"http://localhost:{port}"
        resp = _preflight(client, origin)
        assert resp.headers.get("access-control-allow-origin") in (origin, "*")


def test_the_headers_the_frontends_send_are_still_allowed(client):
    resp = client.options(
        "/suppliers",
        headers={
            "Origin": "http://localhost:3001",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
