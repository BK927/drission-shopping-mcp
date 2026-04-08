from __future__ import annotations

import os


def test_startup_exits_without_api_keys(monkeypatch):
    """Server must exit if NAVER_CLIENT_ID or NAVER_CLIENT_SECRET is missing."""
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)

    from shopping_mcp.asgi import validate_startup

    result = validate_startup()
    assert result["api_keys_ok"] is False


def test_startup_passes_with_api_keys(monkeypatch):
    """Server must pass validation when API keys are set."""
    monkeypatch.setenv("NAVER_CLIENT_ID", "test_id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test_secret")

    from shopping_mcp.asgi import validate_startup

    result = validate_startup()
    assert result["api_keys_ok"] is True
