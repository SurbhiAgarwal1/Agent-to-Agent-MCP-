"""Shared-secret authentication for private A2A and MCP service transports."""

import hmac
import os


class ServiceAuthenticationMiddleware:
    """Protect an internal ASGI path without changing its protocol handler."""

    def __init__(self, app, *, protected_prefix: str):
        self.app = app
        self.protected_prefix = protected_prefix

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not (path == self.protected_prefix or path.startswith(self.protected_prefix + "/")):
            await self.app(scope, receive, send)
            return

        expected = os.getenv("SERVICE_TO_SERVICE_TOKEN", "").strip()
        production = os.getenv("ENVIRONMENT", "development").lower() == "production"
        valid_configuration = len(expected) >= 32
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"authorization", b"").decode("latin1")
        accepted = valid_configuration and hmac.compare_digest(supplied, f"Bearer {expected}")
        if not expected and not production:
            accepted = True  # local development only; production refuses to start unauthenticated
        if accepted:
            await self.app(scope, receive, send)
            return

        status = 503 if production and not valid_configuration else 401
        body = b'{"detail":"Internal service authentication required."}'
        await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
