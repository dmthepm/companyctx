"""SmartProxyProvider Protocol for the Deterministic Waterfall's Attempt 2.

Attempt 2 (see ``docs/ARCHITECTURE.md``) is vendor-agnostic. ``companyctx``
ships *the contract*; the user supplies their own residential-proxy /
headless-browser vendor.

A ``SmartProxyProvider`` is a low-level fetcher: given a URL, it returns the
raw response bytes (or ``None`` on block / failure) plus a
``ProviderRunMetadata`` row. The bytes flow into the same ``trafilatura`` /
``readability-lxml`` / ``extruct`` chain as the zero-key path — the schema
doesn't know which layer produced them.

This module ships only the Protocol. The first concrete implementation lands
after issue #15 (envelope + zero-key provider + waterfall) plus an M2 vendor
eval spike. We do not name a vendor in README / ``docs/PROVIDERS.md`` before
that measurement, per the no-vendor-commitments-before-testing rule.

The Protocol inherits from ``ProviderBase`` so the structural contract is one
chain — any future addition to ``ProviderBase`` propagates automatically.
"""

from __future__ import annotations

from typing import ClassVar, Literal, Protocol, runtime_checkable

from companyctx.providers.base import (
    FetchContext,
    ProviderBase,
    ProviderRunMetadata,
)

SmartProxyCategory = Literal["smart_proxy"]


@runtime_checkable
class SmartProxyProvider(ProviderBase, Protocol):
    """Structural contract for a smart-proxy fetcher plugin.

    Inherits ``slug`` / ``cost_hint`` / ``version`` from :class:`ProviderBase`
    and narrows ``category`` to the ``"smart_proxy"`` literal. Specializes the
    inherited ``fetch`` signature: a smart-proxy hands back raw response
    *bytes* (for downstream parsing by ``trafilatura`` / ``extruct``), not a
    typed signals model.

    **Failure-mode contract.** ``fetch`` MUST NOT raise. Map every failure to
    one of the two metadata statuses below; the framework branches on
    ``ProviderRunMetadata.status``, never on exceptions:

    - ``"not_configured"`` — wired but missing the env-key / credential it
      needs. Use :func:`not_configured_metadata`.
    - ``"failed"`` — tried, upstream rejected (401 / 403 / timeout / 5xx /
      parse error). Use :func:`failed_metadata`.
    """

    category: ClassVar[SmartProxyCategory]

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
        ...


def not_configured_metadata(
    *,
    provider_version: str,
    missing_env: str,
    suggestion: str | None = None,
) -> ProviderRunMetadata:
    """Build the canonical ``not_configured`` row.

    ``missing_env`` is the env var the user must set. ``suggestion`` is folded
    into the ``error`` string when present so the downstream envelope's
    actionable-suggestion field has something to relay.
    """
    error = f"missing env var: {missing_env}"
    if suggestion:
        error = f"{error} — {suggestion}"
    return ProviderRunMetadata(
        status="not_configured",
        latency_ms=0,
        error=error,
        provider_version=provider_version,
    )


def failed_metadata(
    *,
    provider_version: str,
    error: str,
    latency_ms: int = 0,
) -> ProviderRunMetadata:
    """Build the canonical ``failed`` row for a configured-but-blocked attempt."""
    return ProviderRunMetadata(
        status="failed",
        latency_ms=latency_ms,
        error=error,
        provider_version=provider_version,
    )


__all__ = [
    "SmartProxyCategory",
    "SmartProxyProvider",
    "failed_metadata",
    "not_configured_metadata",
]
