from __future__ import annotations

import logging
import threading
from functools import lru_cache
from typing import Any

from mcp.server.fastmcp import FastMCP

from .detail_extractor import ProductDetailExtractor
from .naver_api import NaverShoppingClient
from .utils import is_allowed_product_url

log = logging.getLogger(__name__)

_browser_available: bool = True


def set_browser_available(available: bool) -> None:
    global _browser_available
    _browser_available = available


def _calculate_slots(_available_bytes: int | None = None) -> int:
    """Max concurrent browser slots.

    Always 1: BrowserManager owns a single ChromiumPage, so running more than
    one browser tool at a time would race on the shared tab. The argument and
    MAX_BROWSER_SLOTS env var are accepted but ignored; when BrowserManager
    grows a real page pool, this function is the place to return its size.
    """
    return 1


_browser_slots = _calculate_slots()
_browser_semaphore = threading.Semaphore(_browser_slots)

MAX_WAIT_SECONDS: float = 15.0
MAX_DESCRIPTION_CHARS: int = 20_000


def _clamp_wait_seconds(value: float) -> float:
    """Cap wait_seconds so one request can't park the browser slot for hours."""
    if value is None:
        return 0.0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v < 0:
        return 0.0
    if v > MAX_WAIT_SECONDS:
        return MAX_WAIT_SECONDS
    return v


