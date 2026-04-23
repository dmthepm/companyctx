"""Tests for the vendor-agnostic ``smart_proxy_http`` provider + waterfall wiring.

Covers the Slice B1 acceptance from #6:

- Env-unset → ``not_configured`` row with an actionable ``error`` naming
  ``COMPANYCTX_SMART_PROXY_URL``.
- Env-set + ``--mock`` + ``homepage.html`` present → ``(bytes, ok)``.
- Misconfig paths (bad slug, missing fixture, network raise, vendor 4xx/5xx)
  map to ``failed`` metadata, never raise.
- Orchestrator waterfall: zero-key blocked + smart-proxy configured +
  fixture's ``homepage.html`` present → top-level ``ok`` (recovery).
- Orchestrator waterfall: zero-key blocked + smart-proxy env unset →
  top-level ``partial`` with ``error.suggestion`` pointing at the env var.
- Orchestrator waterfall: zero-key blocked + smart-proxy env set but vendor
  errors → top-level ``degraded``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar, Literal, cast

import pytest
from curl_cffi import requests
from typer.testing import CliRunner

from companyctx import core
from companyctx.cli import app
from companyctx.http import DEFAULT_TIMEOUT_S, DEFAULT_USER_AGENT
from companyctx.providers.base import FetchContext, ProviderBase
from companyctx.providers.site_text_trafilatura import Provider as TrafilaturaProvider
from companyctx.providers.smart_proxy_base import SmartProxyProvider
from companyctx.providers.smart_proxy_http import (
    ENV_URL,
    ENV_VERIFY,
)
from companyctx.providers.smart_proxy_http import (
    Provider as SmartProxyHttpProvider,
)
from companyctx.schema import Envelope, ProviderRunMetadata

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
FIXED_WHEN = datetime(2026, 4, 20, tzinfo=timezone.utc)


def _reg(**mapping: type) -> dict[str, type[ProviderBase]]:
    return cast("dict[str, type[ProviderBase]]", dict(mapping))


def _ctx(*, mock: bool = False, fixtures_dir: str | None = None) -> FetchContext:
    return FetchContext(
        user_agent=DEFAULT_USER_AGENT,
        timeout_s=DEFAULT_TIMEOUT_S,
        mock=mock,
        fixtures_dir=fixtures_dir,
    )


class _FakeResponse:
    """Mimics ``curl_cffi.requests.Response`` for the streaming fetch path.

    Matches the ``iter_content`` + ``headers`` + ``close`` surface the
    hardened ``_from_network`` relies on (see ``companyctx/security.py``).
    """

    def __init__(
        self,
        status_code: int,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body
        self.headers: dict[str, str] = headers or {}
        self.text = body.decode("utf-8", errors="replace")

    def iter_content(self, chunk_size: int = 8192) -> object:
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def close(self) -> None:
        return None


class _ProxyVendorDown:
    """Stand-in smart-proxy that behaves as if the upstream vendor is down."""

    slug: ClassVar[str] = "proxy_vendor_down"
    category: ClassVar[Literal["smart_proxy"]] = "smart_proxy"
    cost_hint: ClassVar[Literal["per-call"]] = "per-call"
    version: ClassVar[str] = "0.1.0"

    def fetch(
        self,
        url: str,
        *,
        ctx: FetchContext,
    ) -> tuple[bytes | None, ProviderRunMetadata]:
        return None, ProviderRunMetadata(
            status="failed",
            latency_ms=42,
            error="proxy auth/block (HTTP 407)",
            provider_version=self.version,
        )


class _ProxyRecoversSite:
    """Stand-in smart-proxy that returns deterministic recovery bytes."""

    slug: ClassVar[str] = "proxy_recovers_site"
    category: ClassVar[Literal["smart_proxy"]] = "smart_proxy"
    cost_hint: ClassVar[Literal["per-call"]] = "per-call"
    version: ClassVar[str] = "0.1.0"
    # Keep the recovered prose above ``EMPTY_RESPONSE_BYTES`` (COX-44
    # / COX-52, now 1024) so recovery tests stay about the waterfall
    # wiring, not the empty-response gate on Attempt 2.
    RECOVERED_HTML = (
        b"<html><body><h1>Recovered Biz</h1>"
        b"<p>hello via proxy. This recovery body is intentionally long enough to clear "
        b"the v0.3.1 empty-response cutoff of 1024 UTF-8 bytes so the waterfall lands on "
        b"status=ok and this test keeps probing the recovery wiring, not the thin-body "
        b"gate. Recovered Biz is a Portland-based fictional company that has served the "
        b"region for over a decade with a realistic mix of consumer and commercial "
        b"services. Our team of nine delivers work the old-fashioned way: named owners, "
        b"written scopes, no surprises on invoice day.</p>"
        b"<p>We work with homeowners, small businesses, and repeat commercial accounts "
        b"across the metro area. Whether you have used a firm like ours before or this "
        b"is your first project, we walk every new client through the process step by "
        b"step: what to expect, what options exist at your price point, and what we "
        b"would recommend if the job were on our own property. No hard sell, no upsell "
        b"theatre, no contracts you cannot cancel.</p>"
        b"<p>Recovered Biz is fully insured and holds every permit and certification "
        b"the state requires for our trade. Our team collectively brings decades of "
        b"hands-on experience, and we publish before-and-after galleries, customer "
        b"reviews, and project case studies so prospective clients can see the actual "
        b"work and not just marketing renders.</p></body></html>"
    )

    def fetch(
        self,
        url: str,
        *,
        ctx: FetchContext,
    ) -> tuple[bytes | None, ProviderRunMetadata]:
        return self.RECOVERED_HTML, ProviderRunMetadata(
            status="ok",
            latency_ms=88,
            error=None,
            provider_version=self.version,
        )


class _ProxyReturnsNonBytes:
    """Malformed smart-proxy that hands back a string instead of bytes."""

    slug: ClassVar[str] = "proxy_returns_string"
    category: ClassVar[Literal["smart_proxy"]] = "smart_proxy"
    cost_hint: ClassVar[Literal["per-call"]] = "per-call"
    version: ClassVar[str] = "0.1.0"

    def fetch(
        self,
        url: str,
        *,
        ctx: FetchContext,
    ) -> tuple[object | None, ProviderRunMetadata]:
        return "<html/>", ProviderRunMetadata(
            status="ok",
            latency_ms=0,
            error=None,
            provider_version=self.version,
        )


# ---------------------------------------------------------------------------
# Provider-level contract
# ---------------------------------------------------------------------------


def test_smart_proxy_http_satisfies_protocol() -> None:
    assert isinstance(SmartProxyHttpProvider(), SmartProxyProvider)


def test_smart_proxy_http_category_and_cost_hint() -> None:
    assert SmartProxyHttpProvider.category == "smart_proxy"
    assert SmartProxyHttpProvider.cost_hint == "per-call"


def test_env_unset_returns_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_URL, raising=False)
    body, meta = SmartProxyHttpProvider().fetch("https://example.com", ctx=_ctx())
    assert body is None
    assert meta.status == "not_configured"
    assert meta.error is not None
    assert ENV_URL in meta.error
    assert "http://user:pass@host:port" in meta.error


def test_env_empty_string_is_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_URL, "   ")
    _, meta = SmartProxyHttpProvider().fetch("https://example.com", ctx=_ctx())
    assert meta.status == "not_configured"


def test_mock_mode_returns_bytes_when_fixture_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    slug = "recoverfix"
    site_dir = tmp_path / slug
    site_dir.mkdir()
    (site_dir / "homepage.html").write_bytes(b"<html><body>recovered</body></html>")
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")

    body, meta = SmartProxyHttpProvider().fetch(
        f"{slug}.example",
        ctx=_ctx(mock=True, fixtures_dir=str(tmp_path)),
    )
    assert meta.status == "ok"
    assert body == b"<html><body>recovered</body></html>"


def test_mock_mode_missing_fixture_returns_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")
    body, meta = SmartProxyHttpProvider().fetch(
        "nonexistent.example",
        ctx=_ctx(mock=True, fixtures_dir=str(tmp_path)),
    )
    assert body is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "fixture missing" in meta.error


def test_mock_mode_without_fixtures_dir_returns_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")
    body, meta = SmartProxyHttpProvider().fetch(
        "example.com",
        ctx=_ctx(mock=True, fixtures_dir=None),
    )
    assert body is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "fixtures_dir" in meta.error


def test_invalid_slug_returns_failed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")
    body, meta = SmartProxyHttpProvider().fetch(
        "../secrets",
        ctx=_ctx(mock=True, fixtures_dir=str(tmp_path)),
    )
    assert body is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "invalid fixture slug" in meta.error


@pytest.mark.parametrize(
    ("status_code", "needle"),
    [
        (401, "proxy auth/block"),
        (403, "proxy auth/block"),
        (500, "proxy upstream HTTP 500"),
    ],
)
def test_network_non_2xx_maps_to_failed(
    monkeypatch: pytest.MonkeyPatch, status_code: int, needle: str
) -> None:
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")
    monkeypatch.setattr(
        "companyctx.providers.smart_proxy_http.requests.get",
        lambda *args, **kwargs: _FakeResponse(status_code=status_code),
    )
    body, meta = SmartProxyHttpProvider().fetch("https://example.com", ctx=_ctx())
    assert body is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert needle in meta.error


def test_network_raises_maps_to_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")

    def _boom(*args: object, **kwargs: object) -> object:
        raise requests.RequestsError("connection refused")

    monkeypatch.setattr("companyctx.providers.smart_proxy_http.requests.get", _boom)
    body, meta = SmartProxyHttpProvider().fetch("https://example.com", ctx=_ctx())
    assert body is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "network error" in meta.error


def test_network_success_returns_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")
    monkeypatch.setattr(
        "companyctx.providers.smart_proxy_http.requests.get",
        lambda *args, **kwargs: _FakeResponse(200, body=b"<html>ok</html>"),
    )
    body, meta = SmartProxyHttpProvider().fetch("https://example.com", ctx=_ctx())
    assert body == b"<html>ok</html>"
    assert meta.status == "ok"


def test_network_passes_proxy_url_and_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")
    monkeypatch.setenv(ENV_VERIFY, "/etc/ssl/vendor-ca.pem")
    captured: dict[str, object] = {}

    def _capture(*args: object, **kwargs: object) -> _FakeResponse:
        captured.update(kwargs)
        return _FakeResponse(200, body=b"<html/>")

    monkeypatch.setattr("companyctx.providers.smart_proxy_http.requests.get", _capture)
    SmartProxyHttpProvider().fetch("example.com", ctx=_ctx())
    assert captured["proxies"] == {
        "http": "http://user:pass@host:7777",
        "https": "http://user:pass@host:7777",
    }
    assert captured["verify"] == "/etc/ssl/vendor-ca.pem"


# ---------------------------------------------------------------------------
# Waterfall integration
# ---------------------------------------------------------------------------


def _blocked_fixture(tmp_path: Path, slug: str, *, with_homepage: bool) -> None:
    site_dir = tmp_path / slug
    site_dir.mkdir()
    (site_dir / "fixture-block.txt").write_text("blocked_by_antibot (HTTP 403)", encoding="utf-8")
    if with_homepage:
        (site_dir / "homepage.html").write_bytes(
            b"<html><body><h1>Recovered</h1>"
            b"<p>proxy win. The smart-proxy recovered a full homepage body, comfortably "
            b"above the v0.3.1 empty-response cutoff of 1024 UTF-8 bytes. A realistic "
            b"residential-proxy recovery returns the rendered page, not just a shell "
            b"-- the kind of multi-paragraph content an LLM can actually synthesize a "
            b"brief from.</p>"
            b"<p>This prose covers the differentiator, audience, and credentials "
            b"sections the partner's brief pipeline expects to see. It names the "
            b"city, the founding year, and the team-size claim in plain text so the "
            b"downstream synthesis layer never has to infer them from chrome. The "
            b"extra length here is deliberate regression padding against the FM-7 "
            b"thin-body class that COX-52 closed out.</p>"
            b"<p>The fictional business is based in Portland, Oregon, and has been "
            b"operating since 2012. We employ a team of nine across the metro area "
            b"and work with homeowners, small businesses, and repeat commercial "
            b"accounts throughout Multnomah and Washington counties. Our core "
            b"offerings are deliberately generic here so the fixture reads like a "
            b"plausible brochure site and trafilatura returns a realistic body "
            b"above the v0.3.1 thin-body floor.</p>"
            b"<p>Every engagement starts with a site walkthrough and a written "
            b"scope so there are no surprises on invoice day. We publish "
            b"before-and-after galleries, customer reviews, and project case "
            b"studies on the site so prospective clients can see the actual work "
            b"our team has delivered, not just marketing renders. The extra "
            b"paragraphs of prose here simulate a normal residential-proxy "
            b"recovery where the full SSR-rendered page is returned by the "
            b"vendor.</p></body></html>"
        )


def test_waterfall_recovers_when_smart_proxy_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    slug = "recoverfix"
    _blocked_fixture(tmp_path, slug, with_homepage=True)
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")

    env = core.run(
        f"{slug}.example",
        mock=True,
        fixtures_dir=tmp_path,
        providers=_reg(
            site_text_trafilatura=TrafilaturaProvider,
            smart_proxy_http=SmartProxyHttpProvider,
        ),
        fetched_at=FIXED_WHEN,
    )

    assert env.status == "ok"
    assert env.data.pages is not None
    assert "proxy win" in env.data.pages.homepage_text
    # Provenance preserves both attempts: zero-key failed, smart-proxy
    # recovered. The ``error`` / ``suggestion`` stay None since top-level is ok.
    assert env.provenance["site_text_trafilatura"].status == "failed"
    assert env.provenance["smart_proxy_http"].status == "ok"
    assert env.error is None


def test_waterfall_partial_when_smart_proxy_not_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    slug = "unconfiguredfix"
    _blocked_fixture(tmp_path, slug, with_homepage=True)
    monkeypatch.delenv(ENV_URL, raising=False)

    env = core.run(
        f"{slug}.example",
        mock=True,
        fixtures_dir=tmp_path,
        providers=_reg(
            site_text_trafilatura=TrafilaturaProvider,
            smart_proxy_http=SmartProxyHttpProvider,
        ),
        fetched_at=FIXED_WHEN,
    )

    assert env.status == "partial"
    assert env.data.pages is None
    assert env.provenance["site_text_trafilatura"].status == "failed"
    assert env.provenance["smart_proxy_http"].status == "not_configured"
    assert env.error is not None
    assert env.error.suggestion is not None
    # The suggestion should include the env var name somewhere along the chain.
    joined_errors = " ".join(meta.error or "" for meta in env.provenance.values())
    assert ENV_URL in joined_errors


def test_waterfall_degraded_when_proxy_configured_but_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    slug = "proxyfails"
    _blocked_fixture(tmp_path, slug, with_homepage=False)

    env = core.run(
        f"{slug}.example",
        mock=True,
        fixtures_dir=tmp_path,
        providers=_reg(
            site_text_trafilatura=TrafilaturaProvider,
            proxy_vendor_down=_ProxyVendorDown,
        ),
        fetched_at=FIXED_WHEN,
    )

    assert env.status == "degraded"
    assert env.provenance["site_text_trafilatura"].status == "failed"
    assert env.provenance["proxy_vendor_down"].status == "failed"
    assert env.error is not None
    assert env.error.suggestion is not None


def test_waterfall_skips_smart_proxy_when_site_text_ok(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Smart-proxy is only invoked on failure — clean path leaves no row."""
    slug = "cleanfix"
    site_dir = tmp_path / slug
    site_dir.mkdir()
    # Body clears the v0.3.1 ``EMPTY_RESPONSE_BYTES`` cutoff (1024) so
    # this test stays about the smart-proxy skip path, not the empty-
    # response check.
    (site_dir / "homepage.html").write_bytes(
        b"<html><body><h1>Clean Biz</h1>"
        b"<p>hello from the clean-path homepage. This body is intentionally long "
        b"enough to clear the v0.3.1 empty-response cutoff of 1024 UTF-8 bytes so "
        b"the zero-key provider completes with status=ok and the smart-proxy never "
        b"has to run.</p>"
        b"<p>The point of the test is the skip path: when Attempt 1 succeeds, "
        b"Attempt 2 stays off provenance entirely. Adding enough prose to clear "
        b"the FM-7 floor keeps that invariant honest without changing the shape "
        b"of the test.</p>"
        b"<p>The rest of this paragraph is padding prose describing a fictional "
        b"Portland business, its service mix, and its credentials, so the "
        b"trafilatura extractor returns a realistic body rather than a "
        b"one-sentence stub. The business has operated in the metro area for "
        b"over a decade and serves homeowners and small commercial accounts.</p>"
        b"<p>Our team of nine covers everything from initial consultation through "
        b"completion with written scopes and named owners. Every engagement "
        b"starts with a site walkthrough and a written scope so there are no "
        b"surprises on invoice day. We publish before-and-after galleries, "
        b"customer reviews, and project case studies on the site so prospective "
        b"clients can see the actual work our team has delivered, not just "
        b"marketing renders.</p></body></html>"
    )
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")

    env = core.run(
        f"{slug}.example",
        mock=True,
        fixtures_dir=tmp_path,
        providers=_reg(
            site_text_trafilatura=TrafilaturaProvider,
            smart_proxy_http=SmartProxyHttpProvider,
        ),
        fetched_at=FIXED_WHEN,
    )

    assert env.status == "ok"
    assert "smart_proxy_http" not in env.provenance
    assert env.provenance["site_text_trafilatura"].status == "ok"


