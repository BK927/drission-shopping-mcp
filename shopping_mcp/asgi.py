from __future__ import annotations

import contextlib
import hmac
import logging
import os
import shutil
import sys

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
import uvicorn

from .server import mcp

log = logging.getLogger(__name__)


def validate_startup() -> dict:
    """Check environment config. Returns status dict."""
    result = {"api_keys_ok": False, "browser_available": False, "browser_path": None}

    # 1. API keys
    client_id = os.getenv("NAVER_CLIENT_ID", "").strip()
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        result["api_keys_ok"] = True
    else:
        log.error("NAVER_CLIENT_ID and NAVER_CLIENT_SECRET must both be set")

    # 2. Chromium binary
    browser_path = os.getenv("DP_BROWSER_PATH", "").strip()
    if browser_path:
        resolved = shutil.which(browser_path)
        if resolved:
            result["browser_available"] = True
            result["browser_path"] = resolved
        else:
            log.warning("DP_BROWSER_PATH=%s not found", browser_path)
    else:
        for name in ("chromium", "chromium-browser", "google-chrome"):
            resolved = shutil.which(name)
            if resolved:
                result["browser_available"] = True
                result["browser_path"] = resolved
                break
        if not result["browser_available"]:
            log.warning("No Chromium binary found in PATH — browser tools will be disabled")

    return result


async def healthz(_request):
    return JSONResponse({"status": "ok"})


_BEARER_PREFIX = "Bearer "


def _is_request_authorized(expected_token: str, auth_header: str | None) -> bool:
    """Constant-time Bearer token check.

    `expected_token` comes from MCP_AUTH_TOKEN; `auth_header` is the raw
    Authorization header value. Comparison uses hmac.compare_digest so we
    don't leak a timing oracle to remote clients.
    """
    if not expected_token:
        return False
    if not auth_header or not auth_header.startswith(_BEARER_PREFIX):
        return False
    presented = auth_header[len(_BEARER_PREFIX):].strip()
    if not presented:
        return False
    # hmac.compare_digest raises TypeError on non-ASCII str inputs, which
    # would surface as an unhandled 500 with a traceback in journald. Valid
    # Bearer tokens are ASCII per RFC 6750 (base64/url-safe), so anything
    # else is rejected outright.
    if not presented.isascii() or not expected_token.isascii():
        return False
    return hmac.compare_digest(presented, expected_token)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Gate /mcp behind a shared token. /healthz stays open for probes."""

    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request, call_next):
        if request.url.path == "/healthz":
            return await call_next(request)
        if not _is_request_authorized(self._token, request.headers.get("authorization")):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def _shutdown_browser() -> None:
    """Close the shared Chromium page so systemd restarts don't leak procs.

    Called from lifespan shutdown. Import is deferred so test monkeypatching
    of get_detail_extractor survives module load order.
    """
    from .server import get_detail_extractor

    try:
        get_detail_extractor().browser.reset()
    except Exception:
        log.warning("Browser shutdown failed", exc_info=True)


@contextlib.asynccontextmanager
async def lifespan(_app: Starlette):
    status = validate_startup()

    if not status["api_keys_ok"]:
        log.error("Shutting down — missing API keys")
        sys.exit(1)  # SystemExit before yield is safe: uvicorn catches it at process level

    if not status["browser_available"]:
        from .server import set_browser_available
        set_browser_available(False)
    else:
        log.info("Chromium found at %s", status["browser_path"])

    host = os.getenv("FASTMCP_HOST", "127.0.0.1")
    port = os.getenv("FASTMCP_PORT", "8000")
    from .server import _browser_slots

    log.info(
        "Shopping MCP ready — host=%s port=%s browser=%s max_browser_slots=%d",
        host,
        port,
        "yes" if status["browser_available"] else "no",
        _browser_slots,
    )

    try:
        async with mcp.session_manager.run():
            yield
    finally:
        _shutdown_browser()


def _build_app() -> Starlette:
    token = os.getenv("MCP_AUTH_TOKEN", "").strip()
    starlette_app = Starlette(
        routes=[
            Route("/healthz", healthz),
            Mount("/mcp", app=mcp.streamable_http_app()),
        ],
        lifespan=lifespan,
    )
    if token:
        starlette_app.add_middleware(BearerAuthMiddleware, token=token)
    else:
        log.warning(
            "MCP_AUTH_TOKEN is not set — /mcp is OPEN. "
            "Put the server behind Cloudflare Access, or set MCP_AUTH_TOKEN."
        )
    return starlette_app


app = _build_app()


def _resolve_bind_host() -> str:
    """Pick the host to bind to, failing closed when no auth token is set.

    An unset MCP_AUTH_TOKEN means /mcp is unauthenticated. In that case we
    force 127.0.0.1 regardless of FASTMCP_HOST so a forgotten token can
    never turn into a public-internet exposure. Operators who truly want
    0.0.0.0 must set a token (or front the server with Cloudflare Access).
    """
    configured = os.getenv("FASTMCP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    token = os.getenv("MCP_AUTH_TOKEN", "").strip()
    if not token and configured != "127.0.0.1":
        log.warning(
            "MCP_AUTH_TOKEN not set — refusing FASTMCP_HOST=%s and binding to "
            "127.0.0.1 instead. Set a token to listen publicly.",
            configured,
        )
        return "127.0.0.1"
    return configured


def main() -> None:
    # .env is already loaded at package import time (shopping_mcp/__init__.py).
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        stream=sys.stderr,
    )
    host = _resolve_bind_host()
    port = int(os.getenv("FASTMCP_PORT", "8000"))
    uvicorn.run("shopping_mcp.asgi:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
