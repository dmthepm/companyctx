"""Provider contract.

Hard rules (enforced by tests in M2/M3):

- Providers **never raise uncaught**. Every failure mode maps to
  ``ProviderRunMetadata.status in {"degraded", "failed", "not_configured"}``.
- Providers declare a ``cost_hint`` so ``companyctx providers list`` can
  surface the cost surface before integrators wire them.
- Providers do not import each other (lint enforces this in CI).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol, runtime_checkable

from companyctx.schema import ProviderRunMetadata, ProviderStatus

ProviderCategory = Literal[
    "site_text",
    "site_meta",
    "reviews",
    "social_discovery",
    "social_counts",
    "signals",
    "mentions",
    "smart_proxy",
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
    mock: bool = False
    fixtures_dir: str | None = None


@runtime_checkable
class ProviderBase(Protocol):
    """Structural contract for a provider plugin."""

    slug: ClassVar[str]
    category: ClassVar[ProviderCategory]
    cost_hint: ClassVar[CostHint]
    version: ClassVar[str]

    def fetch(
        self,
        site: str,
        *,
        ctx: FetchContext,
    ) -> tuple[object | None, ProviderRunMetadata]:
        """Run the provider for one site. Must never raise."""
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