def test_waterfall_handles_non_bytes_smart_proxy_body(tmp_path: Path) -> None:
    """Malformed proxy → row downgraded to failed, top-level stays degraded."""
    slug = "malformedfix"
    _blocked_fixture(tmp_path, slug, with_homepage=False)

    env = core.run(
        f"{slug}.example",
        mock=True,
        fixtures_dir=tmp_path,
        providers=_reg(
            site_text_trafilatura=TrafilaturaProvider,
            proxy_returns_string=_ProxyReturnsNonBytes,
        ),
        fetched_at=FIXED_WHEN,
    )

    assert env.status == "degraded"
    assert env.provenance["proxy_returns_string"].status == "failed"
    assert env.provenance["proxy_returns_string"].error is not None
    assert "non-bytes body" in env.provenance["proxy_returns_string"].error


def test_cli_providers_list_shows_smart_proxy_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env-unset path: smart_proxy_http surfaces as ``not_configured`` in the text table."""
    monkeypatch.delenv(ENV_URL, raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["providers", "list"])
    assert result.exit_code == 0, result.stdout
    assert "smart_proxy_http" in result.stdout
    assert "smart-proxy" in result.stdout
    assert "per-call" in result.stdout
    assert "not_configured" in result.stdout
    assert f"missing env: {ENV_URL}" in result.stdout


def test_cli_providers_list_json_shape_tracks_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """``providers list --json`` flips smart_proxy_http's status when the env var is set."""
    runner = CliRunner()

    monkeypatch.delenv(ENV_URL, raising=False)
    unset = runner.invoke(app, ["providers", "list", "--json"])
    assert unset.exit_code == 0, unset.stdout
    payload = json.loads(unset.stdout)
    proxy_row = next(row for row in payload if row["slug"] == "smart_proxy_http")
    assert proxy_row["tier"] == "smart-proxy"
    assert proxy_row["status"] == "not_configured"
    assert proxy_row["reason"] == f"missing env: {ENV_URL}"

    monkeypatch.setenv(ENV_URL, "http://user:pass@host:8080")
    ready = runner.invoke(app, ["providers", "list", "--json"])
    assert ready.exit_code == 0, ready.stdout
    ready_payload = json.loads(ready.stdout)
    ready_row = next(row for row in ready_payload if row["slug"] == "smart_proxy_http")
    assert ready_row["status"] == "ready"
    assert ready_row["reason"] is None


