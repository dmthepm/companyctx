"""Schema round-trip + ``extra=\"forbid\"`` invariants for the envelope."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from companyctx.schema import (
    CompanyContext,
    Envelope,
    HeuristicSignals,
    ProviderRunMetadata,
    ReviewsSignals,
    SiteSignals,
    SocialSignals,
)


def _fixed_dt() -> datetime:
    return datetime(2026, 4, 20, tzinfo=timezone.utc)


def test_envelope_round_trips_through_json() -> None:
    env = Envelope(
        status="ok",
        data=CompanyContext(
            site="example.com",
            fetched_at=_fixed_dt(),
            pages=SiteSignals(
                homepage_text="hi",
                about_text="about",
                services=["a", "b"],
                tech_stack=["WordPress"],
            ),
            reviews=ReviewsSignals(count=10, rating=4.5, source="reviews_google_places"),
            social=SocialSignals(handles={"instagram": "@ex"}),
            signals=HeuristicSignals(team_size_claim="team of 6"),
        ),
        provenance={
            "site_text_trafilatura": ProviderRunMetadata(
                status="ok", latency_ms=12, provider_version="0.1.0"
            )
        },
    )
    serialized = env.model_dump_json()
    reparsed = Envelope.model_validate_json(serialized)
    assert reparsed == env


def test_envelope_rejects_unknown_top_level_field() -> None:
    with pytest.raises(ValidationError):
        Envelope.model_validate(
            {
                "status": "ok",
                "data": {"site": "x", "fetched_at": _fixed_dt().isoformat()},
                "provenance": {},
                "bogus": 1,
            }
        )


def test_company_context_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        CompanyContext.model_validate(
            {"site": "x", "fetched_at": _fixed_dt().isoformat(), "bogus": 1}
        )


def test_site_signals_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        SiteSignals.model_validate({"homepage_text": "x", "bogus": 1})


def test_provider_run_metadata_cost_incurred_defaults_to_zero() -> None:
    meta = ProviderRunMetadata(status="ok", latency_ms=0, provider_version="0.1.0")
    assert meta.cost_incurred == 0


def test_provider_run_metadata_cost_incurred_explicit() -> None:
    meta = ProviderRunMetadata(
        status="ok",
        latency_ms=0,
        provider_version="0.1.0",
        cost_incurred=42,
    )
    assert meta.cost_incurred == 42


def test_provider_run_metadata_is_frozen() -> None:
    meta = ProviderRunMetadata(status="ok", latency_ms=0, provider_version="0.1.0")
    with pytest.raises(ValidationError):
        meta.status = "failed"  # type: ignore[misc]


def test_envelope_partial_requires_error_and_suggestion_shape() -> None:
    env = Envelope(
        status="partial",
        data=CompanyContext(site="x", fetched_at=_fixed_dt()),
        provenance={
            "site_text_trafilatura": ProviderRunMetadata(
                status="failed",
                latency_ms=100,
                error="blocked_by_antibot (HTTP 403)",
                provider_version="0.1.0",
            )
        },
        error="blocked_by_antibot",
        suggestion="configure a smart-proxy provider key or skip this prospect",
    )
    assert env.status == "partial"
    assert env.error == "blocked_by_antibot"
    assert env.suggestion is not None
