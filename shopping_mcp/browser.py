from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass(slots=True)
class BrowserConfig:
    headless: bool = True
    no_sandbox: bool = True
    browser_path: str | None = None
    user_data_dir: str | None = None
    page_timeout: int = 20

    @classmethod
    def from_env(cls) -> "BrowserConfig":
        def as_bool(name: str, default: bool) -> bool:
            raw = os.getenv(name)
            if raw is None:
                return default
            return raw.strip().lower() in {"1", "true", "yes", "on"}

        return cls(
            headless=as_bool("DP_HEADLESS", True),
            no_sandbox=as_bool("DP_NO_SANDBOX", True),
            browser_path=os.getenv("DP_BROWSER_PATH") or None,
            user_data_dir=os.getenv("DP_USER_DATA_DIR") or None,
            page_timeout=int(os.getenv("DP_PAGE_TIMEOUT", "20")),
        )


class BrowserManager:
    def __init__(self, config: BrowserConfig | None = None) -> None:
        self.config = config or BrowserConfig.from_env()
        self._page: Any | None = None
        self._lock = threading.Lock()

    def _build_options(self) -> Any:
        from DrissionPage import ChromiumOptions

        co = ChromiumOptions()

        # Linux/headless friendly flags.
        if self.config.headless:
            if hasattr(co, "headless"):
                try:
                    co.headless(True)
                except TypeError:
                    co.headless()
            else:
                co.set_argument("--headless=new")

        if self.config.no_sandbox:
            co.set_argument("--no-sandbox")

        co.set_argument("--disable-dev-shm-usage")
        co.set_argument("--disable-gpu")
        co.set_argument("--disable-blink-features=AutomationControlled")

        if self.config.user_data_dir:
            user_data_dir = str(Path(self.config.user_data_dir).expanduser())
            if hasattr(co, "set_user_data_path"):
                co.set_user_data_path(user_data_dir)
            elif hasattr(co, "set_argument"):
                co.set_argument(f"--user-data-dir={user_data_dir}")

        if self.config.browser_path:
            if hasattr(co, "set_browser_path"):
                co.set_browser_path(self.config.browser_path)
            elif hasattr(co, "set_paths"):
                co.set_paths(browser_path=self.config.browser_path)

        return co

    def _new_page(self) -> Any:
        from DrissionPage import ChromiumPage

        log.info("Starting Chromium browser")
        options = self._build_options()
        try:
            return ChromiumPage(options)
        except Exception:
            log.error("Failed to start Chromium browser", exc_info=True)
            raise

    @staticmethod
    def _is_page_alive(page: Any) -> bool:
        """Best-effort check that a cached ChromiumPage still has a live tab.

        DrissionPage doesn't expose a consistent `is_alive` across versions,
        so we probe a cheap attribute and treat any exception as "dead".
        """
        if page is None:
            return False
        states = getattr(page, "states", None)
        if states is not None and hasattr(states, "is_alive"):
            try:
                return bool(states.is_alive)
            except Exception:
                return False
        try:
            _ = page.url
            return True
        except Exception:
            return False

    def get_page(self) -> Any:
        with self._lock:
            if self._page is not None:
                if self._is_page_alive(self._page):
                    return self._page
                log.warning("Cached ChromiumPage looks dead — rebuilding")
                try:
                    self._page.quit()
                except Exception:
                    pass
                self._page = None

            self._page = self._new_page()
            return self._page

    def reset(self) -> None:
        with self._lock:
            if self._page is not None:
                log.info("Resetting browser")
                try:
                    self._page.quit()
                except Exception:
                    pass
                self._page = None
