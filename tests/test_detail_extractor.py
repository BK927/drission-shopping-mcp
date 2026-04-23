from __future__ import annotations


def test_extract_jsonld_drops_non_string_image_entries():
    """JSON-LD may emit ImageObject dicts in `image`; keep only URL strings.

    Schema.org permits `"image": [{"@type": "ImageObject", "url": "..."}]`.
    Passing dicts downstream makes absolutize_url silently no-op (TypeError
    is swallowed) and leaks structured entries into the product `images`
    field — clients can't fetch them.
    """
    from shopping_mcp.detail_extractor import ProductDetailExtractor

    extractor = ProductDetailExtractor()
    products = [
        {
            "name": "Test product",
            "image": [
                {"@type": "ImageObject", "url": "https://cdn.example.com/obj.jpg"},
                "https://cdn.example.com/ok.jpg",
                None,
            ],
        }
    ]

    result = extractor._extract_jsonld(products)

    assert all(isinstance(i, str) for i in result["images"])
    assert "https://cdn.example.com/ok.jpg" in result["images"]
