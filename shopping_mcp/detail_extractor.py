from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .adapters.generic import extract_generic_dom
from .adapters.naver_smartstore import extract_naver_store_dom
from .browser import BrowserManager
from .utils import (
    clip_text,
    domain_for_url,
    ensure_dir,
    is_naver_store_domain,
    load_json_maybe,
    normalize_text,
    parse_price,
)

log = logging.getLogger(__name__)


class ProductDetailExtractor:
    def __init__(self, browser: BrowserManager | None = None) -> None:
        self.browser = browser or BrowserManager()
        self.debug_dir = ensure_dir(os.getenv("DEBUG_CAPTURE_DIR", "./debug_captures"))

    def _run_dom_probe(self, page: Any) -> dict[str, Any]:
        script = r"""
        (() => {
          const text = (selector) => {
            const el = document.querySelector(selector);
            return el ? el.innerText.trim() : null;
          };
          const attrs = (selector, attr) => Array.from(document.querySelectorAll(selector))
            .map(el => el.getAttribute(attr))
            .filter(Boolean);
          const jsonLd = Array.from(document.querySelectorAll('script[type="application/ld+json"]'))
            .map(x => x.textContent)
            .filter(Boolean);
          const metas = {};
          for (const el of document.querySelectorAll('meta[property], meta[name]')) {
            const key = el.getAttribute('property') || el.getAttribute('name');
            const value = el.getAttribute('content');
            if (key && value && !(key in metas)) metas[key] = value;
          }
          const selects = [];
          for (const option of document.querySelectorAll('select option, [role="option"]')) {
            const t = option.innerText?.trim();
            if (t) selects.push(t);
            if (selects.length >= 50) break;
          }
          const rows = [];
          for (const tr of document.querySelectorAll('table tr')) {
            const cells = Array.from(tr.querySelectorAll('th,td')).map(x => x.innerText?.trim()).filter(Boolean);
            if (cells.length >= 2) rows.push([cells[0], cells[1]]);
            if (rows.length >= 50) break;
          }
          return JSON.stringify({
            title: document.title,
            metas,
            jsonLd,
            images: attrs('img[src]', 'src').slice(0, 20),
            options: selects,
            tableRows: rows,
            h1: text('h1'),
            h2: text('h2'),
            bodyText: document.body?.innerText?.slice(0, 12000) || null,
            canonical: document.querySelector('link[rel="canonical"]')?.href || null,
          });
        })();
        """
        raw = page.run_js(script)
        parsed = load_json_maybe(raw)
        return parsed or {}

    def _load_jsonld_products(self, payloads: list[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        def visit(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    visit(item)
                return
            if not isinstance(node, dict):
                return

            node_type = node.get("@type")
            if node_type == "Product" or (isinstance(node_type, list) and "Product" in node_type):
                results.append(node)

            for value in node.values():
                if isinstance(value, (list, dict)):
                    visit(value)

        for payload in payloads:
            try:
                visit(json.loads(payload))
            except Exception:
                continue
        return results

    def _pick_offer(self, product: dict[str, Any]) -> dict[str, Any]:
        offers = product.get("offers")
        if isinstance(offers, list):
            for offer in offers:
                if isinstance(offer, dict):
                    return offer
        if isinstance(offers, dict):
            return offers
        return {}

    def _extract_jsonld(self, jsonld_products: list[dict[str, Any]]) -> dict[str, Any]:
        if not jsonld_products:
            return {}

        product = jsonld_products[0]
        offer = self._pick_offer(product)
        aggregate = product.get("aggregateRating") if isinstance(product.get("aggregateRating"), dict) else {}
        brand = product.get("brand")
        if isinstance(brand, dict):
            brand_name = brand.get("name")
        else:
            brand_name = brand

        images = product.get("image")
        if isinstance(images, str):
            images = [images]
        elif not isinstance(images, list):
            images = []

        return {
            "title": product.get("name"),
            "description": clip_text(product.get("description") or "", 6000) if product.get("description") else None,
            "images": images,
            "current_price": parse_price(offer.get("price") or offer.get("priceSpecification", {}).get("price")),
            "currency": offer.get("priceCurrency"),
            "availability": offer.get("availability"),
            "seller_name": (offer.get("seller") or {}).get("name") if isinstance(offer.get("seller"), dict) else None,
            "brand": brand_name,
            "sku": product.get("sku") or product.get("mpn"),
            "rating_value": aggregate.get("ratingValue"),
            "review_count": aggregate.get("reviewCount"),
        }

    def _merge(self, *sources: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for source in sources:
            for key, value in source.items():
                if value in (None, "", [], {}):
                    continue
                if key not in result:
                    result[key] = value
                    continue
                if isinstance(result[key], list) and isinstance(value, list):
                    seen = set(result[key])
                    for item in value:
                        if item not in seen:
                            result[key].append(item)
                            seen.add(item)
                elif isinstance(result[key], dict) and isinstance(value, dict):
                    merged = dict(result[key])
                    merged.update({k: v for k, v in value.items() if v not in (None, "", [], {})})
                    result[key] = merged
        return result

    def _build_dom_fallback(self, soup: BeautifulSoup, dom_probe: dict[str, Any]) -> dict[str, Any]:
        generic = extract_generic_dom(soup)
        if dom_probe.get("title") and not generic.get("title"):
            generic["title"] = dom_probe["title"]
        if dom_probe.get("images"):
            generic["images"] = list(dict.fromkeys((generic.get("images") or []) + dom_probe["images"]))
        if dom_probe.get("options") and not generic.get("options"):
            generic["options"] = dom_probe["options"][:20]
        if dom_probe.get("tableRows") and not generic.get("specs"):
            generic["specs"] = {x[0]: x[1] for x in dom_probe["tableRows"] if len(x) >= 2}
        if not generic.get("description") and dom_probe.get("bodyText"):
            generic["description"] = clip_text(dom_probe["bodyText"], 6000)
        return generic

    def _site_adapter(self, url: str, soup: BeautifulSoup) -> dict[str, Any]:
        if is_naver_store_domain(url):
            return extract_naver_store_dom(soup)
        return {}

    def _save_debug(self, url: str, html_text: str, page: Any) -> dict[str, str]:
        host = urlparse(url).netloc.replace(":", "_") or "page"
        ts = time.strftime("%Y%m%d-%H%M%S")
        base_dir = ensure_dir(self.debug_dir / f"{ts}-{host}")
        html_path = base_dir / "page.html"
        png_path = base_dir / "page.png"
        html_path.write_text(html_text, encoding="utf-8")
        try:
            page.get_screenshot(str(png_path))
        except Exception:
            pass
        return {"html_path": str(html_path), "screenshot_path": str(png_path)}

    def extract(
        self,
        url: str,
        *,
        wait_seconds: float = 2.5,
        max_description_chars: int = 6000,
        save_debug: bool = False,
        reset_browser: bool = False,
    ) -> dict[str, Any]:
        if reset_browser:
            self.browser.reset()

        page = self.browser.get_page()
        page.get(url)
        time.sleep(max(0.2, wait_seconds))

        html_text = getattr(page, "html", "") or ""
        title = getattr(page, "title", "") or ""
        dom_probe = self._run_dom_probe(page)
        soup = BeautifulSoup(html_text, "lxml")

        jsonld_products = self._load_jsonld_products(dom_probe.get("jsonLd", []))
        jsonld_result = self._extract_jsonld(jsonld_products)
        adapter_result = self._site_adapter(url, soup)
        fallback_result = self._build_dom_fallback(soup, dom_probe)
        merged = self._merge(jsonld_result, adapter_result, fallback_result)

        description = merged.get("description") or ""
        merged["description"] = clip_text(description, max_description_chars) if description else None

        if not merged.get("title"):
            merged["title"] = normalize_text(title) or dom_probe.get("h1") or dom_probe.get("h2")

        if not merged.get("current_price"):
            merged["current_price"] = parse_price(dom_probe.get("metas", {}).get("product:price:amount"))

        if merged.get("current_price") and not merged.get("price_text"):
            merged["price_text"] = f"{merged['current_price']:,}원"

        merged["source_url"] = url
        merged["final_url"] = dom_probe.get("canonical") or url
        merged["domain"] = domain_for_url(url)
        merged["adapter"] = "naver_store" if is_naver_store_domain(url) else "generic"
        merged["jsonld_product_count"] = len(jsonld_products)
        merged["meta"] = dom_probe.get("metas", {})

        if save_debug:
            merged["debug_capture"] = self._save_debug(url, html_text, page)

        return merged
