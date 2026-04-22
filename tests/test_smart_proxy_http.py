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
  top-level ``partial`` with ``suggestion`` pointing at the env var.
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
    def __init__(self, status_code: int, body: bytes = b"") -> None:
        self.status_code = status_code
        self.content = body
        self.text = body.decode("utf-8", errors="replace")


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
    RECOVERED_HTML = b"<html><body><h1>Recovered Biz</h1><p>hello via proxy</p></body></html>"

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
            b"<html><body><h1>Recovered</h1><p>proxy win</p></body></html>"
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
    assert env.suggestion is None


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
    assert env.suggestion is not None
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
    assert env.suggestion is not None


def test_waterfall_skips_smart_proxy_when_site_text_ok(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Smart-proxy is only invoked on failure — clean path leaves no row."""
    slug = "cleanfix"
    site_dir = tmp_path / slug
    site_dir.mkdir()
    (site_dir / "homepage.html").write_bytes(
        b"<html><body><h1>Clean Biz</h1><p>hello</p></body></html>"
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


def test_cli_providers_list_shows_smart_proxy_http() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["providers", "list"])
    assert result.exit_code == 0, result.stdout
    assert "smart_proxy_http" in result.stdout
    assert "smart_proxy" in result.stdout
    assert "per-call" in result.stdout


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
    """End-to-end via the CLI — blocked fixture + env set → ok, exit 0."""
    slug = "clifix02"
    _blocked_fixture(tmp_path, slug, with_homepage=True)
    monkeypatch.setenv(ENV_URL, "http://user:pass@host:7777")

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
