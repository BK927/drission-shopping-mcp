from __future__ import annotations


# ── URL allowlist ────────────────────────────────────────────────────────────

def test_allowlist_accepts_default_naver_hosts(monkeypatch):
    """Default allowlist must cover the Naver Shopping surface used in prod.

    These hosts come back from Naver Shopping API `link` fields and are what
    detail_extractor is actually designed to parse.
    """
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.utils import is_allowed_product_url

    assert is_allowed_product_url("https://smartstore.naver.com/store/products/1")
    assert is_allowed_product_url("https://brand.naver.com/some/brand")
    assert is_allowed_product_url("https://shopping.naver.com/home")
    assert is_allowed_product_url("https://search.shopping.naver.com/search/all?query=x")


def test_allowlist_accepts_subdomains(monkeypatch):
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.utils import is_allowed_product_url

    # Subdomain of an allowed host must still be allowed.
    assert is_allowed_product_url("https://www.smartstore.naver.com/x")


def test_allowlist_rejects_private_and_metadata_ips(monkeypatch):
    """SSRF vectors: LAN router, cloud metadata, loopback, link-local."""
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.utils import is_allowed_product_url

    assert not is_allowed_product_url("http://192.168.1.1/admin")
    assert not is_allowed_product_url("http://169.254.169.254/latest/meta-data/")
    assert not is_allowed_product_url("http://127.0.0.1:22/")
    assert not is_allowed_product_url("http://10.0.0.5/")


def test_allowlist_rejects_dangerous_schemes(monkeypatch):
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.utils import is_allowed_product_url

    assert not is_allowed_product_url("file:///etc/passwd")
    assert not is_allowed_product_url("javascript:alert(1)")
    assert not is_allowed_product_url("chrome://settings")
    assert not is_allowed_product_url("about:blank")
    assert not is_allowed_product_url("")


def test_allowlist_rejects_hosts_outside_allowlist(monkeypatch):
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.utils import is_allowed_product_url

    # Naver-like but not in list — e.g. typo domain.
    assert not is_allowed_product_url("https://naver.com.evil.example/p/1")
    assert not is_allowed_product_url("https://coupang.com/p/1")


def test_allowlist_env_override_replaces_defaults(monkeypatch):
    """ALLOWED_PRODUCT_HOSTS fully replaces defaults — operator opts into risk."""
    monkeypatch.setenv("ALLOWED_PRODUCT_HOSTS", "coupang.com, 11st.co.kr")
    from shopping_mcp.utils import is_allowed_product_url

    assert is_allowed_product_url("https://coupang.com/p/1")
    assert is_allowed_product_url("https://www.11st.co.kr/x")
    assert not is_allowed_product_url("https://smartstore.naver.com/p/1")


# ── Tool-level enforcement ───────────────────────────────────────────────────

def test_get_product_detail_rejects_non_allowlist_url(monkeypatch):
    """Tool entrypoint must block before touching the browser."""
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.server import get_product_detail

    result = get_product_detail(url="http://192.168.1.1/")

    assert "error" in result
    assert "allow" in result["error"].lower() or "not permitted" in result["error"].lower()


def test_capture_product_page_rejects_non_allowlist_url(monkeypatch):
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.server import capture_product_page

    result = capture_product_page(url="file:///etc/passwd")

    assert "error" in result
    assert "allow" in result["error"].lower() or "not permitted" in result["error"].lower()


# ── Parameter clamping ──────────────────────────────────────────────────────

def test_clamp_wait_seconds_caps_large_values():
    """An attacker with one request must not be able to park the single slot
    for hours by passing wait_seconds=99999.
    """
    from shopping_mcp.server import _clamp_wait_seconds, MAX_WAIT_SECONDS

    assert _clamp_wait_seconds(99999) == MAX_WAIT_SECONDS
    assert _clamp_wait_seconds(MAX_WAIT_SECONDS + 0.1) == MAX_WAIT_SECONDS


def test_clamp_wait_seconds_rejects_negative():
    from shopping_mcp.server import _clamp_wait_seconds

    assert _clamp_wait_seconds(-5) == 0.0


