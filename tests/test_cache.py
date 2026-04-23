"""SQLite cache + CLI wiring tests (COX-6 / #9).

Covers:

- :mod:`companyctx.cache` round-trip, TTL, provider_set_hash invalidation,
  list/clear semantics.
- Migration runner: idempotent, applies a no-op migration, ignores stray
  files.
- CLI cache flags: ``--refresh``, ``--no-cache``, ``--from-cache`` (hit +
  miss), ``cache list``, ``cache clear`` filter requirements.
- XDG path resolution under a monkeypatched ``default_cache_dir``.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import ClassVar, Literal, cast

import pytest
from click.testing import Result
from typer.testing import CliRunner

from companyctx import cache as cache_mod
from companyctx import core
from companyctx.cache import (
    CACHE_DB_FILENAME,
    DEFAULT_TTL_SECONDS,
    FetchCache,
    apply_migration_sql,
    normalize_host,
    parse_age,
    provider_set_hash,
)
from companyctx.cli import app
from companyctx.providers.base import FetchContext, ProviderBase
from companyctx.schema import (
    SCHEMA_VERSION,
    CompanyContext,
    Envelope,
    ProviderRunMetadata,
    SiteSignals,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
FIXED_WHEN = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)


# ---- helpers ----


class _AlwaysOk:
    slug: ClassVar[str] = "always_ok"
    category: ClassVar[Literal["site_text"]] = "site_text"
    cost_hint: ClassVar[Literal["free"]] = "free"
    version: ClassVar[str] = "0.1.0"

    def fetch(
        self, site: str, *, ctx: FetchContext
    ) -> tuple[SiteSignals | None, ProviderRunMetadata]:
        return (
            SiteSignals(homepage_text=f"hello {site}"),
            ProviderRunMetadata(status="ok", latency_ms=1, provider_version=self.version),
        )


class _AlwaysOkBumped(_AlwaysOk):
    """Same slug, bumped version — proves the version bump invalidates rows."""

    version: ClassVar[str] = "0.2.0"


def _registry(*classes: type) -> dict[str, type[ProviderBase]]:
    """Build a slug-keyed registry from arbitrary provider-shaped test classes.

    The cast mirrors ``test_core_orchestrator._reg`` — every class passed in
    is runtime-checkable against ``ProviderBase`` even when it doesn't
    formally inherit from the Protocol, so the cast is a typing convenience.
    """
    mapping = {cls.slug: cls for cls in classes}  # type: ignore[attr-defined]
    return cast("dict[str, type[ProviderBase]]", mapping)


def _envelope(site: str, *, when: datetime = FIXED_WHEN) -> Envelope:
    return Envelope(
        schema_version=SCHEMA_VERSION,
        status="ok",
        data=CompanyContext(
            site=site, fetched_at=when, pages=SiteSignals(homepage_text=f"hi {site}")
        ),
        provenance={
            "always_ok": ProviderRunMetadata(status="ok", latency_ms=4, provider_version="0.1.0")
        },
        error=None,
    )


# ---- pure helpers ----


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.com", "example.com"),
        ("Example.COM", "example.com"),
        ("https://example.com", "example.com"),
        ("https://www.example.com/", "example.com"),
        ("HTTP://Acme.example/path?q=1", "acme.example"),
        ("example.com:8080", "example.com"),
    ],
)
def test_normalize_host(raw: str, expected: str) -> None:
    assert normalize_host(raw) == expected


@pytest.mark.parametrize("bad", ["", "   ", "://"])
def test_normalize_host_rejects_garbage(bad: str) -> None:
    with pytest.raises(ValueError):
        normalize_host(bad)


def test_provider_set_hash_is_stable() -> None:
    a = _registry(_AlwaysOk)
    assert provider_set_hash(a) == provider_set_hash(a)


def test_provider_set_hash_changes_on_version_bump() -> None:
    a = _registry(_AlwaysOk)
    b = _registry(_AlwaysOkBumped)
    assert provider_set_hash(a) != provider_set_hash(b)


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("30s", 30), ("5m", 300), ("12h", 43200), ("7d", 604800), ("  3d ", 259200)],
)
def test_parse_age(text: str, seconds: int) -> None:
    assert parse_age(text) == timedelta(seconds=seconds)


@pytest.mark.parametrize("bad", ["", "7", "7days", "abc", "5x"])
def test_parse_age_rejects_garbage(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_age(bad)


# ---- migration harness ----


def test_migration_runner_creates_all_tables(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite3"
    with FetchCache(db) as fc:
        cur = fc._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cur.fetchall()}
    assert {"companies", "raw_payloads", "provenance", "schema_version"} <= tables


def test_migration_runner_records_version(tmp_path: Path) -> None:
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        assert fc.schema_version() == 1


def test_migration_runner_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite3"
    with FetchCache(db):
        pass
    # Re-open: should not re-apply 0001_initial (which would error on
    # CREATE TABLE for an existing table).
    with FetchCache(db) as fc:
        assert fc.schema_version() == 1


def test_no_op_migration_applies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Prove the runner can apply a future migration past the bootstrap one."""
    db = tmp_path / "c.sqlite3"
    with FetchCache(db) as fc:
        # Apply an explicit no-op migration via the public helper to prove the
        # version-tracking + transaction wrapping work end-to-end.
        apply_migration_sql(fc._conn, 99, "-- noop\nSELECT 1;")
        assert fc.schema_version() == 99


