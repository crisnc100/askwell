"""The hosted beta's invite gate: every page and API route needs a valid invite code.

Codes come from `LEDGERLINE_INVITE_CODES` (comma-separated). With no codes set there is
no gate, which is the local default; `LEDGERLINE_ENV=beta` or `prod` refuses to start
without codes (ledgerline/api.py). A visitor enters a code once on the gate page; the
browser then keeps the code's SHA-256 hash, never the code itself, in an HttpOnly
cookie. The hash is plain ASCII, so a code in any script works. Scripts can send the
code in the `X-Invite-Code` header instead. Removing a code from the setting locks out
everyone using it at their next request.

Codes and hashes are compared in constant time, and every configured one is compared on
every check, so the response time does not hint at how much was right.

Only wrong codes count against the limit, one per address, whether they come from the
form, the header or the cookie; requests that present no code do not count, and a right
code never does, so many people behind one office address are never locked out. Once an
address has used up its tries, it can still use the credentials already accepted from
it, but anything new from it, right or wrong, gets 429 until the hour has passed.
Otherwise a locked-out guesser could keep testing codes and spot the one that works.
"""

from __future__ import annotations

import hashlib
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
# The login form holds one code; anything longer is refused before it is read.
MAX_FORM_BYTES = 4096
NEEDS_CODE = "Enter your invite code first."
TOO_MANY = "Too many wrong invite codes from your address. Wait an hour and try again."


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


def cookie_value(code: bytes) -> str:
    return hashlib.sha256(code).hexdigest()


def is_valid_cookie(candidate: str | None, codes: list[bytes]) -> bool:
    if not candidate or len(candidate) != 64:
        return False
    given = candidate.encode("ascii", errors="replace")
    matched = False
    for code in codes:
        matched |= hmac.compare_digest(given, cookie_value(code).encode("ascii"))
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
    # Per address: the hashes of credentials already accepted from it, so a locked-out
    # address keeps working for the people who had logged in. Bounded by the codes.
    accepted: dict[str, set[str]] = {}

    def remember(ip: str, code_hash: str) -> None:
        accepted.setdefault(ip, set()).add(code_hash)

    @app.middleware("http")
    async def _gate(  # pyright: ignore[reportUnusedFunction]
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in OPEN_PATHS:
            return await call_next(request)
        cookie = request.cookies.get(COOKIE)
        header = request.headers.get(HEADER)
        if cookie is None and header is None:
            return _refused(request)
        ip = client_ip(request)
        if is_valid_cookie(cookie, codes):
            presented = cookie
        elif is_valid(header, codes):
            assert header is not None
            presented = cookie_value(header.encode("utf-8"))
        else:
            presented = None
        if attempts.full(ip):
            if presented is not None and presented in accepted.get(ip, set()):
                return await call_next(request)
            return _too_many(request)
        if presented is not None:
            remember(ip, presented)
            return await call_next(request)
        attempts.allow(ip)
        response = _refused(request)
        if cookie is not None:
            # A stale cookie (its code was removed) would otherwise spend a try on
            # every page and asset request.
            response.delete_cookie(COOKIE)
        return response

    @app.get("/invite", response_class=HTMLResponse)
    def invite_page() -> HTMLResponse:  # pyright: ignore[reportUnusedFunction]
        return HTMLResponse(_page())

    @app.post("/invite")
    async def invite(request: Request) -> Response:  # pyright: ignore[reportUnusedFunction]
        ip = client_ip(request)
        # A locked-out address is refused before any of the body is read.
        if attempts.full(ip):
            return _too_many(request)
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > MAX_FORM_BYTES:
            attempts.allow(ip)
            return HTMLResponse(_page("That is too long to be a code."), 413)
        body = b""
        async for chunk in request.stream():
            body += chunk
            if len(body) > MAX_FORM_BYTES:
                attempts.allow(ip)
                return HTMLResponse(_page("That is too long to be a code."), 413)
        form = parse_qs(body.decode("utf-8", errors="replace"))
        code = (form.get("code") or [None])[0]
        if not is_valid(code, codes):
            attempts.allow(ip)
            return HTMLResponse(_page("That code is not valid."), status_code=401)
        assert code is not None
        hashed = cookie_value(code.encode("utf-8"))
        remember(ip, hashed)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            COOKIE,
            hashed,
            max_age=COOKIE_DAYS * 86400,
            httponly=True,
            secure=secure_cookie,
            samesite="lax",
        )
        return response


def _too_many(request: Request) -> Response:
    if _wants_page(request) or request.url.path == "/invite":
        return HTMLResponse(_page("Too many tries. Wait an hour and try again."), 429)
    return JSONResponse({"detail": TOO_MANY}, status_code=429)


def _refused(request: Request) -> Response:
    if _wants_page(request):
        return HTMLResponse(_page(), status_code=401)
    return JSONResponse({"detail": NEEDS_CODE}, status_code=401)
