"""Pydantic v2 schema — the companyctx JSON contract.

The envelope is the product. Providers are replaceable; this shape is not.
Every model sets ``extra="forbid"`` so schema drift is loud. See
``docs/SCHEMA.md`` for the contract walkthrough and ``docs/SPEC.md`` for the
frozen v0.1 snapshot.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EnvelopeStatus = Literal["ok", "partial", "degraded"]
ProviderStatus = Literal["ok", "degraded", "failed", "not_configured"]
MentionKind = Literal["press", "podcast", "award", "mention"]


class SiteSignals(BaseModel):
    """Homepage-derived observations, extractor-agnostic."""

    model_config = ConfigDict(extra="forbid")

    homepage_text: str
    about_text: str | None = None
    services: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)


class ReviewsSignals(BaseModel):
    """Aggregate review observations from a single source provider."""

    model_config = ConfigDict(extra="forbid")

    count: int
    rating: float | None = None
    source: str


class SocialSignals(BaseModel):
    """Platform handles and (where available) follower counts."""

    model_config = ConfigDict(extra="forbid")

    handles: dict[str, str] = Field(default_factory=dict)
    follower_counts: dict[str, int] = Field(default_factory=dict)


class MediaMention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    source: str
    kind: MentionKind
    date: datetime | None = None


class FundingRound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_type: str | None = None
    amount_usd: int | None = None
    announced_at: datetime | None = None


class HeuristicSignals(BaseModel):
    """Raw, uninferred cross-reference observations."""

    model_config = ConfigDict(extra="forbid")

    team_size_claim: str | None = None
    linkedin_employee_count: int | None = None
    hiring_page_active: bool | None = None
    last_funding_round: FundingRound | None = None
    copyright_year: int | None = None
    last_blog_post_at: datetime | None = None
    tech_vs_claim_mismatches: list[str] = Field(default_factory=list)


class MentionsSignals(BaseModel):
    """Collection wrapper so providers can attach their own source metadata later."""

    model_config = ConfigDict(extra="forbid")

    items: list[MediaMention] = Field(default_factory=list)


class ProviderRunMetadata(BaseModel):
    """Per-provider provenance row attached to every envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ProviderStatus
    latency_ms: int
    error: str | None = None
    provider_version: str
    cost_incurred: int = 0
    """Cost charged by this attempt, in US cents. Zero-key providers stay 0."""


class CompanyContext(BaseModel):
    """Schema payload. Every field except site+fetched_at is optional."""

    model_config = ConfigDict(extra="forbid")

    site: str = Field(..., description="Prospect hostname or URL.")
    fetched_at: datetime = Field(..., description="UTC timestamp of the run.")

    pages: SiteSignals | None = None
    reviews: ReviewsSignals | None = None
    social: SocialSignals | None = None
    signals: HeuristicSignals | None = None
    mentions: list[MediaMention] = Field(default_factory=list)


class Envelope(BaseModel):
    """Top-level JSON contract. Every ``fetch`` run emits exactly one of these."""

    model_config = ConfigDict(extra="forbid")

    status: EnvelopeStatus
    data: CompanyContext
    provenance: dict[str, ProviderRunMetadata] = Field(default_factory=dict)
    error: str | None = None
    suggestion: str | None = None


__all__ = [
    "CompanyContext",
    "Envelope",
    "EnvelopeStatus",
    "FundingRound",
    "HeuristicSignals",
    "MediaMention",
    "MentionKind",
    "MentionsSignals",
    "ProviderRunMetadata",
    "ProviderStatus",
    "ReviewsSignals",
    "SiteSignals",
    "SocialSignals",
]
