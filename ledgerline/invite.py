"""The hosted beta's invite gate: every page and API route needs a valid invite code.

Codes come from `LEDGERLINE_INVITE_CODES` (comma-separated). With no codes set there is
no gate, which is the local default. A visitor enters a code once on the gate page; it
is kept in an HttpOnly cookie, and scripts can send it in the `X-Invite-Code` header
instead. Removing a code from the setting locks out everyone using it at their next
request.

Codes are compared in constant time, and every configured code is compared on every
check, so the response time does not hint at how much of a code was right. Wrong codes
are rate limited per address.
"""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable
from html import escape
from urllib.parse import parse_qs

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ledgerline.workspace.limits import RateLimiter

COOKIE = "ledgerline_invite"
HEADER = "X-Invite-Code"
# Paths that answer without a code: the gate itself, and the health check the host polls.
OPEN_PATHS = frozenset({"/invite", "/healthz"})
COOKIE_DAYS = 30
ATTEMPTS_PER_HOUR = 10
MAX_CODE_CHARS = 200
NEEDS_CODE = "Enter your invite code first."


def parse_codes(raw: str | None) -> list[bytes]:
    return [c.strip().encode("utf-8") for c in (raw or "").split(",") if c.strip()]


def is_valid(candidate: str | None, codes: list[bytes]) -> bool:
    if not candidate or len(candidate) > MAX_CODE_CHARS:
        return False
    given = candidate.encode("utf-8")
    matched = False
    for code in codes:
        # No early exit: every code is compared every time.
        matched |= hmac.compare_digest(given, code)
    return matched


def _page(message: str = "") -> str:
    note = f'<p role="alert">{escape(message)}</p>' if message else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ledgerline beta</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:28rem;margin:4rem auto;padding:0 1rem}}
input,button{{font:inherit;padding:.4rem .6rem}}</style></head>
<body><h1>Ledgerline beta</h1>
<p>This beta is invite-only. Enter the code you were given.</p>{note}
<form method="post" action="/invite">
<label>Invite code
<input name="code" autocomplete="off" required maxlength="{MAX_CODE_CHARS}"></label>
<button type="submit">Continue</button></form></body></html>
"""


def _wants_page(request: Request) -> bool:
    return request.method == "GET" and "text/html" in request.headers.get("accept", "")


def install(
    app: FastAPI,
    codes: list[bytes],
    client_ip: Callable[[Request], str],
    secure_cookie: bool = True,
) -> None:
    """Add the gate to `app`. Does nothing when `codes` is empty."""
    if not codes:
        return
    attempts = RateLimiter(ATTEMPTS_PER_HOUR, 3600.0)

    @app.middleware("http")
    async def _gate(  # pyright: ignore[reportUnusedFunction]
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in OPEN_PATHS:
            return await call_next(request)
        given = request.cookies.get(COOKIE) or request.headers.get(HEADER)
        if is_valid(given, codes):
            return await call_next(request)
        if _wants_page(request):
            return HTMLResponse(_page(), status_code=401)
        return JSONResponse({"detail": NEEDS_CODE}, status_code=401)

    @app.get("/invite", response_class=HTMLResponse)
    def invite_page() -> HTMLResponse:  # pyright: ignore[reportUnusedFunction]
        return HTMLResponse(_page())

    @app.post("/invite")
    async def invite(request: Request) -> Response:  # pyright: ignore[reportUnusedFunction]
        form = parse_qs((await request.body()).decode("utf-8", errors="replace"))
        code = (form.get("code") or [None])[0]
        # Every try counts, right or wrong, so the limit is checked before the code.
        if not attempts.allow(client_ip(request)):
            return HTMLResponse(_page("Too many tries. Wait an hour and try again."), 429)
        if not is_valid(code, codes):
            return HTMLResponse(_page("That code is not valid."), status_code=401)
        response = RedirectResponse("/", status_code=303)
        assert code is not None
        response.set_cookie(
            COOKIE,
            code,
            max_age=COOKIE_DAYS * 86400,
            httponly=True,
            secure=secure_cookie,
            samesite="lax",
        )
        return response
