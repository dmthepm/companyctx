"""Contract tests for the SmartProxyProvider Protocol."""

from __future__ import annotations

import pytest

from companyctx.http import DEFAULT_TIMEOUT_S, DEFAULT_USER_AGENT
from companyctx.providers.base import (
    FetchContext,
    ProviderBase,
    ProviderRunMetadata,
)
from companyctx.providers.smart_proxy_base import (
    SmartProxyProvider,
    failed_metadata,
    not_configured_metadata,
)


class _GoodProxy:
    """A correctly-shaped smart-proxy provider."""

    slug = "proxy_test_good"
    category = "smart_proxy"
    cost_hint = "per-call"
    version = "0.0.1"

    def fetch(
        self,
        url: str,
        *,
        ctx: FetchContext,
    ) -> tuple[bytes | None, ProviderRunMetadata]:
        return b"<html>ok</html>", ProviderRunMetadata(
            status="ok",
            latency_ms=12,
            error=None,
            provider_version=self.version,
        )


class _UnconfiguredProxy:
    slug = "proxy_test_unconfigured"
    category = "smart_proxy"
    cost_hint = "per-call"
    version = "0.0.1"

    def fetch(
        self,
        url: str,
        *,
        ctx: FetchContext,
    ) -> tuple[bytes | None, ProviderRunMetadata]:
        return None, not_configured_metadata(
            provider_version=self.version,
            missing_env="TEST_PROXY_KEY",
            suggestion="set TEST_PROXY_KEY in your shell",
        )


class _MissingFetch:
    """Has all attrs but no fetch — must fail isinstance check."""

    slug = "proxy_test_no_fetch"
    category = "smart_proxy"
    cost_hint = "per-call"
    version = "0.0.1"


def test_protocol_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        SmartProxyProvider()  # type: ignore[misc]


def test_concrete_provider_passes_isinstance_check() -> None:
    assert isinstance(_GoodProxy(), SmartProxyProvider)


def test_subclass_missing_fetch_fails_isinstance_check() -> None:
    """Closes the contract-enforcement gap: no fetch → not a SmartProxyProvider."""
    assert not isinstance(_MissingFetch(), SmartProxyProvider)


def test_inherits_provider_base_chain() -> None:
    """SmartProxyProvider extends ProviderBase — one structural chain, not two.

    ``issubclass()`` against a Protocol with non-method members raises in
    CPython, so the inheritance is verified via ``__mro__`` instead. The
    structural check uses ``isinstance`` against the ``ProviderBase`` Protocol
    on a concrete provider — same chain, both Protocols recognize it.
    """
    assert ProviderBase in SmartProxyProvider.__mro__
    assert isinstance(_GoodProxy(), ProviderBase)


def test_category_narrowed_to_smart_proxy_literal() -> None:
    from typing import get_args

    from companyctx.providers.smart_proxy_base import SmartProxyCategory

    assert get_args(SmartProxyCategory) == ("smart_proxy",)
    assert _GoodProxy.category == "smart_proxy"


def test_smart_proxy_category_is_in_provider_category_literal() -> None:
    from typing import get_args

    from companyctx.providers.base import ProviderCategory

    assert "smart_proxy" in get_args(ProviderCategory)


def test_concrete_provider_round_trips_bytes_and_metadata() -> None:
    provider = _GoodProxy()
    ctx = FetchContext(user_agent=DEFAULT_USER_AGENT, timeout_s=DEFAULT_TIMEOUT_S)
    body, meta = provider.fetch("https://example.com", ctx=ctx)
    assert body == b"<html>ok</html>"
    assert meta.status == "ok"
    assert meta.provider_version == "0.0.1"


def test_unconfigured_provider_returns_not_configured_envelope() -> None:
    provider = _UnconfiguredProxy()
    ctx = FetchContext(user_agent=DEFAULT_USER_AGENT, timeout_s=DEFAULT_TIMEOUT_S)
    body, meta = provider.fetch("https://example.com", ctx=ctx)
    assert body is None
    assert meta.status == "not_configured"
    assert meta.error is not None
    assert "TEST_PROXY_KEY" in meta.error


def test_not_configured_metadata_helper_shape() -> None:
    meta = not_configured_metadata(
        provider_version="0.0.1",
        missing_env="FOO_KEY",
        suggestion="export FOO_KEY=...",
    )
    assert meta.status == "not_configured"
    assert meta.latency_ms == 0
    assert meta.error is not None
    assert "FOO_KEY" in meta.error
    assert "export FOO_KEY=..." in meta.error
    assert meta.provider_version == "0.0.1"


def test_not_configured_metadata_without_suggestion() -> None:
    meta = not_configured_metadata(provider_version="0.0.1", missing_env="BAR_KEY")
    assert meta.status == "not_configured"
    assert meta.error == "missing env var: BAR_KEY"


def test_failed_metadata_helper_shape() -> None:
    meta = failed_metadata(provider_version="0.0.1", error="HTTP 403", latency_ms=874)
    assert meta.status == "failed"
    assert meta.latency_ms == 874
    assert meta.error == "HTTP 403"
    assert meta.provider_version == "0.0.1"