def test_cli_fetch_blocked_fixture_partial_without_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end via the CLI — blocked fixture + env unset → partial, exit 0."""
    slug = "clifix01"
    _blocked_fixture(tmp_path, slug, with_homepage=True)
    monkeypatch.delenv(ENV_URL, raising=False)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "fetch",
            f"{slug}.example",
            "--mock",
            "--json",
            "--fixtures-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    env = Envelope.model_validate(json.loads(result.stdout))
    assert env.status == "partial"


def test_cli_fetch_blocked_fixture_ok_with_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end via the CLI — blocked fixture + env set → ok, exit 0.

    GOOGLE_PLACES_API_KEY stays unset so the Places provider skips
    invocation and the envelope status reflects the smart-proxy
    recovery outcome on its own.
    """
    slug = "clifix02"
    _blocked_fixture(tmp_path, slug, with_homepage=True)
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "fetch",
            f"{slug}.example",
            "--mock",
            "--json",
            "--fixtures-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    env = Envelope.model_validate(json.loads(result.stdout))
    assert env.status == "ok"
    assert env.data.pages is not None
    assert env.provenance["site_text_trafilatura"].status == "failed"
    assert env.provenance["smart_proxy_http"].status == "ok"
    assert "reviews_google_places" not in env.provenance


# ---------------------------------------------------------------------------
# Robots.txt enforcement on the smart-proxy path (regression for review #1)
# ---------------------------------------------------------------------------


