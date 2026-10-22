"""Security headers on every response.

The page and the API come from this one server, so these are the only place
the browser learns what the page may load, who may frame it, and to insist
on HTTPS.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from ..config import Settings

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

# FastAPI's interactive docs load their scripts from a CDN; a policy strict
# enough for the app would leave them blank.
DOCS_PREFIXES = ("/docs", "/redoc")


def content_security_policy(settings: Settings) -> str:
    """What the page may load: itself, plus Google's sign-in when it is on."""
    script = ["'self'"]
    connect = ["'self'"]
    frame = ["'none'"]
    if settings.firebase_enabled:
        # Firebase's Google popup loads Google's script, talks to its token
        # endpoints and runs a helper frame on the project's auth domain.
        script += ["https://apis.google.com", "https://www.gstatic.com"]
        connect += ["https://*.googleapis.com", "https://apis.google.com"]
        auth_domain = (settings.firebase_web_config or {}).get("authDomain", "")
        frame = ["https://accounts.google.com", "https://apis.google.com"]
        if auth_domain:
            frame.append(f"https://{auth_domain}")
    directives = {
        "default-src": ["'self'"],
        "script-src": script,
        # React sets style properties directly; inline <style> is not used,
        # but libraries may, and styles cannot run code.
        "style-src": ["'self'", "'unsafe-inline'"],
        "img-src": ["'self'", "data:", "https:"],
        "font-src": ["'self'", "data:"],
        "connect-src": connect,
        "frame-src": frame,
        "frame-ancestors": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
        "object-src": ["'none'"],
    }
    return "; ".join(f"{name} {' '.join(values)}" for name, values in directives.items())


def security_headers(settings: Settings) -> list[tuple[bytes, bytes]]:
    headers = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"same-origin"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    ]
    # Only over HTTPS: telling a browser to insist on it for a plain-http
    # development server would lock that browser out of it.
    if settings.cookie_secure:
        headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
    return headers


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.headers = security_headers(settings)
        self.csp = (b"content-security-policy", content_security_policy(settings).encode())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        extra = list(self.headers)
        if not str(scope.get("path", "")).startswith(DOCS_PREFIXES):
            extra.append(self.csp)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                present = {name.lower() for name, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [
                    (name, value) for name, value in extra if name not in present
                ]
            await send(message)

        await self.app(scope, receive, send_with_headers)
