"""Pytest fixtures shared across the suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Absolute path to the repo's fixtures/ directory."""
    return Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolate_cli_cache_dir(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Point ``companyctx.cli.default_cache_dir`` at a per-test tmp dir.

    The cache wired in COX-6 / #9 writes the envelope on every CLI
    ``fetch`` invocation. Without isolation, every CLI test pollutes the
    developer's real XDG cache and — more importantly — earlier tests'
    cached envelopes leak into later tests. The cache key intentionally
    omits env-config (documented in SPEC §cache-semantics), so a test
    that toggles ``GOOGLE_PLACES_API_KEY`` between runs would otherwise
    keep getting the previous run's envelope back even with the new env.

    Tests that want to *inspect* the cache directory take a
    ``isolated_cache_dir`` fixture (see ``test_cache.py``); that fixture
    does the same monkeypatch and returns the path. This autouse one is
    purely defensive and runs even for tests that don't touch the cache.
    """
    target = tmp_path_factory.mktemp("companyctx-cache")
    monkeypatch.setattr("companyctx.cli.default_cache_dir", lambda: target)
    return target
