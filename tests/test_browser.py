from __future__ import annotations

from typing import Any


class FakePage:
    """Minimal stand-in for DrissionPage.ChromiumPage.

    `alive=False` simulates a crashed / closed tab by making property access
    raise — the shape the real ChromiumPage exhibits after the underlying
    browser process dies.
    """

    def __init__(self, alive: bool = True) -> None:
        self._alive = alive
        self.quit_called = False

    @property
    def url(self) -> str:
        if not self._alive:
            raise RuntimeError("page dead")
        return "https://example.com"

    def quit(self) -> None:
        self.quit_called = True


def _patch_new_page(monkeypatch, made: list[Any]) -> None:
    from shopping_mcp.browser import BrowserManager

    def fake_new_page(self) -> Any:  # noqa: ANN001
        page = FakePage(alive=True)
        made.append(page)
        return page

    monkeypatch.setattr(BrowserManager, "_new_page", fake_new_page)


def test_get_page_creates_when_cache_empty(monkeypatch):
    from shopping_mcp.browser import BrowserManager

    bm = BrowserManager()
    made: list[Any] = []
    _patch_new_page(monkeypatch, made)

    page = bm.get_page()

    assert made == [page]


def test_get_page_reuses_cached_alive_page(monkeypatch):
    from shopping_mcp.browser import BrowserManager

    bm = BrowserManager()
    alive = FakePage(alive=True)
    bm._page = alive

    made: list[Any] = []
    _patch_new_page(monkeypatch, made)

    page = bm.get_page()

    assert page is alive
    assert made == []  # no rebuild


def test_get_page_rebuilds_when_cached_page_is_dead(monkeypatch):
    """If the cached page crashed, next get_page() must transparently restart.

    Without this, long-running Pi deployments wedge after the first browser
    crash: every subsequent call returns the same dead object.
    """
    from shopping_mcp.browser import BrowserManager

    bm = BrowserManager()
    dead = FakePage(alive=False)
    bm._page = dead

    made: list[Any] = []
    _patch_new_page(monkeypatch, made)

    page = bm.get_page()

    assert page is not dead
    assert page is made[0]
    assert dead.quit_called  # cleanup old handle before replacing
