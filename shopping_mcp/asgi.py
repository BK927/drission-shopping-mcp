from __future__ import annotations

import contextlib
import logging
import os
import shutil
import sys

from dotenv import load_dotenv
from starlette.applications import Starlette
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


@contextlib.asynccontextmanager
async def lifespan(_app: Starlette):
    status = validate_startup()

    if not status["api_keys_ok"]:
        log.error("Shutting down — missing API keys")
        sys.exit(1)

    if not status["browser_available"]:
        from .server import set_browser_available
        set_browser_available(False)
    else:
        log.info("Chromium found at %s", status["browser_path"])

    host = os.getenv("FASTMCP_HOST", "127.0.0.1")
    port = os.getenv("FASTMCP_PORT", "8000")
    log.info(
        "Shopping MCP ready — host=%s port=%s browser=%s",
        host,
        port,
        "yes" if status["browser_available"] else "no",
    )

    async with mcp.session_manager.run():
        yield


app = Starlette(
    routes=[
        Route("/healthz", healthz),
        Mount("/mcp", app=mcp.streamable_http_app()),
    ],
    lifespan=lifespan,
)


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        stream=sys.stderr,
    )
    host = os.getenv("FASTMCP_HOST", "127.0.0.1")
    port = int(os.getenv("FASTMCP_PORT", "8000"))
    uvicorn.run("shopping_mcp.asgi:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