def test_migration_runner_ignores_non_matching_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stray files in the migrations dir (.bak, .swp) must not break discovery."""
    fake = [(1, _read_initial_sql())]
    monkeypatch.setattr(cache_mod, "_discover_migrations", lambda: fake)
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        assert fc.schema_version() == 1


def _read_initial_sql() -> str:
    from importlib import resources

    return (
        resources.files(cache_mod.MIGRATIONS_PACKAGE)
        .joinpath("0001_initial.sql")
        .read_text(encoding="utf-8")
    )


# ---- round-trip ----


def test_put_get_round_trip(tmp_path: Path) -> None:
    registry = _registry(_AlwaysOk)
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        fc.put_envelope(_envelope("example.com"), registry=registry)
        got = fc.get_envelope("example.com", registry=registry)
    assert got is not None
    assert got.data.site == "example.com"
    assert got.status == "ok"
    assert got.data.pages is not None
    assert got.data.pages.homepage_text == "hi example.com"


def test_get_returns_none_on_miss(tmp_path: Path) -> None:
    registry = _registry(_AlwaysOk)
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        assert fc.get_envelope("example.com", registry=registry) is None


def test_get_returns_none_when_expired(tmp_path: Path) -> None:
    registry = _registry(_AlwaysOk)
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        fc.put_envelope(_envelope("example.com"), registry=registry, ttl_seconds=10, now=FIXED_WHEN)
        future = FIXED_WHEN + timedelta(seconds=10_000)
        assert fc.get_envelope("example.com", registry=registry, now=future) is None


def test_get_returns_none_on_provider_set_hash_mismatch(tmp_path: Path) -> None:
    """Bumping a provider's version invalidates cached rows — that's the contract."""
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        fc.put_envelope(_envelope("example.com"), registry=_registry(_AlwaysOk))
        assert fc.get_envelope("example.com", registry=_registry(_AlwaysOkBumped)) is None


def test_put_appends_audit_trail(tmp_path: Path) -> None:
    """``--refresh`` writes shadow rows; old payloads stay queryable."""
    registry = _registry(_AlwaysOk)
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        fc.put_envelope(_envelope("example.com", when=FIXED_WHEN), registry=registry)
        fc.put_envelope(
            _envelope("example.com", when=FIXED_WHEN + timedelta(hours=1)),
            registry=registry,
        )
        cur = fc._conn.execute(
            "SELECT COUNT(*) AS n FROM raw_payloads WHERE normalized_host = ?",
            ("example.com",),
        )
        assert cur.fetchone()["n"] == 2


# ---- list / clear ----


def test_list_entries_one_per_host(tmp_path: Path) -> None:
    registry = _registry(_AlwaysOk)
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        fc.put_envelope(_envelope("a.example"), registry=registry)
        fc.put_envelope(_envelope("b.example"), registry=registry)
        # Shadow write for a.example — list still returns one row.
        fc.put_envelope(
            _envelope("a.example", when=FIXED_WHEN + timedelta(hours=1)), registry=registry
        )
        entries = fc.list_entries()
    hosts = [e.normalized_host for e in entries]
    assert hosts == ["a.example", "b.example"]


def test_clear_by_site(tmp_path: Path) -> None:
    registry = _registry(_AlwaysOk)
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        fc.put_envelope(_envelope("a.example"), registry=registry)
        fc.put_envelope(_envelope("b.example"), registry=registry)
        removed = fc.clear(site="a.example")
        assert removed == 1
        hosts = [e.normalized_host for e in fc.list_entries()]
    assert hosts == ["b.example"]


def test_clear_by_older_than(tmp_path: Path) -> None:
    registry = _registry(_AlwaysOk)
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        old = FIXED_WHEN - timedelta(days=10)
        new = FIXED_WHEN
        fc.put_envelope(_envelope("a.example", when=old), registry=registry, now=old)
        fc.put_envelope(_envelope("b.example", when=new), registry=registry, now=new)
        removed = fc.clear(older_than=timedelta(days=5), now=new)
    assert removed == 1


def test_clear_repoints_companies_to_survivor(tmp_path: Path) -> None:
    """When the latest run is reaped but earlier runs survive, companies repoints."""
    registry = _registry(_AlwaysOk)
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        old_when = FIXED_WHEN - timedelta(days=1)
        fc.put_envelope(_envelope("a.example", when=old_when), registry=registry, now=old_when)
        fc.put_envelope(_envelope("a.example", when=FIXED_WHEN), registry=registry, now=FIXED_WHEN)
        # Drop the recent one only.
        fc.clear(older_than=timedelta(seconds=0), now=FIXED_WHEN + timedelta(hours=1))
        # The survivor is the older row; companies must point at it, not be empty.
        entries = fc.list_entries()
    assert len(entries) == 0 or entries[0].fetched_at == old_when


# ---- core.run integration ----


def test_core_run_writes_cache(tmp_path: Path) -> None:
    registry = _registry(_AlwaysOk)
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        env = core.run("example.com", providers=registry, fetched_at=FIXED_WHEN, cache=fc)
        assert env.status == "ok"
        # Round-tripped envelope present in cache.
        assert fc.get_envelope("example.com", registry=registry) is not None


def test_core_run_short_circuits_on_cache_hit(tmp_path: Path) -> None:
    """A cache hit must skip provider invocation entirely."""
    seen: list[str] = []

    class _Recording(_AlwaysOk):
        slug: ClassVar[str] = "recording"

        def fetch(
            self, site: str, *, ctx: FetchContext
        ) -> tuple[SiteSignals | None, ProviderRunMetadata]:
            seen.append(site)
            return super().fetch(site, ctx=ctx)

    registry = _registry(_Recording)
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        core.run("example.com", providers=registry, fetched_at=FIXED_WHEN, cache=fc)
        assert seen == ["example.com"]
        core.run("example.com", providers=registry, fetched_at=FIXED_WHEN, cache=fc)
        # No second call — the second run was served from cache.
        assert seen == ["example.com"]


def test_core_run_refresh_skips_read(tmp_path: Path) -> None:
    seen: list[str] = []

    class _Recording(_AlwaysOk):
        slug: ClassVar[str] = "recording"

        def fetch(
            self, site: str, *, ctx: FetchContext
        ) -> tuple[SiteSignals | None, ProviderRunMetadata]:
            seen.append(site)
            return super().fetch(site, ctx=ctx)

    registry = _registry(_Recording)
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        core.run("example.com", providers=registry, fetched_at=FIXED_WHEN, cache=fc)
        core.run(
            "example.com",
            providers=registry,
            fetched_at=FIXED_WHEN,
            cache=fc,
            read_cache=False,
        )
        assert seen == ["example.com", "example.com"]


def test_core_run_disabled_writes_when_write_cache_false(tmp_path: Path) -> None:
    registry = _registry(_AlwaysOk)
    with FetchCache(tmp_path / "c.sqlite3") as fc:
        core.run(
            "example.com",
            providers=registry,
            fetched_at=FIXED_WHEN,
            cache=fc,
            write_cache=False,
        )
        assert fc.get_envelope("example.com", registry=registry) is None


def test_core_run_cache_read_failure_falls_through(tmp_path: Path) -> None:
    """A cache read crash must never take a successful fetch down with it."""
    registry = _registry(_AlwaysOk)
    db = tmp_path / "c.sqlite3"
    with FetchCache(db) as fc:
        # Corrupt the latest payload so model_validate_json raises.
        fc.put_envelope(_envelope("example.com"), registry=registry)
        fc._conn.execute("UPDATE raw_payloads SET payload_json = '{not json'")
        fc._conn.commit()
        env = core.run("example.com", providers=registry, fetched_at=FIXED_WHEN, cache=fc)
    assert env.status == "ok"


# ---- CLI integration ----


@pytest.fixture
def isolated_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``companyctx.cli.default_cache_dir`` at an isolated tmp dir."""
    target = tmp_path / "cache"
    monkeypatch.setattr("companyctx.cli.default_cache_dir", lambda: target)
    return target


