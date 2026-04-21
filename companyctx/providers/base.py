"""Provider contract.

Hard rules (enforced by tests in M2/M3):

- Providers **never raise uncaught**. Every failure mode maps to
  ``ProviderRunMetadata.status in {"degraded", "failed"}``.
- Providers declare a ``cost_hint`` so ``companyctx providers list`` can
  surface the cost surface before integrators wire them.
- Providers do not import each other (lint enforces this in CI).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol

ProviderStatus = Literal["ok", "degraded", "failed", "not_configured"]
ProviderCategory = Literal[
    "site_text",
    "site_meta",
    "reviews",
    "social_discovery",
    "social_counts",
    "signals",
    "mentions",
]
CostHint = Literal["free", "per-call", "per-1k"]


class ProviderError(Exception):
    """Raised internally inside a provider; the framework converts to ``failed`` status.

    Providers themselves should not let this escape — they catch it at their
    boundary and return ``(None, ProviderRunMetadata(status="failed", ...))``.
    """


@dataclass(frozen=True)
class FetchContext:
    """Per-run context passed to every provider invocation."""

    user_agent: str
    timeout_s: float
    ignore_robots: bool = False


@dataclass(frozen=True)
class ProviderRunMetadata:
    """Per-provider provenance row attached to every output envelope."""

    status: ProviderStatus
    latency_ms: int
    error: str | None
    provider_version: str


class ProviderBase(Protocol):
    """Structural contract for a provider plugin.

    Concrete providers in M3 implement this. M1 only locks the shape.
    """

    slug: ClassVar[str]
    category: ClassVar[ProviderCategory]
    cost_hint: ClassVar[CostHint]
    version: ClassVar[str]

    def fetch(
        self,
        domain: str,
        *,
        ctx: FetchContext,
    ) -> tuple[object | None, ProviderRunMetadata]:
        """Run the provider for one domain.

        Returns a 2-tuple of ``(signals_model_or_None, ProviderRunMetadata)``.
        Must never raise an uncaught exception.
        """
        ...


__all__ = [
    "CostHint",
    "FetchContext",
    "ProviderBase",
    "ProviderCategory",
    "ProviderError",
    "ProviderRunMetadata",
    "ProviderStatus",
]
