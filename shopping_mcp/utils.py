from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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


def strip_noise_from_html(value: str) -> str:
    value = SCRIPT_CLEAN_RE.sub(" ", value)
    value = STYLE_CLEAN_RE.sub(" ", value)
    return TAG_RE.sub(" ", value)
