from __future__ import annotations


def test_calculate_slots_is_always_one(monkeypatch):
    """BrowserManager shares a single ChromiumPage, so slots must be 1.

    Running concurrent tools against the same tab would race on page.get().
    If/when a real page pool lands, this test is the signal to revisit.
    """
    monkeypatch.delenv("MAX_BROWSER_SLOTS", raising=False)
    from shopping_mcp.server import _calculate_slots

    # Memory inputs simulating small / medium / large Pi models — all must
    # produce 1 because we only have one browser tab to share.
    assert _calculate_slots(500 * 1024 * 1024) == 1
    assert _calculate_slots(1500 * 1024 * 1024) == 1
    assert _calculate_slots(4 * 1024 * 1024 * 1024) == 1


def test_calculate_slots_ignores_env_override(monkeypatch):
    """MAX_BROWSER_SLOTS must not raise concurrency above 1.

    We deliberately drop the env override knob because the current
    BrowserManager shares a single page — honoring it would reintroduce the
    race this change is fixing.
    """
    monkeypatch.setenv("MAX_BROWSER_SLOTS", "9")
    from shopping_mcp.server import _calculate_slots

    assert _calculate_slots(4 * 1024 * 1024 * 1024) == 1


def test_browser_slots_module_value_is_one(monkeypatch):
    """The module-level slot count must also be 1 regardless of host memory."""
    monkeypatch.delenv("MAX_BROWSER_SLOTS", raising=False)
    from shopping_mcp.server import _browser_slots

    assert _browser_slots == 1


def test_browser_gate_returns_error_when_unavailable():
    import shopping_mcp.server as srv

    original = srv._browser_available
    try:
        srv._browser_available = False
        result = srv.get_product_detail(url="https://example.com")
        assert "error" in result
        assert "Chromium" in result["error"]
    finally:
        srv._browser_available = original
