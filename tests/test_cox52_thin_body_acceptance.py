"""COX-52 acceptance — 500-byte HTML payload trips empty_response.

Three tests that mirror the acceptance checklist on issue #91:

1. ``site_text_trafilatura`` (Attempt 1) — a ~500-byte homepage HTML
   extracts to well under the v0.4.0 1024-byte floor. Provider row must
   be ``status: failed`` with ``error: "empty_response"`` instead of the
   pre-fix silent-success (the prose cleared the v0.3.0 64-byte floor).
2. ``smart_proxy_http`` (Attempt 2) — same ~500-byte recovery body
   through the smart-proxy recovery path. The proxy itself returns
   ``status: ok`` with bytes, but the orchestrator's empty-response
   gate in ``core._attempt_smart_proxy_recovery`` now tags the proxy
   row ``failed`` with ``error: "empty_response"`` under the new floor.
3. Orchestrator envelope — top-level ``status: degraded``,
   ``error.code: "empty_response"``, actionable ``suggestion``.

These are the FM-7 thin-body cases the partner-integration validation
measured at 19.6 % of 209 sites (`research/2026-04-22-v0.2-joel-
integration-validation.md` §3). They surfaced as ``status: ok`` on
v0.3.0; v0.4.0 raises the floor 64 → 1024 so they surface honestly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar, Literal, cast

from companyctx import core
from companyctx.providers.base import FetchContext, ProviderBase
from companyctx.providers.site_text_trafilatura import Provider as TrafilaturaProvider
from companyctx.schema import (
    ProviderRunMetadata,
    SiteSignals,
)

FIXED_WHEN = datetime(2026, 4, 20, tzinfo=timezone.utc)

# Realistic ~500-byte homepage for a virtual-staging studio. Extracts to
# ~370 UTF-8 bytes under trafilatura — above the v0.3.0 64-byte floor
# (would have silently passed) but well under the v0.4.0 1024-byte
# floor (now trips empty_response). Matches the FM-7 thin-body shape
# the partner validation flagged.
THIN_HOMEPAGE_HTML = (
    "<!DOCTYPE html><html><head><title>Acme Virtual Staging</title></head>"
    "<body><h1>Acme Virtual Staging</h1><p>Our boutique virtual staging "
    "studio serves Atlanta and Charlotte metro real-estate agents with "
    "next-day turnaround on empty-listing photography. Browse the gallery "
    "to see recent before-and-after work across townhomes, lofts, and "
    "suburban single-family listings. Book a consult through the contact "
    "form above; custom quotes available for bulk orders over twenty "
    "listings.</p></body></html>"
)


def _reg(**mapping: type) -> dict[str, type[ProviderBase]]:
    return cast("dict[str, type[ProviderBase]]", dict(mapping))


def _write_thin_fixture(tmp_path: Path, slug: str) -> None:
    site_dir = tmp_path / slug
    site_dir.mkdir()
    (site_dir / "homepage.html").write_text(THIN_HOMEPAGE_HTML, encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. site_text_trafilatura (Attempt 1)
# ---------------------------------------------------------------------------


def test_site_text_trafilatura_500byte_payload_emits_empty_response(tmp_path: Path) -> None:
    """Zero-key provider: ~500-byte HTML → ``status: failed`` + ``empty_response``.

    Pre-v0.4.0 this payload cleared the 64-byte floor and the provider
    row was ``status: ok``. Under the v0.4.0 1024-byte floor the same
    payload now surfaces the honest failed row. Acceptance gate from
    COX-52 / issue #91.
    """
    slug = "fm7thin1"
    _write_thin_fixture(tmp_path, slug)

    signals, meta = TrafilaturaProvider().fetch(
        f"{slug}.example",
        ctx=FetchContext(
            user_agent="test",
            timeout_s=1.0,
            ignore_robots=False,
            mock=True,
            fixtures_dir=str(tmp_path),
        ),
    )
    assert signals is None
    assert meta.status == "failed"
    assert meta.error == "empty_response"


# ---------------------------------------------------------------------------
# 2. smart_proxy_http (Attempt 2) — exercised through the orchestrator so
#    the shared empty-response gate on recovered bytes is in scope.
# ---------------------------------------------------------------------------


class _BlockedPrimary:
    """Forces the waterfall into Attempt 2 so the proxy's recovery body
    is what the empty-response gate runs against."""

    slug: ClassVar[str] = "site_text_blocked"
    category: ClassVar[Literal["site_text"]] = "site_text"
    cost_hint: ClassVar[Literal["free"]] = "free"
    version: ClassVar[str] = "0.1.0"

    def fetch(
        self, site: str, *, ctx: FetchContext
    ) -> tuple[SiteSignals | None, ProviderRunMetadata]:
        return None, ProviderRunMetadata(
            status="failed",
            latency_ms=0,
            error="blocked_by_antibot (HTTP 403)",
            provider_version=self.version,
        )


class _ThinBodyProxy:
    """Smart-proxy that returns a ~500-byte homepage HTML — the exact FM-7
    thin-body class the v0.4.0 floor raise targets."""

    slug: ClassVar[str] = "smart_proxy_thin"
    category: ClassVar[Literal["smart_proxy"]] = "smart_proxy"
    cost_hint: ClassVar[Literal["per-call"]] = "per-call"
    version: ClassVar[str] = "0.1.0"

    def fetch(self, url: str, *, ctx: FetchContext) -> tuple[bytes | None, ProviderRunMetadata]:
        return THIN_HOMEPAGE_HTML.encode("utf-8"), ProviderRunMetadata(
            status="ok",
            latency_ms=1,
            provider_version=self.version,
        )


def test_smart_proxy_http_500byte_recovery_emits_empty_response() -> None:
    """Smart-proxy recovery: ~500-byte recovered body → proxy row tagged
    ``empty_response``. Mirrors the Attempt-1 check so Attempt 2 cannot
    launder a thin body onto the envelope. Acceptance gate from COX-52 /
    issue #91.
    """
    env = core.run(
        "any.example",
        mock=True,
        providers=_reg(
            site_text_blocked=_BlockedPrimary,
            smart_proxy_thin=_ThinBodyProxy,
        ),
        fetched_at=FIXED_WHEN,
    )
    proxy_row = env.provenance["smart_proxy_thin"]
    assert proxy_row.status == "failed"
    assert proxy_row.error == "empty_response"


# ---------------------------------------------------------------------------
# 3. Orchestrator envelope
# ---------------------------------------------------------------------------


def test_orchestrator_thin_extraction_lands_as_degraded_empty_response(tmp_path: Path) -> None:
    """Top-level envelope on a ~500-byte homepage lands as:
    ``status: degraded`` + ``error.code: "empty_response"`` + actionable
    ``suggestion`` naming the HTTP 200 + browser hint. Full acceptance
    shape from COX-52 / issue #91.
    """
    slug = "fm7thin2"
    _write_thin_fixture(tmp_path, slug)

    env = core.run(
        f"{slug}.example",
        mock=True,
        fixtures_dir=tmp_path,
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "degraded"
    assert env.error is not None
    assert env.error.code == "empty_response"
    assert env.error.suggestion is not None
    assert "HTTP 200" in env.error.suggestion
    # Pages slot never populated on a thin-body failure.
    assert env.data.pages is None
