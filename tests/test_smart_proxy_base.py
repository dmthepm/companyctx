"""Contract tests for the SmartProxyProvider abstract base."""

from __future__ import annotations

import pytest

from companyctx.http import DEFAULT_TIMEOUT_S, DEFAULT_USER_AGENT
from companyctx.providers.base import (
    FetchContext,
    ProviderRunMetadata,
)
from companyctx.providers.smart_proxy_base import SmartProxyProvider


class _GoodProxy(SmartProxyProvider):
    slug = "proxy_test_good"
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


class _UnconfiguredProxy(SmartProxyProvider):
    slug = "proxy_test_unconfigured"
    cost_hint = "per-call"
    version = "0.0.1"

    def is_configured(self) -> bool:
        return False

    def fetch(
        self,
        url: str,
        *,
        ctx: FetchContext,
    ) -> tuple[bytes | None, ProviderRunMetadata]:
        return None, self.not_configured_metadata(
            missing_env="TEST_PROXY_KEY",
            suggestion="set TEST_PROXY_KEY in your shell",
        )


def test_cannot_instantiate_abstract_base() -> None:
    with pytest.raises(TypeError):
        SmartProxyProvider()  # type: ignore[abstract]


def test_subclass_missing_fetch_cannot_instantiate() -> None:
    class _Incomplete(SmartProxyProvider):
        slug = "proxy_test_incomplete"
        cost_hint = "per-call"
        version = "0.0.1"

    with pytest.raises(TypeError):
        _Incomplete()  # type: ignore[abstract]


def test_concrete_subclass_instantiates_and_fetches() -> None:
    provider = _GoodProxy()
    ctx = FetchContext(user_agent=DEFAULT_USER_AGENT, timeout_s=DEFAULT_TIMEOUT_S)
    body, meta = provider.fetch("https://example.com", ctx=ctx)
    assert body == b"<html>ok</html>"
    assert meta.status == "ok"
    assert meta.provider_version == "0.0.1"


def test_category_is_locked_to_smart_proxy() -> None:
    assert _GoodProxy.category == "smart_proxy"
    assert SmartProxyProvider.category == "smart_proxy"


def test_is_configured_default_true_and_overridable() -> None:
    assert _GoodProxy().is_configured() is True
    assert _UnconfiguredProxy().is_configured() is False


def test_not_configured_metadata_helper_shape() -> None:
    meta = _UnconfiguredProxy.not_configured_metadata(
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
    meta = _GoodProxy.not_configured_metadata(missing_env="BAR_KEY")
    assert meta.status == "not_configured"
    assert meta.error == "missing env var: BAR_KEY"


def test_failed_metadata_helper_shape() -> None:
    meta = _GoodProxy.failed_metadata(error="HTTP 403", latency_ms=874)
    assert meta.status == "failed"
    assert meta.latency_ms == 874
    assert meta.error == "HTTP 403"
    assert meta.provider_version == "0.0.1"


def test_unconfigured_provider_returns_not_configured_envelope() -> None:
    provider = _UnconfiguredProxy()
    ctx = FetchContext(user_agent=DEFAULT_USER_AGENT, timeout_s=DEFAULT_TIMEOUT_S)
    body, meta = provider.fetch("https://example.com", ctx=ctx)
    assert body is None
    assert meta.status == "not_configured"
    assert meta.error is not None
    assert "TEST_PROXY_KEY" in meta.error


def test_smart_proxy_category_is_in_provider_category_literal() -> None:
    from typing import get_args

    from companyctx.providers.base import ProviderCategory

    assert "smart_proxy" in get_args(ProviderCategory)
