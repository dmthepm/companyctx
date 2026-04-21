"""Schema round-trip + ``extra=\"forbid\"`` invariants for the envelope."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from companyctx.schema import (
    CompanyContext,
    Envelope,
    FundingRound,
    HeuristicSignals,
    MediaMention,
    MentionsSignals,
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
            mentions=MentionsSignals(
                items=[
                    MediaMention(
                        title="Award",
                        url="https://example.com/award",
                        source="Example News",
                        kind="award",
                    )
                ]
            ),
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


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            Envelope,
            {
                "status": "ok",
                "data": {"site": "x", "fetched_at": _fixed_dt().isoformat()},
                "provenance": {},
            },
        ),
        (CompanyContext, {"site": "x", "fetched_at": _fixed_dt().isoformat()}),
        (SiteSignals, {"homepage_text": "x"}),
        (ReviewsSignals, {"count": 1, "source": "reviews_google_places"}),
        (SocialSignals, {}),
        (
            MediaMention,
            {
                "title": "Example",
                "url": "https://example.com/press",
                "source": "Example News",
                "kind": "press",
            },
        ),
        (FundingRound, {}),
        (HeuristicSignals, {}),
        (MentionsSignals, {}),
        (
            ProviderRunMetadata,
            {"status": "ok", "latency_ms": 0, "provider_version": "0.1.0"},
        ),
    ],
)
def test_models_reject_unknown_fields(model: type[object], payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**payload, "bogus": 1})  # type: ignore[attr-defined]


def test_provider_run_metadata_cost_incurred_defaults_to_zero() -> None:
    meta = ProviderRunMetadata(status="ok", latency_ms=0, provider_version="0.1.0")
    assert isinstance(meta.cost_incurred, int)
    assert meta.cost_incurred == 0


def test_provider_run_metadata_cost_incurred_explicit() -> None:
    meta = ProviderRunMetadata(
        status="ok",
        latency_ms=0,
        provider_version="0.1.0",
        cost_incurred=42,
    )
    assert isinstance(meta.cost_incurred, int)
    assert meta.cost_incurred == 42


def test_provider_run_metadata_is_frozen() -> None:
    meta = ProviderRunMetadata(status="ok", latency_ms=0, provider_version="0.1.0")
    with pytest.raises(ValidationError):
        meta.status = "failed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "status": "partial",
            "data": {"site": "x", "fetched_at": _fixed_dt().isoformat()},
            "provenance": {},
        },
        {
            "status": "degraded",
            "data": {"site": "x", "fetched_at": _fixed_dt().isoformat()},
            "provenance": {},
            "error": "no providers succeeded",
        },
        {
            "status": "ok",
            "data": {"site": "x", "fetched_at": _fixed_dt().isoformat()},
            "provenance": {},
            "error": "should not be here",
            "suggestion": "should not be here",
        },
    ],
)
def test_envelope_rejects_inconsistent_status_error_and_suggestion(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        Envelope.model_validate(payload)
