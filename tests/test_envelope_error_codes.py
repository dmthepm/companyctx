"""Coverage for every ``EnvelopeErrorCode`` value.

The issue acceptance (COX-37) requires that each of the 7 closed-set codes
is exercised by at least one test. Each case feeds a hand-rolled failing
provider through the orchestrator and asserts the classifier lands on the
expected code. The orchestrator's classifier lives at
``core._classify_error_code``; keep this test in sync when the code set
grows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, cast

from companyctx import core
from companyctx.providers.base import FetchContext, ProviderBase
from companyctx.schema import (
    EnvelopeErrorCode,
    ProviderRunMetadata,
    ProviderStatus,
    SiteSignals,
)

FIXED_WHEN = datetime(2026, 4, 20, tzinfo=timezone.utc)


def _reg(**mapping: type) -> dict[str, type[ProviderBase]]:
    return cast("dict[str, type[ProviderBase]]", dict(mapping))


def _make_failing_provider(
    *,
    slug: str,
    error: str,
    status: ProviderStatus = "failed",
    category: Literal[
        "site_text",
        "site_meta",
        "reviews",
        "social_discovery",
        "social_counts",
        "signals",
        "mentions",
        "smart_proxy",
    ] = "site_text",
) -> type:
    """Factory — returns a provider class that always fails with ``error``.

    Used across the error-code parametrisation so each test reads end-to-end.
    """

    class _Provider:
        pass

    _Provider.slug = slug  # type: ignore[attr-defined]
    _Provider.category = category  # type: ignore[attr-defined]
    _Provider.cost_hint = "free"  # type: ignore[attr-defined]
    _Provider.version = "0.2.0"  # type: ignore[attr-defined]

    def fetch(
        self: _Provider, site: str, *, ctx: FetchContext
    ) -> tuple[SiteSignals | None, ProviderRunMetadata]:
        return None, ProviderRunMetadata(
            status=status,
            latency_ms=0,
            error=error,
            provider_version="0.2.0",
        )

    _Provider.fetch = fetch  # type: ignore[attr-defined]
    _Provider.__name__ = f"_Provider_{slug}"
    return _Provider


def _run_with_error(error: str, *, status: ProviderStatus = "failed") -> EnvelopeErrorCode:
    provider = _make_failing_provider(slug="errorprobe", error=error, status=status)
    env = core.run(
        "probe.example",
        mock=True,
        providers=_reg(errorprobe=provider),
        fetched_at=FIXED_WHEN,
    )
    assert env.error is not None
    return env.error.code


def test_ssrf_rejected_code_from_unsafe_url_error() -> None:
    assert _run_with_error("unsafe_url: metadata host not allowed") == "ssrf_rejected"


def test_network_timeout_code_from_timeout_error() -> None:
    assert _run_with_error("network error: Timeout") == "network_timeout"


def test_blocked_by_antibot_code_from_http_403() -> None:
    assert _run_with_error("blocked_by_antibot (HTTP 403)") == "blocked_by_antibot"


def test_blocked_by_antibot_code_from_robots_block() -> None:
    assert _run_with_error("blocked_by_robots") == "blocked_by_antibot"


def test_path_traversal_rejected_code_from_escape_error() -> None:
    assert (
        _run_with_error("fixture path escapes fixtures_dir: /etc/passwd")
        == "path_traversal_rejected"
    )


def test_path_traversal_rejected_code_from_invalid_slug() -> None:
    assert _run_with_error("invalid fixture slug: '../'") == "path_traversal_rejected"


def test_response_too_large_code_from_cap_error() -> None:
    assert _run_with_error("response_too_large: exceeded 10485760 bytes") == "response_too_large"


def test_misconfigured_provider_code_from_not_configured_row() -> None:
    code = _run_with_error(
        "missing env var: COMPANYCTX_SMART_PROXY_URL",
        status="not_configured",
    )
    assert code == "misconfigured_provider"


def test_no_provider_succeeded_code_for_unclassified_reason() -> None:
    assert _run_with_error("something we do not recognize") == "no_provider_succeeded"
