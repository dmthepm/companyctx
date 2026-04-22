"""Deterministic Waterfall orchestrator.

One site in → one ``Envelope`` out. Runs every registered primary provider,
assembles the envelope, and — when a ``site_text`` provider returned
``failed`` and a ``smart_proxy`` provider is registered — re-fetches via the
user's smart proxy as Attempt 2. The recovered bytes flow through the same
extraction chain and populate the ``pages`` slot; top-level status is
aggregated with recovery awareness. Never raises at the boundary.

See ``docs/ARCHITECTURE.md`` for the three-attempt waterfall shape.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path

from companyctx import __version__
from companyctx.extract import site_signals_from_homepage_bytes
from companyctx.providers import discover
from companyctx.providers.base import FetchContext, ProviderBase
from companyctx.schema import (
    CompanyContext,
    Envelope,
    EnvelopeStatus,
    HeuristicSignals,
    MediaMention,
    MentionsSignals,
    ProviderRunMetadata,
    ReviewsSignals,
    SiteSignals,
    SocialSignals,
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
DEFAULT_TIMEOUT_S = 10.0
CORE_PROVIDER_VERSION = __version__
DISCOVERY_PROVIDER_SLUG = "_provider_discovery"
ORCHESTRATOR_PROVIDER_SLUG = "_orchestrator"
GENERIC_SUGGESTION = "configure a smart-proxy provider key or skip this prospect"

_RECOVERABLE_CATEGORIES = frozenset({"site_text", "site_meta"})
_SMART_PROXY_CATEGORY = "smart_proxy"


def run(
    site: str,
    *,
    mock: bool = False,
    fixtures_dir: str | Path | None = None,
    ignore_robots: bool = False,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    providers: Mapping[str, type[ProviderBase]] | None = None,
    fetched_at: datetime | None = None,
) -> Envelope:
    """Run every registered provider for ``site`` and emit one envelope.

    The boundary is non-raising: every provider failure (anti-bot, missing
    key, timeout, unhandled exception inside a provider) is captured as a
    ``ProviderRunMetadata`` row and surfaced on the envelope. The caller only
    ever sees a well-formed ``Envelope``.
    """
    ctx = FetchContext(
        user_agent=user_agent,
        timeout_s=timeout_s,
        ignore_robots=ignore_robots,
        mock=mock,
        fixtures_dir=str(fixtures_dir) if fixtures_dir is not None else None,
    )

    when = fetched_at if fetched_at is not None else datetime.now(timezone.utc)
    try:
        registry = providers if providers is not None else discover()
    except Exception as exc:  # noqa: BLE001 - deliberate boundary
        return _fallback_envelope(
            site=site,
            when=when,
            provenance={
                DISCOVERY_PROVIDER_SLUG: _failed_metadata(
                    error=f"provider discovery failed: {exc.__class__.__name__}: {exc}",
                    provider_version=CORE_PROVIDER_VERSION,
                )
            },
            registry={},
        )

    primary_registry = {
        slug: cls
        for slug, cls in registry.items()
        if getattr(cls, "category", None) != _SMART_PROXY_CATEGORY
    }
    smart_proxy_registry = {
        slug: cls
        for slug, cls in registry.items()
        if getattr(cls, "category", None) == _SMART_PROXY_CATEGORY
    }

    results: list[tuple[str, object | None, ProviderRunMetadata]] = []
    try:
        # Deterministic order — slug alphabetical so two --mock runs produce
        # byte-identical output.
        for slug in sorted(primary_registry):
            cls = primary_registry[slug]
            signals, meta = _invoke(slug, cls, site=site, ctx=ctx)
            results.append((slug, signals, meta))

        provenance: dict[str, ProviderRunMetadata] = {slug: meta for slug, _, meta in results}

        # Waterfall Attempt 2: on a failed site_text / site_meta row, let a
        # registered smart-proxy try to recover the pages slot. Only the
        # first failure gets a retry — the smart-proxy is a fallback fetcher
        # for the page, not a sibling provider, so one success is enough.
        if smart_proxy_registry:
            for index, (slug, _signals, meta) in enumerate(list(results)):
                primary_cls = primary_registry.get(slug)
                category = getattr(primary_cls, "category", None) if primary_cls else None
                if category not in _RECOVERABLE_CATEGORIES:
                    continue
                if meta.status != "failed":
                    continue
                recovered_signals = _attempt_smart_proxy_recovery(
                    site=site,
                    ctx=ctx,
                    smart_proxy_registry=smart_proxy_registry,
                    provenance=provenance,
                )
                if recovered_signals is not None:
                    results[index] = (slug, recovered_signals, meta)
                break

        data = CompanyContext(
            site=site,
            fetched_at=when,
            **_merge_signals(results),
        )
        status = _aggregate_status(provenance, registry)
        error, suggestion = _envelope_narrative(status, provenance)
        return Envelope(
            status=status,
            data=data,
            provenance=provenance,
            error=error,
            suggestion=suggestion,
        )
    except Exception as exc:  # noqa: BLE001 - deliberate boundary
        provenance = {slug: meta for slug, _, meta in results}
        provenance[ORCHESTRATOR_PROVIDER_SLUG] = _failed_metadata(
            error=f"orchestrator failed: {exc.__class__.__name__}: {exc}",
            provider_version=CORE_PROVIDER_VERSION,
        )
        return _fallback_envelope(site=site, when=when, provenance=provenance, registry=registry)


def _invoke(
    slug: str,
    cls: type[ProviderBase],
    *,
    site: str,
    ctx: FetchContext,
) -> tuple[object | None, ProviderRunMetadata]:
    """Call the provider's ``fetch``, catching any escaped exception.

    Providers are supposed to catch at their boundary; this is the last line
    of defense so one bad plugin can't take the whole run down.
    """
    version = getattr(cls, "version", "unknown")
    start = time.monotonic()
    try:
        provider = cls()
        result = provider.fetch(site, ctx=ctx)
    except Exception as exc:  # noqa: BLE001 — deliberate boundary
        return None, ProviderRunMetadata(
            status="failed",
            latency_ms=_elapsed_ms(start),
            error=f"provider raised: {exc.__class__.__name__}: {exc}",
            provider_version=version,
            cost_incurred=0,
        )
    return _normalize_provider_result(
        slug=slug,
        result=result,
        provider_version=version,
        latency_ms=_elapsed_ms(start),
    )


def _attempt_smart_proxy_recovery(
    *,
    site: str,
    ctx: FetchContext,
    smart_proxy_registry: Mapping[str, type[ProviderBase]],
    provenance: dict[str, ProviderRunMetadata],
) -> SiteSignals | None:
    """Try every registered smart-proxy provider in slug order.

    The first one that returns bytes + ``ok`` metadata wins. Every attempt's
    metadata is written into ``provenance`` so the user sees the trace. On
    bytes the shared extractor turns them into a ``SiteSignals`` payload;
    parse failures downgrade the proxy row to ``failed`` and move on.
    """
    for proxy_slug in sorted(smart_proxy_registry):
        proxy_cls = smart_proxy_registry[proxy_slug]
        body, proxy_meta = _invoke_smart_proxy(proxy_slug, proxy_cls, url=site, ctx=ctx)
        provenance[proxy_slug] = proxy_meta
        if body is None or proxy_meta.status != "ok":
            continue
        try:
            return site_signals_from_homepage_bytes(body)
        except Exception as exc:  # noqa: BLE001 - deliberate boundary
            provenance[proxy_slug] = _failed_metadata(
                error=f"smart-proxy bytes extraction failed: {exc.__class__.__name__}: {exc}",
                provider_version=proxy_meta.provider_version,
                latency_ms=proxy_meta.latency_ms,
            )
    return None


def _invoke_smart_proxy(
    slug: str,
    cls: type[ProviderBase],
    *,
    url: str,
    ctx: FetchContext,
) -> tuple[bytes | None, ProviderRunMetadata]:
    """Call a smart-proxy's ``fetch``, catching any escaped exception.

    Smart-proxies return ``(bytes | None, ProviderRunMetadata)`` — a different
    shape from primary providers — so the normalisation rules are distinct.
    """
    version = getattr(cls, "version", "unknown")
    start = time.monotonic()
    try:
        provider = cls()
        result = provider.fetch(url, ctx=ctx)
    except Exception as exc:  # noqa: BLE001 — deliberate boundary
        return None, ProviderRunMetadata(
            status="failed",
            latency_ms=_elapsed_ms(start),
            error=f"smart-proxy raised: {exc.__class__.__name__}: {exc}",
            provider_version=version,
            cost_incurred=0,
        )
    if not isinstance(result, tuple) or len(result) != 2:
        return None, _failed_metadata(
            error=f"{slug} returned invalid result: expected (bytes|None, metadata)",
            provider_version=version,
            latency_ms=_elapsed_ms(start),
        )
    body, raw_meta = result
    try:
        meta = (
            raw_meta
            if isinstance(raw_meta, ProviderRunMetadata)
            else ProviderRunMetadata.model_validate(raw_meta)
        )
    except Exception as exc:  # noqa: BLE001 - deliberate boundary
        return None, _failed_metadata(
            error=f"{slug} returned invalid metadata: {exc.__class__.__name__}: {exc}",
            provider_version=version,
            latency_ms=_elapsed_ms(start),
        )
    if body is not None and not isinstance(body, (bytes, bytearray)):
        return None, _failed_metadata(
            error=f"{slug} returned non-bytes body: {type(body).__name__}",
            provider_version=meta.provider_version,
            latency_ms=meta.latency_ms,
        )
    return (bytes(body) if body is not None else None), meta


_SIGNAL_ASSIGN: dict[type, str] = {
    SiteSignals: "pages",
    ReviewsSignals: "reviews",
    SocialSignals: "social",
    HeuristicSignals: "signals",
    MentionsSignals: "mentions",
}


def _merge_signals(
    results: Iterable[tuple[str, object | None, ProviderRunMetadata]],
) -> dict[str, object]:
    """Route each provider's typed signals into its CompanyContext slot.

    Last-writer-wins per slot. Providers covering the same slot should run in
    a deterministic order (the orchestrator sorts by slug) so the outcome is
    stable.
    """
    merged: dict[str, object] = {
        "pages": None,
        "reviews": None,
        "social": None,
        "signals": None,
        "mentions": None,
    }
    for _slug, signals, _meta in results:
        if signals is None:
            continue
        slot = _SIGNAL_ASSIGN.get(type(signals))
        if slot is not None:
            merged[slot] = signals
            continue
        # Back-compat: a mentions provider may still hand back a plain list.
        if isinstance(signals, list) and all(isinstance(m, MediaMention) for m in signals):
            merged["mentions"] = MentionsSignals(items=signals)
    return merged


def _aggregate_status(
    provenance: Mapping[str, ProviderRunMetadata],
    registry: Mapping[str, type[ProviderBase]],
) -> EnvelopeStatus:
    """Waterfall-aware status rollup.

    A failed site_text/site_meta row is ``recovered`` when a smart-proxy row
    in the same run is ``ok`` — recovery rows stay in provenance for
    traceability but don't count as top-level failures. When no ``ok`` rows
    exist and any row is ``not_configured``, the envelope reports
    ``partial`` with a config-based suggestion rather than ``degraded``,
    matching the shape documented in ``docs/EXTRACTION-STRATEGY.md``.
    """
    rows = list(provenance.items())
    if not rows:
        return "degraded"

    recovered_slugs: set[str] = set()
    smart_proxy_recovered = any(
        meta.status == "ok"
        and getattr(registry.get(slug), "category", None) == _SMART_PROXY_CATEGORY
        for slug, meta in rows
    )
    if smart_proxy_recovered:
        for slug, meta in rows:
            cls = registry.get(slug)
            if cls is None:
                continue
            category = getattr(cls, "category", None)
            if category in _RECOVERABLE_CATEGORIES and meta.status == "failed":
                recovered_slugs.add(slug)

    effective = [(slug, meta) for slug, meta in rows if slug not in recovered_slugs]
    any_ok = any(meta.status == "ok" for _slug, meta in effective)
    any_fail = any(
        meta.status in ("failed", "not_configured", "degraded") for _slug, meta in effective
    )
    if any_ok and not any_fail:
        return "ok"
    if any_ok and any_fail:
        return "partial"
    if any(meta.status == "not_configured" for _slug, meta in rows):
        return "partial"
    return "degraded"


def _envelope_narrative(
    status: EnvelopeStatus,
    provenance: Mapping[str, ProviderRunMetadata],
) -> tuple[str | None, str | None]:
    if status == "ok":
        return None, None
    # Pull the first concrete failure reason for the error string; suggestion
    # is generic-but-actionable so downstream pipelines can branch.
    failure_reason = None
    for meta in provenance.values():
        if meta.status in ("failed", "not_configured", "degraded") and meta.error:
            failure_reason = meta.error
            break
    if status == "partial":
        return (
            failure_reason or "one or more providers failed",
            GENERIC_SUGGESTION,
        )
    # degraded
    return (
        failure_reason or "no providers succeeded",
        GENERIC_SUGGESTION,
    )


def _normalize_provider_result(
    *,
    slug: str,
    result: object,
    provider_version: str,
    latency_ms: int,
) -> tuple[object | None, ProviderRunMetadata]:
    if not isinstance(result, tuple) or len(result) != 2:
        return None, _failed_metadata(
            error=f"{slug} returned invalid result tuple: expected (signals, metadata)",
            provider_version=provider_version,
            latency_ms=latency_ms,
        )
    signals: object | None = result[0]
    raw_meta: object = result[1]

    try:
        meta = (
            raw_meta
            if isinstance(raw_meta, ProviderRunMetadata)
            else ProviderRunMetadata.model_validate(raw_meta)
        )
    except Exception as exc:  # noqa: BLE001 - deliberate boundary
        return None, _failed_metadata(
            error=f"{slug} returned invalid metadata: {exc.__class__.__name__}: {exc}",
            provider_version=provider_version,
            latency_ms=latency_ms,
        )

    try:
        normalized_signals = _normalize_signals(signals)
    except Exception as exc:  # noqa: BLE001 - deliberate boundary
        return None, _failed_metadata(
            error=f"{slug} returned invalid payload: {exc}",
            provider_version=meta.provider_version,
            latency_ms=meta.latency_ms,
        )

    return normalized_signals, meta


def _normalize_signals(signals: object | None) -> object | None:
    if signals is None:
        return None
    if isinstance(
        signals,
        (SiteSignals, ReviewsSignals, SocialSignals, HeuristicSignals, MentionsSignals),
    ):
        return signals
    if isinstance(signals, list) and all(isinstance(item, MediaMention) for item in signals):
        return MentionsSignals(items=signals)
    raise TypeError(f"unsupported payload type: {type(signals).__name__}")


def _fallback_envelope(
    *,
    site: str,
    when: datetime,
    provenance: Mapping[str, ProviderRunMetadata],
    registry: Mapping[str, type[ProviderBase]],
) -> Envelope:
    status = _aggregate_status(provenance, registry)
    error, suggestion = _envelope_narrative(status, provenance)
    if error is None:
        error = "no providers succeeded"
    if suggestion is None:
        suggestion = GENERIC_SUGGESTION
    return Envelope(
        status=status,
        data=CompanyContext(site=site, fetched_at=when),
        provenance=dict(provenance),
        error=error,
        suggestion=suggestion,
    )


def _failed_metadata(
    *,
    error: str,
    provider_version: str,
    latency_ms: int = 0,
) -> ProviderRunMetadata:
    return ProviderRunMetadata(
        status="failed",
        latency_ms=latency_ms,
        error=error,
        provider_version=provider_version,
        cost_incurred=0,
    )


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


__all__ = ["DEFAULT_TIMEOUT_S", "DEFAULT_USER_AGENT", "run"]
