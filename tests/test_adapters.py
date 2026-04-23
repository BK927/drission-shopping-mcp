from __future__ import annotations

from bs4 import BeautifulSoup


PAGE_URL = "https://shop.example.com/p/123"


def test_generic_adapter_absolutizes_relative_image_urls():
    """Without base_url resolution, MCP clients receive '/static/x.jpg' which
    they cannot fetch. The adapter must turn relative src values into full
    URLs anchored at the product page.
    """
    from shopping_mcp.adapters.generic import extract_generic_dom

    html = """
      <html>
        <body>
          <img src="/static/hero.jpg">
          <img src="thumb.png">
          <img src="https://cdn.example.com/abs.jpg">
          <img src="//cdn2.example.com/proto-rel.jpg">
        </body>
      </html>
    """
    soup = BeautifulSoup(html, "lxml")

    result = extract_generic_dom(soup, base_url=PAGE_URL)
    images = result["images"]

    assert "https://shop.example.com/static/hero.jpg" in images
    assert "https://shop.example.com/p/thumb.png" in images
    assert "https://cdn.example.com/abs.jpg" in images
    assert "https://cdn2.example.com/proto-rel.jpg" in images


def test_naver_store_adapter_absolutizes_relative_image_urls():
    from shopping_mcp.adapters.naver_smartstore import extract_naver_store_dom

    html = """
      <html>
        <body>
          <img src="/img/product/1.jpg">
          <img src="https://shop-phinf.pstatic.net/abs.jpg">
        </body>
      </html>
    """
    soup = BeautifulSoup(html, "lxml")

    result = extract_naver_store_dom(
        soup, base_url="https://smartstore.naver.com/store/products/999"
    )
    images = result["images"]

    assert "https://smartstore.naver.com/img/product/1.jpg" in images
    assert "https://shop-phinf.pstatic.net/abs.jpg" in images
