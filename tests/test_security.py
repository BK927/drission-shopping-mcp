from __future__ import annotations

from pathlib import Path


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


# ── URL parser-differential defense ─────────────────────────────────────────

def test_allowlist_blocks_backslash_smuggle(monkeypatch):
    """Python's urlparse reads 'http://evil.com\\@smartstore.naver.com/' as
    host=smartstore.naver.com, but Chromium (WHATWG) rewrites \\ to / and
    navigates to evil.com. The allowlist MUST reject such URLs outright.
    """
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.utils import is_allowed_product_url

    assert not is_allowed_product_url("http://evil.com\\@smartstore.naver.com/")


def test_allowlist_blocks_whitespace_and_null_in_url(monkeypatch):
    """Tab/newline/null/space in a URL are either silently stripped or
    treated differently by Python vs Chromium. Reject at the raw-string
    level rather than trust either parser.
    """
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.utils import is_allowed_product_url

    assert not is_allowed_product_url("http://smartstore.naver.com\t/x")
    assert not is_allowed_product_url("http://smartstore.naver.com\n/x")
    assert not is_allowed_product_url("http://smartstore.naver.com\r/x")
    assert not is_allowed_product_url("http://smartstore.naver.com\x00/x")
    assert not is_allowed_product_url("http://smartstore.naver.com /x")


def test_canonicalize_returns_url_without_userinfo_and_fragment(monkeypatch):
    """canonicalize_product_url must strip userinfo and fragment so what we
    hand to Chromium matches what we just validated. Also must drop bytes
    that could split parser interpretations later.
    """
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.utils import canonicalize_product_url

    # userinfo stripped, fragment stripped, path kept, query kept
    canonical = canonicalize_product_url(
        "https://user:pw@smartstore.naver.com/a/b?q=1#frag"
    )
    assert canonical == "https://smartstore.naver.com/a/b?q=1"


def test_canonicalize_lowercases_scheme_and_host(monkeypatch):
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.utils import canonicalize_product_url

    assert canonicalize_product_url(
        "HTTPS://SMARTSTORE.NAVER.COM/p/1"
    ) == "https://smartstore.naver.com/p/1"


def test_canonicalize_returns_none_for_backslash_url(monkeypatch):
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.utils import canonicalize_product_url

    assert canonicalize_product_url(
        "http://evil.com\\@smartstore.naver.com/"
    ) is None


def test_canonicalize_keeps_port_when_present(monkeypatch):
    monkeypatch.setenv("ALLOWED_PRODUCT_HOSTS", "localdev.example")
    from shopping_mcp.utils import canonicalize_product_url

    assert canonicalize_product_url(
        "http://localdev.example:8080/p"
    ) == "http://localdev.example:8080/p"


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


def test_auth_rejects_non_ascii_token_without_raising():
    """hmac.compare_digest raises TypeError on non-ASCII str inputs; that used
    to surface as a 500 with a traceback in journald. Guard before the call.
    """
    from shopping_mcp.asgi import _is_request_authorized

    # Just assert it returns False rather than raising.
    assert _is_request_authorized("secret-token", "Bearer sécret") is False
    assert _is_request_authorized("secret-token", "Bearer 한글토큰") is False


# ── Debug directory name sanitization ──────────────────────────────────────

def test_safe_host_for_dirname_drops_suspicious_chars():
    """Only [a-zA-Z0-9.-] survive. Anything else (null, %2f, spaces,
    backslashes, colons) becomes an underscore so the directory name is
    predictable and won't crash mkdir.
    """
    from shopping_mcp.utils import safe_host_for_dirname

    assert safe_host_for_dirname("smartstore.naver.com") == "smartstore.naver.com"
    assert safe_host_for_dirname("host\x00evil") == "host_evil"
    # '%' is dropped to '_' but digits/letters ('2f') survive — that's fine
    # as long as path separators ('/', '\\') can never appear.
    assert safe_host_for_dirname("..%2f..%2f") == ".._2f.._2f"
    assert safe_host_for_dirname("") == "page"
    assert safe_host_for_dirname(None) == "page"


# ── Capture size cap ────────────────────────────────────────────────────────

def test_save_debug_truncates_large_html(tmp_path, monkeypatch):
    """A malicious page returning 100 MB of HTML cannot balloon disk usage.
    50 rotated captures × 100 MB = 5 GB — not acceptable on an SD card.
    """
    monkeypatch.setenv("DEBUG_CAPTURE_DIR", str(tmp_path))
    from shopping_mcp.detail_extractor import ProductDetailExtractor

    class FakePage:
        def get_screenshot(self, _path):
            pass

    ext = ProductDetailExtractor()
    big_html = "x" * (5 * 1024 * 1024)  # 5 MB

    result = ext._save_debug("https://smartstore.naver.com/x", big_html, FakePage())

    html_path = Path(result["html_path"])
    assert html_path.exists()
    # File must be no larger than the documented cap (2 MB).
    from shopping_mcp.detail_extractor import ProductDetailExtractor as _PDE
    assert html_path.stat().st_size <= _PDE.MAX_DEBUG_HTML_BYTES


# ── Chromium hardening flags ────────────────────────────────────────────────