def test_clamp_wait_seconds_preserves_reasonable_values():
    from shopping_mcp.server import _clamp_wait_seconds

    assert _clamp_wait_seconds(3.5) == 3.5
    assert _clamp_wait_seconds(0) == 0


def test_clamp_max_chars_caps_large_values():
    """max_description_chars is user-controlled output size; cap it so one
    request can't force the server to ship huge payloads over the MCP wire.
    """
    from shopping_mcp.server import _clamp_max_chars, MAX_DESCRIPTION_CHARS

    assert _clamp_max_chars(10_000_000) == MAX_DESCRIPTION_CHARS
    assert _clamp_max_chars(0) == 1  # must allow at least 1 char


def test_clamp_max_chars_preserves_reasonable_values():
    from shopping_mcp.server import _clamp_max_chars

    assert _clamp_max_chars(6000) == 6000


# ── Bearer token auth ───────────────────────────────────────────────────────

def test_auth_accepts_matching_bearer_token():
    """Constant-time match against configured token passes."""
    from shopping_mcp.asgi import _is_request_authorized

    assert _is_request_authorized("secret-token", "Bearer secret-token") is True


def test_auth_rejects_missing_header():
    from shopping_mcp.asgi import _is_request_authorized

    assert _is_request_authorized("secret-token", "") is False
    assert _is_request_authorized("secret-token", None) is False


def test_auth_rejects_wrong_token():
    from shopping_mcp.asgi import _is_request_authorized

    assert _is_request_authorized("secret-token", "Bearer other") is False


def test_auth_rejects_missing_bearer_prefix():
    """Raw token without 'Bearer ' prefix must not authenticate — RFC 6750."""
    from shopping_mcp.asgi import _is_request_authorized

    assert _is_request_authorized("secret-token", "secret-token") is False


def test_auth_rejects_case_mismatch_on_scheme_prefix():
    """Treat prefix check strictly — avoid 'bearer ' lowercase bypass surprises."""
    from shopping_mcp.asgi import _is_request_authorized

    # Current implementation matches the RFC-canonical 'Bearer ' (capital B).
    # Document the chosen strictness; relax later if clients need it.
    assert _is_request_authorized("secret-token", "bearer secret-token") is False


# ── Debug capture rotation ──────────────────────────────────────────────────

def test_prune_capture_dir_keeps_only_most_recent(tmp_path):
    """Otherwise an attacker calling capture_product_page in a loop fills the
    Pi SD card. Oldest captures are removed first.
    """
    from shopping_mcp.utils import prune_capture_dir

    # Create 7 capture-style subdirectories, each with a file inside.
    names = [
        "20260101-010101-a.example.com",
        "20260101-020202-b.example.com",
        "20260101-030303-c.example.com",
        "20260101-040404-d.example.com",
        "20260101-050505-e.example.com",
        "20260101-060606-f.example.com",
        "20260101-070707-g.example.com",
    ]
    for name in names:
        d = tmp_path / name
        d.mkdir()
        (d / "page.html").write_text("x")

    prune_capture_dir(tmp_path, keep=3)

    survivors = sorted(p.name for p in tmp_path.iterdir())
    # Last 3 (lexicographic = chronological here) must remain.
    assert survivors == names[-3:]


def test_prune_capture_dir_noop_when_under_limit(tmp_path):
    from shopping_mcp.utils import prune_capture_dir

    (tmp_path / "20260101-010101-x").mkdir()
    (tmp_path / "20260101-020202-y").mkdir()

    prune_capture_dir(tmp_path, keep=5)

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "20260101-010101-x",
        "20260101-020202-y",
    ]


def test_prune_capture_dir_ignores_stray_files(tmp_path):
    """Pruning only touches directories that look like captures. Stray files
    (e.g. a user note the operator left in debug_captures/) must be kept.
    """
    from shopping_mcp.utils import prune_capture_dir

    (tmp_path / "20260101-010101-a").mkdir()
    (tmp_path / "20260101-020202-b").mkdir()
    (tmp_path / "README.txt").write_text("operator notes")

    prune_capture_dir(tmp_path, keep=1)

    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert "README.txt" in remaining
    assert "20260101-020202-b" in remaining
    assert "20260101-010101-a" not in remaining