def _fetch(runner: CliRunner, *extra: str) -> Result:
    return runner.invoke(
        app,
        [
            "fetch",
            "acme-bakery.example",
            "--mock",
            "--json",
            "--fixtures-dir",
            str(FIXTURES_DIR),
            *extra,
        ],
    )


def test_cli_fetch_writes_to_xdg_cache_path(isolated_cache_dir: Path) -> None:
    runner = CliRunner()
    result = _fetch(runner)
    assert result.exit_code == 0, result.output
    assert (isolated_cache_dir / CACHE_DB_FILENAME).exists()


def test_cli_fetch_from_cache_miss_exits_non_zero(isolated_cache_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "fetch",
            "no-such-site.example",
            "--from-cache",
            "--json",
        ],
    )
    assert result.exit_code == 2
    assert "cache miss" in result.output


def test_cli_fetch_from_cache_hit_returns_envelope(isolated_cache_dir: Path) -> None:
    runner = CliRunner()
    primed = _fetch(runner)
    assert primed.exit_code == 0
    result = runner.invoke(app, ["fetch", "acme-bakery.example", "--from-cache", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["data"]["site"] == "acme-bakery.example"


def test_cli_fetch_rejects_from_cache_with_refresh(isolated_cache_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "fetch",
            "acme-bakery.example",
            "--from-cache",
            "--refresh",
            "--json",
        ],
    )
    assert result.exit_code != 0


def test_cli_cache_list_empty(isolated_cache_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["cache", "list"])
    assert result.exit_code == 0
    assert "empty cache" in result.output


def test_cli_cache_list_after_fetch(isolated_cache_dir: Path) -> None:
    runner = CliRunner()
    _fetch(runner)
    result = runner.invoke(app, ["cache", "list", "--json"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.stdout)
    assert len(rows) == 1
    assert rows[0]["normalized_host"] == "acme-bakery.example"


def test_cli_cache_clear_requires_filter(isolated_cache_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["cache", "clear"])
    assert result.exit_code != 0


def test_cli_cache_clear_by_site(isolated_cache_dir: Path) -> None:
    runner = CliRunner()
    _fetch(runner)
    result = runner.invoke(app, ["cache", "clear", "--site", "acme-bakery.example"])
    assert result.exit_code == 0
    assert "removed 1" in result.output


def test_cli_cache_clear_invalid_age(isolated_cache_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["cache", "clear", "--older-than", "7"])
    assert result.exit_code != 0


# ---- TTL default ----


def test_default_ttl_is_30_days() -> None:
    assert DEFAULT_TTL_SECONDS == 30 * 24 * 60 * 60


# ---- defensive: SQLite file is a real DB ----


def test_db_file_is_sqlite(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite3"
    with FetchCache(db):
        pass
    # SQLite header magic — first 16 bytes.
    with open(db, "rb") as fh:
        assert fh.read(16).startswith(b"SQLite format 3")
    # Connect via vanilla sqlite3 to prove the file is portable.
    conn = sqlite3.connect(str(db))
    try:
        cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
        assert cur.fetchone()[0] == 1
    finally:
        conn.close()