def _captured_args(monkeypatch) -> list[str]:
    """Spin up BrowserConfig+Manager and capture the set_argument calls made
    against a fake ChromiumOptions. Avoids needing a real Chromium to test
    that we emit hardening flags.
    """
    from shopping_mcp.browser import BrowserManager

    calls: list[str] = []

    class FakeOptions:
        def set_argument(self, arg):
            calls.append(arg)

        # The real code also probes for these methods; make them no-op.
        def headless(self, *_a, **_kw):
            pass

        def set_user_data_path(self, _path):
            pass

        def set_browser_path(self, _path):
            pass

    # Force a known set of options off so we assert on what _build_options
    # adds rather than what the env brings in.
    monkeypatch.delenv("DP_USER_DATA_DIR", raising=False)
    monkeypatch.delenv("DP_BROWSER_PATH", raising=False)
    monkeypatch.setattr(
        "shopping_mcp.browser.BrowserManager._build_options",
        lambda self: _real_build_options(self, FakeOptions(), calls),
    )
    BrowserManager()._build_options()
    return calls


def _real_build_options(manager, co, _calls):
    """Re-run the real _build_options logic but against the fake options
    object. We patch this in via monkeypatch.setattr on the class.
    """
    # Mirror browser.BrowserManager._build_options without importing
    # ChromiumOptions — the fake already exposes the same surface.
    if manager.config.headless:
        if hasattr(co, "headless"):
            try:
                co.headless(True)
            except TypeError:
                co.headless()
        else:
            co.set_argument("--headless=new")
    if manager.config.no_sandbox:
        co.set_argument("--no-sandbox")
    for arg in (
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
    ):
        co.set_argument(arg)
    for arg in manager._hardening_args():
        co.set_argument(arg)
    return co


def test_chromium_hardening_flags_present(monkeypatch):
    """Attack-surface reduction flags must be emitted every time we build
    ChromiumOptions. Missing flags were let chromium pull optional features
    with their own CVEs.
    """
    from shopping_mcp.browser import BrowserManager

    expected = {
        "--disable-extensions",
        "--disable-plugins",
        "--disable-sync",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-component-update",
    }

    args = BrowserManager()._hardening_args()
    missing = expected - set(args)
    assert not missing, f"missing hardening flags: {missing}"


def test_host_resolver_rules_matches_allowlist(monkeypatch):
    """--host-resolver-rules should mirror the allowlist so Chromium itself
    won't resolve anything off-list — catches redirect-to-internal-IP too.
    """
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.browser import BrowserManager

    rules_arg = next(
        (a for a in BrowserManager()._hardening_args()
         if a.startswith("--host-resolver-rules=")),
        None,
    )
    assert rules_arg is not None, "missing --host-resolver-rules flag"
    # Must at minimum contain 'naver.com' and map unknown hosts to NOTFOUND.
    assert "NOTFOUND" in rules_arg
    assert "naver.com" in rules_arg


# ── Post-navigation URL re-check ────────────────────────────────────────────

def test_extract_aborts_when_final_url_leaves_allowlist(monkeypatch):
    """A 302 (or meta-refresh, or JS nav) from an allowlisted page to an off-
    list host must not return scraped content. Otherwise a compromised Naver
    store page can pivot the browser anywhere and leak the result.
    """
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.detail_extractor import ProductDetailExtractor

    class FakePage:
        html = "<html></html>"
        title = ""
        # Navigation landed at an off-allowlist URL (attacker redirect target).
        url = "http://192.168.1.1/leaked"

        def get(self, _url):
            pass

        def run_js(self, _script):
            return "{}"

        def get_screenshot(self, _path):
            pass

    class FakeBrowser:
        def get_page(self):
            return FakePage()

        def reset(self):
            pass

    ext = ProductDetailExtractor(browser=FakeBrowser())
    result = ext.extract("https://smartstore.naver.com/start", wait_seconds=0)

    assert "error" in result
    assert "redirect" in result["error"].lower() or "final url" in result["error"].lower()


def test_extract_succeeds_when_final_url_stays_on_allowlist(monkeypatch):
    """Benign case: final page.url is still on the allowlist (same origin or
    whitelisted redirect). Extraction must proceed normally.
    """
    monkeypatch.delenv("ALLOWED_PRODUCT_HOSTS", raising=False)
    from shopping_mcp.detail_extractor import ProductDetailExtractor

    class FakePage:
        html = "<html><head><title>ok</title></head><body></body></html>"
        title = "ok"
        url = "https://smartstore.naver.com/start/real"

        def get(self, _url):
            pass

        def run_js(self, _script):
            return "{}"

        def get_screenshot(self, _path):
            pass

    class FakeBrowser:
        def get_page(self):
            return FakePage()

        def reset(self):
            pass

    ext = ProductDetailExtractor(browser=FakeBrowser())
    result = ext.extract("https://smartstore.naver.com/start", wait_seconds=0)

    assert "error" not in result
    assert result.get("source_url") == "https://smartstore.naver.com/start"


# ── Fail-closed bind host ───────────────────────────────────────────────────

def test_resolve_bind_host_keeps_public_when_token_set(monkeypatch):
    """Operator deliberately set both a token AND FASTMCP_HOST=0.0.0.0 — fine,
    they opted into the risk with auth in place.
    """
    monkeypatch.setenv("MCP_AUTH_TOKEN", "s")
    monkeypatch.setenv("FASTMCP_HOST", "0.0.0.0")
    from shopping_mcp.asgi import _resolve_bind_host

    assert _resolve_bind_host() == "0.0.0.0"


def test_resolve_bind_host_forces_loopback_when_token_empty(monkeypatch):
    """Token unset → public bind is refused. A forgotten token after copying
    .env.example must NOT silently expose /mcp to the world.
    """
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("FASTMCP_HOST", "0.0.0.0")
    from shopping_mcp.asgi import _resolve_bind_host

    assert _resolve_bind_host() == "127.0.0.1"


def test_resolve_bind_host_default_is_loopback(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("FASTMCP_HOST", raising=False)
    from shopping_mcp.asgi import _resolve_bind_host

    assert _resolve_bind_host() == "127.0.0.1"


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
