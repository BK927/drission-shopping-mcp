from __future__ import annotations

from bs4 import BeautifulSoup

from ..utils import absolutize_url, clip_text, normalize_text, parse_price


SMARTSTORE_SCRIPT_HINTS = [
    "__PRELOADED_STATE__",
    "__NEXT_DATA__",
    "smartstore",
    "mallPc",
]


def extract_naver_store_dom(soup: BeautifulSoup, *, base_url: str = "") -> dict:
    def first_text(*selectors: str) -> str | None:
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                text = normalize_text(node.get_text(" ", strip=True))
                if text:
                    return text
        return None

    title = first_text(
        "h3",
        "h1",
        "[data-shp-area='product_name']",
        "[class*='product_name']",
        "[class*='ProductName']",
    )

    price_text = first_text(
        "[class*='price']",
        "[class*='sale_price']",
        "[data-shp-area='buybox'] [class*='price']",
    )
    current_price = parse_price(price_text)

    desc = first_text(
        "[class*='se-main-container']",
        "[class*='detail']",
        "#INTRODUCE",
    )

    shipping = first_text(
        "[class*='delivery']",
        "[class*='shipping']",
    )

    images: list[str] = []
    for node in soup.select("img[src]"):
        src = node.get("src")
        if not src:
            continue
        absolute = absolutize_url(src, base_url)
        if absolute not in images:
            images.append(absolute)
        if len(images) >= 15:
            break

    specs: dict[str, str] = {}
    for row in soup.select("table tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            key = normalize_text(cells[0].get_text(" ", strip=True))
            val = normalize_text(cells[1].get_text(" ", strip=True))
            if key and val and key not in specs:
                specs[key] = val

    options: list[str] = []
    for node in soup.select("select option, [role='option']"):
        text = normalize_text(node.get_text(" ", strip=True))
        if text and text not in options:
            options.append(text)
        if len(options) >= 30:
            break

    return {
        "title": title,
        "description": clip_text(desc or "", 6000) if desc else None,
        "current_price": current_price,
        "price_text": f"{current_price:,}원" if current_price else price_text,
        "images": images,
        "shipping": shipping,
        "options": options[:20],
        "specs": specs,
    }
