"""M1 contract tests.

Stubs are intentional in M1 — these tests assert the surface exists and the
not-yet-implemented bits raise the expected errors so M2/M3 can light them up
incrementally without rewriting the contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from companyctx.cache import CACHE_DB_FILENAME, CacheKey, FetchCache
from companyctx.config import APP_NAME, Settings, default_cache_dir, default_config_dir
from companyctx.http import DEFAULT_TIMEOUT_S, DEFAULT_USER_AGENT, build_session
from companyctx.providers import ENTRY_POINT_GROUP, discover
from companyctx.providers.base import (
    FetchContext,
    ProviderError,
    ProviderRunMetadata,
)
from companyctx.robots import is_allowed
from companyctx.schema import CompanyContext


def test_app_name_constant() -> None:
    assert APP_NAME == "companyctx"


def test_default_dirs_resolve() -> None:
    assert isinstance(default_cache_dir(), Path)
    assert isinstance(default_config_dir(), Path)


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.cache_enabled is False
    assert settings.verbose is False
    assert isinstance(settings.cache_dir, Path)
    assert isinstance(settings.config_dir, Path)


def test_cache_key_is_hashable_value() -> None:
    a = CacheKey(domain="example.com", provider_slug="site_text_trafilatura")
    b = CacheKey(domain="example.com", provider_slug="site_text_trafilatura")
    assert a == b
    assert hash(a) == hash(b)
    assert CACHE_DB_FILENAME.endswith(".sqlite3")


def test_fetch_cache_methods_are_stubs() -> None:
    cache = FetchCache(db_path=Path("/tmp/should-not-exist.sqlite3"))
    key = CacheKey(domain="example.com", provider_slug="x")
    with pytest.raises(NotImplementedError):
        cache.get(key)
    with pytest.raises(NotImplementedError):
        cache.put(key, b"", ttl_seconds=60)
    with pytest.raises(NotImplementedError):
        cache.list_entries()
    with pytest.raises(NotImplementedError):
        cache.clear()


def test_http_constants_and_session_stub() -> None:
    assert "companyctx" in DEFAULT_USER_AGENT
    assert DEFAULT_TIMEOUT_S > 0
    with pytest.raises(NotImplementedError):
        build_session()


def test_robots_default_path_is_stub() -> None:
    with pytest.raises(NotImplementedError):
        is_allowed("https://example.com/", user_agent=DEFAULT_USER_AGENT)


def test_provider_discovery_returns_dict() -> None:
    found = discover()
    assert isinstance(found, dict)
    assert ENTRY_POINT_GROUP == "companyctx.providers"


def test_provider_run_metadata_shape() -> None:
    meta = ProviderRunMetadata(
        status="degraded",
        latency_ms=0,
        error="key missing",
        provider_version="0.1.0",
    )
    assert meta.status == "degraded"
    assert meta.error == "key missing"


def test_fetch_context_defaults() -> None:
    ctx = FetchContext(user_agent=DEFAULT_USER_AGENT, timeout_s=DEFAULT_TIMEOUT_S)
    assert ctx.ignore_robots is False


def test_provider_error_is_exception() -> None:
    assert issubclass(ProviderError, Exception)


def test_company_context_requires_domain_and_fetched_at() -> None:
    pack = CompanyContext(domain="example.com", fetched_at=datetime.now(timezone.utc))
    assert pack.domain == "example.com"


def test_company_context_rejects_unknown_field() -> None:
    with pytest.raises(ValueError):
        CompanyContext(domain="example.com", fetched_at=datetime.now(timezone.utc), bogus=1)  # type: ignore[call-arg]