def _clamp_max_chars(value: int) -> int:
    """Cap description size so a request can't force huge MCP payloads."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return MAX_DESCRIPTION_CHARS
    if v < 1:
        return 1
    if v > MAX_DESCRIPTION_CHARS:
        return MAX_DESCRIPTION_CHARS
    return v


_BUSY_ERROR = {"error": "Server busy \u2013 all browser slots in use. Try again shortly."}
_NO_BROWSER_ERROR = {"error": "Chromium is not available. Install chromium and restart the server."}
_BLOCKED_URL_ERROR = {
    "error": (
        "URL host is not on the allowlist. Permitted hosts default to Naver "
        "Shopping domains; extend with ALLOWED_PRODUCT_HOSTS env if needed."
    )
}


mcp = FastMCP(
    "drission-shopping-mcp",
    instructions=(
        "Search products with Naver Shopping API, then optionally fetch a real product page and "
        "extract detailed product information with DrissionPage. Prefer search first, then detail."
    ),
    stateless_http=True,
    json_response=True,
)


@lru_cache(maxsize=1)
def get_naver_client() -> NaverShoppingClient:
    return NaverShoppingClient.from_env()


@lru_cache(maxsize=1)
def get_detail_extractor() -> ProductDetailExtractor:
    return ProductDetailExtractor()


@mcp.tool()
def search_naver_products(
    query: str,
    display: int = 10,
    start: int = 1,
    sort: str = "sim",
    filter: str | None = None,
    exclude: str | None = None,
) -> dict[str, Any]:
    """Search products via Naver Shopping API.

    Args:
        query: Search keywords.
        display: Number of items to return (1~100).
        start: Start offset (1~1000).
        sort: sim/date/asc/dsc.
        filter: e.g. naverpay.
        exclude: e.g. used:rental:cbshop.
    """
    log.info("search_naver_products query=%s", query)
    return get_naver_client().search(
        query=query,
        display=display,
        start=start,
        sort=sort,
        filter=filter,
        exclude=exclude,
    )


@mcp.tool()
def search_naver_products_raw(
    query: str,
    display: int = 10,
    start: int = 1,
    sort: str = "sim",
    filter: str | None = None,
    exclude: str | None = None,
) -> dict[str, Any]:
    """Return the near-raw JSON response from Naver Shopping API."""
    log.info("search_naver_products_raw query=%s", query)
    return get_naver_client().search_raw(
        query=query,
        display=display,
        start=start,
        sort=sort,
        filter=filter,
        exclude=exclude,
    )


@mcp.tool()
def get_product_detail(
    url: str,
    wait_seconds: float = 2.5,
    max_description_chars: int = 6000,
    save_debug: bool = False,
    reset_browser: bool = False,
) -> dict[str, Any]:
    """Open a product page in DrissionPage and extract detail data.

    Args:
        url: Product page URL.
        wait_seconds: Time to wait after page.get(). Increase for heavy JS pages.
        max_description_chars: Clip long descriptions to this length.
        save_debug: Save HTML/screenshot under DEBUG_CAPTURE_DIR.
        reset_browser: Restart browser before opening the page.
    """
    if not _browser_available:
        return {**_NO_BROWSER_ERROR}
    if not is_allowed_product_url(url):
        log.warning("get_product_detail blocked non-allowlist url=%s", url)
        return {**_BLOCKED_URL_ERROR}
    wait_seconds = _clamp_wait_seconds(wait_seconds)
    max_description_chars = _clamp_max_chars(max_description_chars)
    if not _browser_semaphore.acquire(timeout=60):
        log.warning("Browser semaphore timeout for get_product_detail url=%s", url)
        return {**_BUSY_ERROR}
    try:
        log.info("get_product_detail url=%s", url)
        return get_detail_extractor().extract(
            url,
            wait_seconds=wait_seconds,
            max_description_chars=max_description_chars,
            save_debug=save_debug,
            reset_browser=reset_browser,
        )
    except Exception:
        log.error("get_product_detail failed url=%s", url, exc_info=True)
        return {"error": f"Failed to extract detail from {url}"}
    finally:
        _browser_semaphore.release()


@mcp.tool()
def search_then_fetch_detail(
    query: str,
    pick: int = 1,
    display: int = 5,
    sort: str = "sim",
    filter: str | None = None,
    exclude: str | None = None,
    wait_seconds: float = 2.5,
    save_debug: bool = False,
) -> dict[str, Any]:
    """Search Naver products first, then fetch detail for the picked result.

    Args:
        query: Search keywords.
        pick: 1-based index from the search results.
        display: Number of candidates to fetch from search.
    """
    if not _browser_available:
        return {**_NO_BROWSER_ERROR}
    wait_seconds = _clamp_wait_seconds(wait_seconds)

    log.info("search_then_fetch_detail query=%s pick=%d", query, pick)
    search = get_naver_client().search(
        query=query,
        display=display,
        start=1,
        sort=sort,
        filter=filter,
        exclude=exclude,
    )
    items = search.get("items", [])
    if not items:
        return {"search": search, "picked": None, "detail": None, "error": "No search results."}

    index = max(1, pick) - 1
    if index >= len(items):
        index = 0
    picked = items[index]

    picked_link = picked.get("link", "")
    if not is_allowed_product_url(picked_link):
        log.warning(
            "search_then_fetch_detail skipped non-allowlist link=%s", picked_link
        )
        return {
            "search": search,
            "picked": picked,
            "detail": None,
            "error": (
                "Picked product's link host is not on the allowlist. "
                "Extend ALLOWED_PRODUCT_HOSTS to include it."
            ),
        }

    if not _browser_semaphore.acquire(timeout=60):
        log.warning("Browser semaphore timeout for search_then_fetch_detail query=%s", query)
        return {"search": search, "picked": picked, "detail": None, "error": "Server busy \u2013 all browser slots in use. Try again shortly."}
    try:
        detail = get_detail_extractor().extract(
            picked["link"],
            wait_seconds=wait_seconds,
            save_debug=save_debug,
        )
    except Exception:
        log.error("search_then_fetch_detail extract failed query=%s", query, exc_info=True)
        detail = {"error": f"Failed to extract detail from {picked['link']}"}
    finally:
        _browser_semaphore.release()

    return {"search": search, "picked": picked, "detail": detail}


@mcp.tool()
def capture_product_page(url: str, wait_seconds: float = 2.5) -> dict[str, Any]:
    """Capture page HTML and screenshot for debugging extractors."""
    if not _browser_available:
        return {**_NO_BROWSER_ERROR}
    if not is_allowed_product_url(url):
        log.warning("capture_product_page blocked non-allowlist url=%s", url)
        return {**_BLOCKED_URL_ERROR}
    wait_seconds = _clamp_wait_seconds(wait_seconds)
    if not _browser_semaphore.acquire(timeout=60):
        log.warning("Browser semaphore timeout for capture_product_page url=%s", url)
        return {**_BUSY_ERROR}
    try:
        log.info("capture_product_page url=%s", url)
        detail = get_detail_extractor().extract(
            url,
            wait_seconds=wait_seconds,
            save_debug=True,
            max_description_chars=1200,
        )
        return {
            "source_url": detail.get("source_url"),
            "title": detail.get("title"),
            "debug_capture": detail.get("debug_capture"),
            "adapter": detail.get("adapter"),
            "jsonld_product_count": detail.get("jsonld_product_count"),
        }
    except Exception:
        log.error("capture_product_page failed url=%s", url, exc_info=True)
        return {"error": f"Failed to capture page {url}"}
    finally:
        _browser_semaphore.release()
