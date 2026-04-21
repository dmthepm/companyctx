"""Abstract base for SmartProxyProvider plugins.

Attempt 2 of the Deterministic Waterfall (see ``docs/ARCHITECTURE.md``) is
vendor-agnostic. ``companyctx`` ships *the contract*; the user supplies their
own residential-proxy / headless-browser vendor and chooses which one plugs in.

A ``SmartProxyProvider`` is a low-level fetcher: given a URL, it returns the
raw response bytes (or ``None`` on block / failure) plus a
``ProviderRunMetadata`` row. The bytes then flow into the same
``trafilatura`` / ``readability-lxml`` / ``extruct`` chain as the zero-key
path — the schema doesn't know which layer produced them.

This module ships only the interface. The first concrete implementation lands
after issue #15 (envelope + zero-key provider + waterfall) plus an M2 vendor
eval spike. We do not name a vendor in README / ``docs/PROVIDERS.md`` before
that measurement, per the no-vendor-commitments-before-testing rule.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Literal

from companyctx.providers.base import (
    CostHint,
    FetchContext,
    ProviderRunMetadata,
)

SmartProxyCategory = Literal["smart_proxy"]


class SmartProxyProvider(ABC):
    """Abstract smart-proxy fetcher.

    Conforms structurally to ``ProviderBase`` but specializes the ``fetch``
    return type: a smart-proxy hands back raw response *bytes* (for downstream
    parsing by ``trafilatura`` / ``extruct``), not a typed signals model.

    Subclasses MUST set ``slug``, ``cost_hint``, ``version`` and implement
    ``fetch``. ``category`` is fixed at ``"smart_proxy"``.

    **Failure-mode contract.** ``fetch`` MUST NOT raise. Map every failure to
    one of the two metadata statuses below; the framework branches on
    ``ProviderRunMetadata.status``, never on exceptions:

    - ``"not_configured"`` — the provider is wired but missing the env-key /
      credential it needs. Build with :meth:`not_configured_metadata`.
    - ``"failed"`` — the provider tried and the upstream rejected the request
      (401 / 403 / timeout / 5xx / parse error). Build with
      :meth:`failed_metadata`.

    Subclasses override :meth:`is_configured` to return ``False`` when the
    required env-key is absent. The framework calls ``is_configured`` before
    ``fetch`` so a missing-key path can short-circuit cleanly without paying
    the network round-trip.
    """

    slug: ClassVar[str]
    category: ClassVar[SmartProxyCategory] = "smart_proxy"
    cost_hint: ClassVar[CostHint]
    version: ClassVar[str]

    @abstractmethod
    def fetch(
        self,
        url: str,
        *,
        ctx: FetchContext,
    ) -> tuple[bytes | None, ProviderRunMetadata]:
        """Fetch one URL through the smart-proxy.

        Returns ``(response_bytes, metadata)``. On block, missing credentials,
        or upstream failure, returns ``(None, ProviderRunMetadata(status=...))``.
        Never raises.
        """

    def is_configured(self) -> bool:
        """Return True iff this provider has the credentials it needs.

        Default: ``True`` — subclasses with env-key requirements override.
        """
        return True

    @classmethod
    def not_configured_metadata(
        cls,
        *,
        missing_env: str,
        suggestion: str | None = None,
    ) -> ProviderRunMetadata:
        """Build the canonical ``not_configured`` row.

        ``missing_env`` is the name of the env var the user must set.
        ``suggestion`` is folded into the ``error`` string when present so the
        downstream envelope's actionable-suggestion field has something to
        relay.
        """
        error = f"missing env var: {missing_env}"
        if suggestion:
            error = f"{error} — {suggestion}"
        return ProviderRunMetadata(
            status="not_configured",
            latency_ms=0,
            error=error,
            provider_version=cls.version,
        )

    @classmethod
    def failed_metadata(
        cls,
        *,
        error: str,
        latency_ms: int = 0,
    ) -> ProviderRunMetadata:
        """Build the canonical ``failed`` row for a configured-but-blocked attempt."""
        return ProviderRunMetadata(
            status="failed",
            latency_ms=latency_ms,
            error=error,
            provider_version=cls.version,
        )


__all__ = ["SmartProxyCategory", "SmartProxyProvider"]
