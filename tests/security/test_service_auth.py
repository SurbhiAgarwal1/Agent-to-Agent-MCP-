"""ASGI service-authentication configuration and token checks."""

import asyncio
from app.security.service_auth import ServiceAuthenticationMiddleware


def _status(monkeypatch, *, environment, token, authorization):
    if token is None:
        monkeypatch.delenv("SERVICE_TO_SERVICE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("SERVICE_TO_SERVICE_TOKEN", token)
    monkeypatch.setenv("ENVIRONMENT", environment)
    sent = []

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    app = ServiceAuthenticationMiddleware(inner, protected_prefix="/a2a")
    headers = [] if authorization is None else [(b"authorization", authorization.encode())]
    scope = {"type": "http", "path": "/a2a", "headers": headers}
    asyncio.run(app(scope, None, sent.append))
    return sent[0]["status"]


def test_service_auth_is_required_in_production_and_optional_only_in_development(monkeypatch):
    assert _status(monkeypatch, environment="production", token=None, authorization=None) == 503
    assert _status(monkeypatch, environment="production", token="too-short", authorization="Bearer too-short") == 503
    assert _status(monkeypatch, environment="production", token="a" * 40, authorization="Bearer wrong") == 401
    assert _status(monkeypatch, environment="production", token="a" * 40, authorization=f"Bearer {'a' * 40}") == 200
    assert _status(monkeypatch, environment="development", token=None, authorization=None) == 200
