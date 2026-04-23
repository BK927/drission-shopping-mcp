from __future__ import annotations


def test_shutdown_browser_calls_reset(monkeypatch):
    """Shutdown hook must close the Chromium page so restarts don't leak procs.

    Tested by stubbing get_detail_extractor to return a fake with a reset()
    that records invocations — mirrors what systemd sees when the unit stops.
    """
    import shopping_mcp.server as srv
    from shopping_mcp.asgi import _shutdown_browser

    calls: list[str] = []

    class FakeBrowser:
        def reset(self) -> None:
            calls.append("reset")

    class FakeExtractor:
        browser = FakeBrowser()

    fake = FakeExtractor()
    monkeypatch.setattr(srv, "get_detail_extractor", lambda: fake)

    _shutdown_browser()

    assert calls == ["reset"]


def test_shutdown_browser_swallows_errors(monkeypatch):
    """A broken browser.reset() must not prevent a clean shutdown."""
    import shopping_mcp.server as srv
    from shopping_mcp.asgi import _shutdown_browser

    class ExplodingBrowser:
        def reset(self) -> None:
            raise RuntimeError("boom")

    class FakeExtractor:
        browser = ExplodingBrowser()

    monkeypatch.setattr(srv, "get_detail_extractor", lambda: FakeExtractor())

    # Must not raise.
    _shutdown_browser()