def test_smart_proxy_http_honors_robots_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Robots-disallow on the target URL → failed row, never fires the proxy."""
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")
    monkeypatch.setattr(
        "companyctx.providers.smart_proxy_http.is_allowed",
        lambda url, user_agent: False,
    )

    def _boom(*args: object, **kwargs: object) -> _FakeResponse:
        raise AssertionError("proxy must not be contacted when robots disallows")

    monkeypatch.setattr("companyctx.providers.smart_proxy_http.requests.get", _boom)

    body, meta = SmartProxyHttpProvider().fetch("https://example.com", ctx=_ctx())
    assert body is None
    assert meta.status == "failed"
    assert meta.error == "blocked_by_robots"


def test_smart_proxy_http_ignore_robots_bypasses_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """With ``ctx.ignore_robots=True`` the robots check is skipped, same as zero-key."""
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")
    monkeypatch.setattr(
        "companyctx.providers.smart_proxy_http.is_allowed",
        lambda url, user_agent: False,
    )
    monkeypatch.setattr(
        "companyctx.providers.smart_proxy_http.requests.get",
        lambda *args, **kwargs: _FakeResponse(200, body=b"<html>proxied</html>"),
    )

    ctx = FetchContext(
        user_agent=DEFAULT_USER_AGENT,
        timeout_s=DEFAULT_TIMEOUT_S,
        ignore_robots=True,
    )
    body, meta = SmartProxyHttpProvider().fetch("https://example.com", ctx=ctx)
    assert body == b"<html>proxied</html>"
    assert meta.status == "ok"


def test_waterfall_does_not_launder_robots_block(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero-key robots-block must not be recovered by smart-proxy.

    The orchestrator short-circuits the retry when the zero-key failure is
    ``blocked_by_robots``; the smart-proxy's own robots check is the
    defense-in-depth second layer (tested above).
    """
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")
    monkeypatch.setattr(
        "companyctx.providers.site_text_trafilatura.is_allowed",
        lambda url, user_agent: False,
    )

    def _boom(*args: object, **kwargs: object) -> _FakeResponse:
        raise AssertionError("smart-proxy network path must not fire on a robots block")

    monkeypatch.setattr("companyctx.providers.smart_proxy_http.requests.get", _boom)

    env = core.run(
        "https://example.com",
        providers=_reg(
            site_text_trafilatura=TrafilaturaProvider,
            smart_proxy_http=SmartProxyHttpProvider,
        ),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "degraded"
    assert env.provenance["site_text_trafilatura"].status == "failed"
    assert env.provenance["site_text_trafilatura"].error == "blocked_by_robots"
    # Orchestrator short-circuits before invoking smart-proxy.
    assert "smart_proxy_http" not in env.provenance


# ---------------------------------------------------------------------------
# Recovery accounting (regression for review #2)
# ---------------------------------------------------------------------------


class _AlwaysFailSiteText:
    slug: ClassVar[str] = "always_fail_site_text"
    category: ClassVar[Literal["site_text"]] = "site_text"
    cost_hint: ClassVar[Literal["free"]] = "free"
    version: ClassVar[str] = "0.1.0"

    def fetch(self, site: str, *, ctx: FetchContext) -> tuple[object | None, ProviderRunMetadata]:
        return None, ProviderRunMetadata(
            status="failed",
            latency_ms=7,
            error="always-fail",
            provider_version=self.version,
        )


class _AlsoFailSiteText:
    slug: ClassVar[str] = "also_fail_site_text"
    category: ClassVar[Literal["site_text"]] = "site_text"
    cost_hint: ClassVar[Literal["free"]] = "free"
    version: ClassVar[str] = "0.1.0"

    def fetch(self, site: str, *, ctx: FetchContext) -> tuple[object | None, ProviderRunMetadata]:
        return None, ProviderRunMetadata(
            status="failed",
            latency_ms=11,
            error="also-fail",
            provider_version=self.version,
        )


def test_recovery_only_suppresses_the_retried_slug() -> None:
    """Multiple failing site_text providers + one proxy-ok → status partial.

    Only the first eligible failing slug (alphabetical:
    ``also_fail_site_text``) gets retried; the orchestrator must not count
    the second failure as recovered.
    """
    env = core.run(
        "example.com",
        providers=_reg(
            also_fail_site_text=_AlsoFailSiteText,
            always_fail_site_text=_AlwaysFailSiteText,
            proxy_recovers_site=_ProxyRecoversSite,
        ),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "partial"
    assert env.provenance["also_fail_site_text"].status == "failed"
    assert env.provenance["always_fail_site_text"].status == "failed"
    assert env.provenance["proxy_recovers_site"].status == "ok"
    # The pages slot was populated by the proxy recovery on the first failure.
    assert env.data.pages is not None


# ---------------------------------------------------------------------------
# site_meta is NOT recoverable (regression for review #3)
# ---------------------------------------------------------------------------


class _FailingSiteMeta:
    """A failing ``site_meta`` provider — must not trigger smart-proxy recovery.

    The recovery extractor produces ``SiteSignals`` (for the ``pages`` slot);
    overlaying that onto a failed ``site_meta`` row would clobber the page
    data from a sibling ``site_text`` provider and attribute the wrong shape
    to the metadata slot.
    """

    slug: ClassVar[str] = "failing_site_meta"
    category: ClassVar[Literal["site_meta"]] = "site_meta"
    cost_hint: ClassVar[Literal["free"]] = "free"
    version: ClassVar[str] = "0.1.0"

    def fetch(self, site: str, *, ctx: FetchContext) -> tuple[object | None, ProviderRunMetadata]:
        return None, ProviderRunMetadata(
            status="failed",
            latency_ms=9,
            error="meta-miss",
            provider_version=self.version,
        )


# ---------------------------------------------------------------------------
# Security guardrails on the proxied path (SSRF, redirect cap, body cap)
# ---------------------------------------------------------------------------


def test_smart_proxy_rejects_non_http_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-HTTP target → ``unsafe_url`` row, proxy never contacted."""
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")

    def _boom(*args: object, **kwargs: object) -> _FakeResponse:
        raise AssertionError("proxy must not fire for unsafe scheme")

    monkeypatch.setattr("companyctx.providers.smart_proxy_http.requests.get", _boom)

    body, meta = SmartProxyHttpProvider().fetch("file:///etc/passwd", ctx=_ctx())
    assert body is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "unsafe_url" in meta.error


def test_smart_proxy_rejects_metadata_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cloud-metadata hostnames are refused before egress through the proxy."""
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")

    def _boom(*args: object, **kwargs: object) -> _FakeResponse:
        raise AssertionError("proxy must not fire for metadata host")

    monkeypatch.setattr("companyctx.providers.smart_proxy_http.requests.get", _boom)

    body, meta = SmartProxyHttpProvider().fetch("http://metadata.google.internal/", ctx=_ctx())
    assert body is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "unsafe_url" in meta.error


def test_smart_proxy_refuses_oversize_body_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ``Content-Length`` above the cap trips before any body is read."""
    from companyctx.security import MAX_RESPONSE_BYTES

    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")
    monkeypatch.setattr(
        "companyctx.providers.smart_proxy_http.requests.get",
        lambda *args, **kwargs: _FakeResponse(
            200, body=b"", headers={"content-length": str(MAX_RESPONSE_BYTES + 1)}
        ),
    )
    body, meta = SmartProxyHttpProvider().fetch("https://example.com", ctx=_ctx())
    assert body is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "response_too_large" in meta.error


def test_smart_proxy_refuses_oversize_body_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    """When content-length is absent or lies, the streaming cap still trips."""
    from companyctx.security import MAX_RESPONSE_BYTES

    big = b"x" * (MAX_RESPONSE_BYTES + 1024)
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")
    monkeypatch.setattr(
        "companyctx.providers.smart_proxy_http.requests.get",
        lambda *args, **kwargs: _FakeResponse(200, body=big),
    )
    body, meta = SmartProxyHttpProvider().fetch("https://example.com", ctx=_ctx())
    assert body is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "response_too_large" in meta.error


def test_smart_proxy_redirect_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A redirect loop is capped at :data:`MAX_REDIRECTS`."""
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")
    monkeypatch.setattr(
        "companyctx.providers.smart_proxy_http.requests.get",
        lambda *args, **kwargs: _FakeResponse(
            302, body=b"", headers={"location": "https://example.com/next"}
        ),
    )
    body, meta = SmartProxyHttpProvider().fetch("https://example.com", ctx=_ctx())
    assert body is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "redirect limit" in meta.error


def test_smart_proxy_rejects_traversal_fixture_slug(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Symlinked fixture escapes are refused by the path-traversal guard."""
    # The slug regex already rejects ``..``; this locks the
    # symlink-resolving fallback (``_safe_fixture_root``) for parity with
    # the zero-key provider's hardening.
    escape_target = tmp_path / "outside"
    escape_target.mkdir()
    (escape_target / "homepage.html").write_bytes(b"<html>escape</html>")
    inside = tmp_path / "inside"
    inside.mkdir()
    (inside / "recoverfix").symlink_to(escape_target)

    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")
    body, meta = SmartProxyHttpProvider().fetch(
        "recoverfix.example",
        ctx=_ctx(mock=True, fixtures_dir=str(inside)),
    )
    assert body is None
    assert meta.status == "failed"
    assert meta.error is not None
    assert "escapes fixtures_dir" in meta.error


def test_site_meta_failure_does_not_trigger_recovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """site_text ok, site_meta fails → pages stays site_text's richer output.

    Without the recovery-category tightening the orchestrator would feed
    proxy bytes into ``SiteSignals`` and overwrite ``pages`` with the
    homepage-only recovery payload. The fix keeps site_meta off the retry
    list entirely.
    """
    slug = "metaok"
    site_dir = tmp_path / slug
    site_dir.mkdir()
    # Body clears ``EMPTY_RESPONSE_BYTES`` (1024, v0.3.1) so the
    # zero-key provider completes with ``ok`` — this test is about
    # site_meta failures not being routed to smart-proxy recovery, not
    # about empty responses.
    (site_dir / "homepage.html").write_bytes(
        b"<html><body><h1>Real Biz</h1>"
        b"<p>full homepage prose. This body is intentionally long enough to clear "
        b"the v0.3.1 empty-response cutoff of 1024 UTF-8 bytes so the zero-key "
        b"provider lands on status=ok and the assertion chain about site_meta not "
        b"triggering recovery stays clean.</p>"
        b"<p>A realistic homepage carries a differentiator paragraph, a "
        b"who-we-serve paragraph, and a credentials paragraph. This filler covers "
        b"all three so the test fixture reads like a plausible small-business "
        b"brochure site and the extractor returns something well above the FM-7 "
        b"thin-body floor.</p>"
        b"<p>Real Biz is a fictional Portland-based company that has operated in "
        b"the metro area for over a decade. We serve homeowners, small "
        b"businesses, and repeat commercial accounts with written scopes and "
        b"named owners on every project. Our team of nine is fully insured and "
        b"licensed across the region we work in.</p>"
        b"<p>Every engagement starts with a site walkthrough and a written scope "
        b"so there are no surprises on invoice day. We publish before-and-after "
        b"galleries, customer reviews, and project case studies on the site so "
        b"prospective clients can see the actual work our team has delivered, "
        b"not just marketing renders. The extra paragraphs of prose here "
        b"simulate a normal SSR-rendered homepage that trafilatura can "
        b"meaningfully extract from.</p></body></html>"
    )
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")

    env = core.run(
        f"{slug}.example",
        mock=True,
        fixtures_dir=tmp_path,
        providers=_reg(
            failing_site_meta=_FailingSiteMeta,
            site_text_trafilatura=TrafilaturaProvider,
            smart_proxy_http=SmartProxyHttpProvider,
        ),
        fetched_at=FIXED_WHEN,
    )

    # site_meta failure should NOT be recovered — smart-proxy stays off.
    assert "smart_proxy_http" not in env.provenance
    assert env.provenance["failing_site_meta"].status == "failed"
    assert env.provenance["site_text_trafilatura"].status == "ok"
    # Pages reflects the site_text payload, not a homepage-only overlay.
    assert env.data.pages is not None
    assert "Real Biz" in env.data.pages.homepage_text
    # Envelope is partial: site_text ok + site_meta failed, no recovery.
    assert env.status == "partial"
