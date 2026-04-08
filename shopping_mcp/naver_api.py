from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

from .utils import clean_html_text, parse_price

log = logging.getLogger(__name__)

NAVER_SHOPPING_API_URL = "https://openapi.naver.com/v1/search/shop.json"


@dataclass(slots=True)
class NaverShoppingClient:
    client_id: str
    client_secret: str
    base_url: str = NAVER_SHOPPING_API_URL
    timeout: float = 20.0

    @classmethod
    def from_env(cls) -> "NaverShoppingClient":
        client_id = os.getenv("NAVER_CLIENT_ID", "").strip()
        client_secret = os.getenv("NAVER_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET must be set.")
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            base_url=os.getenv("NAVER_API_BASE_URL", NAVER_SHOPPING_API_URL).strip() or NAVER_SHOPPING_API_URL,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
            "Accept": "application/json",
            "User-Agent": "drission-shopping-mcp/0.1",
        }

    def _normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        lowest_price = parse_price(item.get("lprice"))
        highest_price = parse_price(item.get("hprice"))
        return {
            "title": clean_html_text(item.get("title")),
            "title_html": item.get("title") or "",
            "link": item.get("link") or "",
            "image": item.get("image") or "",
            "lowest_price": lowest_price,
            "highest_price": highest_price,
            "current_price": lowest_price,
            "price_text": f"{lowest_price:,}원" if lowest_price else None,
            "mall_name": item.get("mallName") or "",
            "product_id": item.get("productId") or "",
            "product_type": item.get("productType") or "",
            "maker": item.get("maker") or "",
            "brand": item.get("brand") or "",
            "category1": item.get("category1") or "",
            "category2": item.get("category2") or "",
            "category3": item.get("category3") or "",
            "category4": item.get("category4") or "",
            "raw": item,
        }

    def search(
        self,
        *,
        query: str,
        display: int = 10,
        start: int = 1,
        sort: str = "sim",
        filter: str | None = None,
        exclude: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "query": query,
            "display": max(1, min(display, 100)),
            "start": max(1, min(start, 1000)),
            "sort": sort,
        }
        if filter:
            params["filter"] = filter
        if exclude:
            params["exclude"] = exclude

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(self.base_url, params=params, headers=self._headers())
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                log.error("Naver API error: %s %s", response.status_code, response.text[:200])
                raise
            data = response.json()

        return {
            "last_build_date": data.get("lastBuildDate"),
            "total": data.get("total", 0),
            "start": data.get("start", start),
            "display": data.get("display", display),
            "items": [self._normalize_item(x) for x in data.get("items", [])],
            "query": query,
            "sort": sort,
            "filter": filter,
            "exclude": exclude,
        }

    def search_raw(self, **kwargs: Any) -> dict[str, Any]:
        params: dict[str, Any] = {
            "query": kwargs["query"],
            "display": max(1, min(int(kwargs.get("display", 10)), 100)),
            "start": max(1, min(int(kwargs.get("start", 1)), 1000)),
            "sort": kwargs.get("sort", "sim"),
        }
        if kwargs.get("filter"):
            params["filter"] = kwargs["filter"]
        if kwargs.get("exclude"):
            params["exclude"] = kwargs["exclude"]

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(self.base_url, params=params, headers=self._headers())
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                log.error("Naver API error: %s %s", response.status_code, response.text[:200])
                raise
            return response.json()
