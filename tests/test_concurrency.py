from __future__ import annotations


def test_calculate_slots_low_memory():
    from shopping_mcp.server import _calculate_slots
    # < 1GB -> 1 slot
    assert _calculate_slots(500 * 1024 * 1024) == 1


def test_calculate_slots_medium_memory():
    from shopping_mcp.server import _calculate_slots
    # 1-2GB -> 2 slots
    assert _calculate_slots(1500 * 1024 * 1024) == 2


def test_calculate_slots_high_memory():
    from shopping_mcp.server import _calculate_slots
    # >= 2GB -> 3 slots (cap)
    assert _calculate_slots(4 * 1024 * 1024 * 1024) == 3


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
