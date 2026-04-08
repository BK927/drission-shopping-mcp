#!/usr/bin/env python3
"""End-to-end smoke test — calls every MCP tool function directly.

Loads .env automatically. No running server needed.

Usage:
    uv run python scripts/smoke_test.py

Exit code: 0 = all passed, 1 = one or more failures.
"""
from __future__ import annotations

import io
import sys

# Force UTF-8 output (Windows terminals default to cp949)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

# Load .env before importing shopping_mcp (credentials + config needed at import)
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from shopping_mcp.server import (
    search_naver_products,
    search_naver_products_raw,
    get_product_detail,
    search_then_fetch_detail,
    capture_product_page,
    _browser_available,
)


# ── Output helpers ────────────────────────────────────────────────────────────

errors = 0


def ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def fail(msg: str) -> None:
    global errors
    errors += 1
    print(f"  FAIL  {msg}")


def skip(msg: str) -> None:
    print(f"  SKIP  {msg}")


def section(n: int, title: str) -> None:
    print(f"\n[{n}] {title}")


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_search() -> list[dict]:
    """search_naver_products — Naver API integration."""
    section(1, "search_naver_products")
    try:
        result = search_naver_products(query="무선 마우스", display=3)
        items = result.get("items", [])
        if not items:
            fail("No items returned")
            return []
        ok(f"{len(items)} items returned (total={result.get('total', '?'):,})")
        ok(f"First: {items[0].get('title', '?')[:50]}")
        ok(f"Price: {items[0].get('price_text') or '(none)'}")
        return items
    except Exception as e:
        fail(f"Exception: {e}")
        return []


def test_search_raw() -> None:
    """search_naver_products_raw — raw Naver API response."""
    section(2, "search_naver_products_raw")
    try:
        result = search_naver_products_raw(query="키보드", display=1)
        if result.get("items"):
            ok(f"Raw response OK (total={result.get('total', '?'):,})")
        else:
            fail("No items in raw response")
    except Exception as e:
        fail(f"Exception: {e}")


def test_get_detail(link: str) -> None:
    """get_product_detail — browser extraction."""
    section(3, "get_product_detail")
    if not _browser_available:
        skip("Chromium not available — browser tools disabled")
        skip("Install chromium and set DP_BROWSER_PATH to enable")
        return
    if not link:
        skip("No URL from step 1")
        return
    try:
        result = get_product_detail(url=link, wait_seconds=5)
        err = result.get("error", "")
        if err:
            fail(err)
            return
        ok(f"Title:   {(result.get('title') or '(none)')[:50]}")
        ok(f"Price:   {result.get('price_text') or result.get('current_price') or '(none)'}")
        ok(f"Images:  {len(result.get('images') or [])}")
        ok(f"Adapter: {result.get('adapter', '?')}")
    except Exception as e:
        fail(f"Exception: {e}")


def test_search_then_fetch() -> None:
    """search_then_fetch_detail — full search-to-detail pipeline."""
    section(4, "search_then_fetch_detail")
    if not _browser_available:
        skip("Chromium not available")
        return
    try:
        result = search_then_fetch_detail(
            query="USB 허브", pick=1, display=3, wait_seconds=5
        )
        picked = result.get("picked") or {}
        detail = result.get("detail") or {}
        if not picked:
            fail(f"Nothing picked: {result.get('error', '(no error)')}")
            return
        ok(f"Picked: {picked.get('title', '?')[:50]}")
        err = detail.get("error", "")
        if err:
            fail(f"Detail error: {err}")
        else:
            ok(f"Detail: {(detail.get('title') or '(none)')[:50]}")
            ok(f"Price:  {detail.get('price_text') or detail.get('current_price') or '(none)'}")
    except Exception as e:
        fail(f"Exception: {e}")


def test_capture() -> None:
    """capture_product_page — debug capture (Chromium only)."""
    section(5, "capture_product_page")
    if not _browser_available:
        skip("Chromium not available")
        return
    # Use a simple, reliable Naver page for capture test
    try:
        result = capture_product_page(
            url="https://smartstore.naver.com/", wait_seconds=3
        )
        if result.get("error"):
            fail(result["error"])
        else:
            ok(f"Captured: {(result.get('title') or '(none)')[:50]}")
            ok(f"Adapter: {result.get('adapter', '?')}")
    except Exception as e:
        fail(f"Exception: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("drission-shopping-mcp smoke test")
    print(f"Browser available: {'yes' if _browser_available else 'no (Chromium not found)'}")

    # Run tests
    items = test_search()
    test_search_raw()
    first_link = items[0].get("link", "") if items else ""
    test_get_detail(first_link)
    test_search_then_fetch()
    test_capture()

    # Summary
    print(f"\n{'All checks passed.' if errors == 0 else f'{errors} check(s) FAILED.'}")
    sys.exit(min(errors, 1))


if __name__ == "__main__":
    main()
