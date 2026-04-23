from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .utils import _get_allowed_product_hosts

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

        for arg in self._hardening_args():
            co.set_argument(arg)

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

    def _hardening_args(self) -> list[str]:
        """Chromium flags that shrink the attack surface of a --no-sandbox
        renderer. Safe defaults; no functional impact on product scraping.

        --host-resolver-rules is the belt-and-suspenders against redirect-to-
        internal-IP: Chromium itself refuses DNS for anything outside the
        URL allowlist, so even if an allowlisted page tries to pivot the
        browser via 302/JS/meta-refresh to 169.254.169.254 it cannot resolve.
        """
        args = [
            "--disable-extensions",
            "--disable-plugins",
            "--disable-sync",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-domain-reliability",
            "--disable-features=Translate,MediaRouter,OptimizationHints,"
            "AutofillServerCommunication",
        ]
        allowed = _get_allowed_product_hosts()
        if allowed:
            # EXCLUDE each allowed host (and its subdomains via wildcard),
            # then MAP everything else to NOTFOUND so DNS resolution fails.
            excludes = []
            for host in sorted(allowed):
                excludes.append(f"EXCLUDE {host}")
                excludes.append(f"EXCLUDE *.{host}")
            rules = ",".join(excludes + ["MAP * ~NOTFOUND"])
            args.append(f"--host-resolver-rules={rules}")
        return args

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
