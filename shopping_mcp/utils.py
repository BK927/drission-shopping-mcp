from __future__ import annotations

import html
import ipaddress
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


CAPTURE_DIR_RE = re.compile(r"^\d{8}-\d{6}-")


PRICE_RE = re.compile(r"([0-9][0-9,]{0,20})")
WHITESPACE_RE = re.compile(r"\s+")
SCRIPT_CLEAN_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.I | re.S)
STYLE_CLEAN_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def clean_html_text(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = TAG_RE.sub(" ", value)
    value = WHITESPACE_RE.sub(" ", value)
    return value.strip()


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return WHITESPACE_RE.sub(" ", html.unescape(value)).strip()


def parse_price(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = PRICE_RE.search(str(value))
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def clip_text(value: str, max_chars: int = 6000) -> str:
    value = normalize_text(value)
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    return value


def load_json_maybe(value: str | None) -> Any | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def domain_for_url(url: str) -> str:
    return urlparse(url).netloc.lower()


def is_naver_store_domain(url: str) -> bool:
    host = domain_for_url(url)
    return any(
        token in host
        for token in (
            "smartstore.naver.com",
            "brand.naver.com",
            "shopping.naver.com",
            "store.naver.com",
        )
    )


ALLOWED_PRODUCT_HOSTS_DEFAULT: frozenset[str] = frozenset({
    "smartstore.naver.com",
    "brand.naver.com",
    "shopping.naver.com",
    "search.shopping.naver.com",
    "store.naver.com",
})


def _get_allowed_product_hosts() -> frozenset[str]:
    """Allowlist of hostnames the browser tools may navigate to.

    Read at call time (not import) so ALLOWED_PRODUCT_HOSTS set in .env after
    import still applies. An operator explicitly setting this env var opts
    into extra risk — their value fully replaces the defaults rather than
    extending them, so the choice is visible.
    """
    raw = os.getenv("ALLOWED_PRODUCT_HOSTS", "").strip()
    if not raw:
        return ALLOWED_PRODUCT_HOSTS_DEFAULT
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def is_allowed_product_url(url: str) -> bool:
    """Whether a URL is safe to hand to the browser.

    Enforces scheme (http/https only), disallows numeric hosts pointing at
    private / link-local / loopback ranges, and requires the host to match
    the allowlist (exact match or dotted subdomain).
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False

    allowed = _get_allowed_product_hosts()
    return any(host == h or host.endswith("." + h) for h in allowed)


def prune_capture_dir(debug_dir: str | Path, keep: int) -> None:
    """Remove oldest timestamp-prefixed capture subdirectories beyond `keep`.

    Debug captures accumulate forever by default and a looping attacker can
    fill the Pi's SD card. We key on the timestamp-{host} naming convention
    `_save_debug` emits so operator-placed files like README.txt are left
    alone. Silent on I/O errors — pruning must never break a capture.
    """
    if keep < 0:
        keep = 0
    root = Path(debug_dir)
    try:
        entries = [
            p for p in root.iterdir()
            if p.is_dir() and CAPTURE_DIR_RE.match(p.name)
        ]
    except OSError:
        return
    entries.sort(key=lambda p: p.name)
    for stale in entries[:-keep] if keep > 0 else entries:
        try:
            shutil.rmtree(stale)
        except OSError:
            continue


def absolutize_url(url: str, base_url: str) -> str:
    """Turn a possibly-relative URL into an absolute one using base_url.

    Falls back to the original value when base_url is empty or either value
    is malformed — callers get back something they can still show.
    """
    if not url:
        return url
    if not base_url:
        return url
    try:
        return urljoin(base_url, url)
    except Exception:
        return url


def strip_noise_from_html(value: str) -> str:
    value = SCRIPT_CLEAN_RE.sub(" ", value)
    value = STYLE_CLEAN_RE.sub(" ", value)
    return TAG_RE.sub(" ", value)
