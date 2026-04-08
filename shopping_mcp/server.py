from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from mcp.server.fastmcp import FastMCP

log = logging.getLogger(__name__)

from .detail_extractor import ProductDetailExtractor
from .naver_api import NaverShoppingClient

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
    return get_detail_extractor().extract(
        url,
        wait_seconds=wait_seconds,
        max_description_chars=max_description_chars,
        save_debug=save_debug,
        reset_browser=reset_browser,
    )


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
    detail = get_detail_extractor().extract(
        picked["link"],
        wait_seconds=wait_seconds,
        save_debug=save_debug,
    )
    return {"search": search, "picked": picked, "detail": detail}


@mcp.tool()
def capture_product_page(url: str, wait_seconds: float = 2.5) -> dict[str, Any]:
    """Capture page HTML and screenshot for debugging extractors."""
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
