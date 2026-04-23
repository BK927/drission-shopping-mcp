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


# Bytes that Python's RFC 3986 urlparse and Chromium's WHATWG URL parser
# handle differently. A single backslash inside the authority is the classic
# SSRF bypass: urlparse treats it as normal, WHATWG rewrites it to '/'.
# Rejecting them at the raw-string level keeps both parsers in lockstep.
_URL_FORBIDDEN_CHARS = ("\\", "\t", "\n", "\r", "\x00", " ")


def canonicalize_product_url(url: str) -> str | None:
    """Validate and return a canonical URL safe to hand to Chromium.

    Returns None if the URL contains parser-differential bytes, uses a
    non-http(s) scheme, points at a reserved IP literal, or fails the
    allowlist. When it returns a string, that string has been reconstructed
    from urlparse's components (userinfo and fragment dropped) so callers
    can pass the return value — not the raw input — to the browser, and
    what we validated is exactly what navigates.
    """
    if not url:
        return None
    if any(c in url for c in _URL_FORBIDDEN_CHARS):
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return None

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return None

    allowed = _get_allowed_product_hosts()
    if not any(host == h or host.endswith("." + h) for h in allowed):
        return None

    try:
        port = parsed.port
    except ValueError:
        return None
    port_part = f":{port}" if port else ""
    path = parsed.path or "/"
    query_part = f"?{parsed.query}" if parsed.query else ""
    return f"{scheme}://{host}{port_part}{path}{query_part}"


def is_allowed_product_url(url: str) -> bool:
    """True iff canonicalize_product_url accepts the URL."""
    return canonicalize_product_url(url) is not None


_DIRNAME_SAFE_RE = re.compile(r"[^a-zA-Z0-9.\-]")


def safe_host_for_dirname(host: str | None) -> str:
    """Turn a hostname into a filesystem-safe directory fragment.

    Only [a-zA-Z0-9.-] are preserved; anything else becomes '_'. Empty or
    None becomes 'page'. Avoids null bytes, percent-encoded path separators,
    and other operator-hostile characters landing inside debug_captures/.
    """
    if not host:
        return "page"
    cleaned = _DIRNAME_SAFE_RE.sub("_", host)
    return cleaned or "page"


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
