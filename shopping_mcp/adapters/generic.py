from __future__ import annotations

from bs4 import BeautifulSoup

from ..utils import clip_text, normalize_text, parse_price


def extract_generic_dom(soup: BeautifulSoup) -> dict:
    def meta(*keys: str) -> str | None:
        for key in keys:
            tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
            if tag and tag.get("content"):
                return normalize_text(tag["content"])
        return None

    def text_selectors(*selectors: str) -> str | None:
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                text = normalize_text(node.get_text(" ", strip=True))
                if text:
                    return text
        return None

    title = (
        meta("og:title", "twitter:title")
        or text_selectors("h1", "[data-testid='product-name']", ".prod_title", ".product_title")
        or (normalize_text(soup.title.text) if soup.title else None)
    )
    description = meta("description", "og:description", "twitter:description") or text_selectors(
        ".product_description", ".prod_description", "#product-detail", "#DETAIL"
    )

    image_candidates: list[str] = []
    for selector in [
        "meta[property='og:image']",
        "meta[name='twitter:image']",
        "img[src]",
    ]:
        for node in soup.select(selector):
            url = node.get("content") or node.get("src")
            if url and url not in image_candidates:
                image_candidates.append(url)
            if len(image_candidates) >= 12:
                break
        if len(image_candidates) >= 12:
            break

    price_text = (
        meta("product:price:amount")
        or text_selectors(
            "[itemprop='price']",
            "[data-testid='price']",
            ".price",
            ".prod_price",
            ".total_price",
            ".sale_price",
        )
    )
    current_price = parse_price(price_text)

    seller_name = text_selectors(
        ".seller_name",
        "[data-testid='seller-name']",
        ".store_name",
        ".shop_name",
    )

    shipping = text_selectors(
        ".shipping",
        ".delivery",
        ".delivery_info",
        "[data-testid='shipping']",
    )

    options: list[str] = []
    for select in soup.select("select"):
        for option in select.select("option"):
            text = normalize_text(option.get_text(" ", strip=True))
            if text and text.lower() not in {"선택", "choose", "select"} and text not in options:
                options.append(text)
            if len(options) >= 30:
                break

    for label in soup.select("label"):
        text = normalize_text(label.get_text(" ", strip=True))
        if 1 < len(text) <= 80 and text not in options:
            options.append(text)
        if len(options) >= 30:
            break

    specs: dict[str, str] = {}
    for row in soup.select("table tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            key = normalize_text(cells[0].get_text(" ", strip=True))
            val = normalize_text(cells[1].get_text(" ", strip=True))
            if key and val and key not in specs:
                specs[key] = val
        if len(specs) >= 30:
            break

    return {
        "title": title,
        "description": clip_text(description or "", 6000) if description else None,
        "current_price": current_price,
        "price_text": f"{current_price:,}원" if current_price else price_text,
        "images": image_candidates,
        "seller_name": seller_name,
        "shipping": shipping,
        "options": options[:20],
        "specs": specs,
    }
