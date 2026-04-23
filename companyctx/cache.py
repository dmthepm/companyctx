"""SQLite-backed fetch cache — Vertical Memory.

Every ``companyctx fetch`` run persists the full normalized envelope to a
local SQLite file under XDG-compliant paths. Over time the user accumulates
a queryable B2B dataset as a side effect of normal use; this is the moat
against hosted actors (Apify / Clearbit / Firecrawl) where the JSON
evaporates per call.

Schema is versioned. Migrations are first-class — numbered SQL files under
:mod:`companyctx.migrations` are applied in ascending order at open time,
each in its own transaction. There are no implicit ``ALTER TABLE`` calls.

Read-key shape: ``(normalized_host, provider_set_hash)`` + TTL. The
``provider_set_hash`` is derived from sorted ``(slug, provider_version)``
pairs of the registry that produced the row, so bumping a provider's
version naturally invalidates stale rows without an explicit DELETE.

See COX-6 / GitHub #9 for scope. The ``companyctx query`` DSL over the
cache is v0.2 design surface and intentionally not part of M3.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path
from urllib.parse import urlparse

from companyctx.providers.base import ProviderBase
from companyctx.schema import (
    SCHEMA_VERSION,
    Envelope,
    ProviderRunMetadata,
)

CACHE_DB_FILENAME = "companyctx.sqlite3"
DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days — provider-specific TTLs are M4+.
MIGRATIONS_PACKAGE = "companyctx.migrations"

_MIGRATION_FILENAME_RE = re.compile(r"^(\d{4})_[\w\-]+\.sql$")


@dataclass(frozen=True)
class CacheKey:
    """Envelope-level cache key.

    ``provider_set_hash`` reflects the registry that produced the row; reads
    must compute the same hash from the current registry to avoid serving
    stale rows after a provider version bump.
    """

    normalized_host: str
    provider_set_hash: str


@dataclass(frozen=True)
class CacheEntry:
    """A single cached envelope row, surfaced by ``cache list``."""

    normalized_host: str
    site: str
    status: str
    fetched_at: datetime
    expires_at: datetime
    schema_version: str
    run_id: str


def normalize_host(site: str) -> str:
    """Canonicalize a site identifier into the cache's primary key.

    Accepts ``example.com``, ``https://example.com``, ``Example.COM/path``,
    ``www.example.com`` — all collapse to ``example.com``. Raises
    :class:`ValueError` for empty / unparseable input so cache writes can't
    silently key on garbage.
    """
    if not site or not site.strip():
        raise ValueError("site is empty")
    raw = site.strip()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.netloc or parsed.path).lower().strip("/")
    if not host:
        raise ValueError(f"could not normalize host from {site!r}")
    if host.startswith("www."):
        host = host[4:]
    # Drop port if present (cache keys are host-only — port is a fetcher
    # concern, not a vertical-memory one).
    if ":" in host:
        host = host.split(":", 1)[0]
    if not host:
        raise ValueError(f"could not normalize host from {site!r}")
    return host


def provider_set_hash(registry: Mapping[str, type[ProviderBase]]) -> str:
    """Stable hash of ``(slug, provider_version)`` pairs in the registry.

    Two registries with the same slugs but a bumped ``version`` on any
    provider produce different hashes — that's the cache-invalidation
    contract. SHA-256 truncated to 16 hex chars is plenty for keying;
    collisions on a per-host bucket would require ~2^64 distinct provider
    sets per site.
    """
    pairs = sorted(
        (slug, str(getattr(cls, "version", "unknown"))) for slug, cls in registry.items()
    )
    canonical = json.dumps(pairs, separators=(",", ":"), sort_keys=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class FetchCache:
    """SQLite-backed envelope cache.

    The connection is opened per instance and held open. Callers should
    use the cache as a context manager or call :meth:`close` explicitly;
    leaking connections on long-running daemons is the user's problem,
    not ours (the CLI is one-shot per invocation).
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def __enter__(self) -> FetchCache:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    # ----- migrations -----

    def schema_version(self) -> int:
        cur = self._conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        row = cur.fetchone()
        return int(row["version"]) if row else 0

    def _migrate(self) -> None:
        """Apply every pending migration in ascending order.

        Each migration runs inside its own transaction; a failure leaves the
        database at the previous version, never half-migrated.
        """
        # Bootstrap: schema_version must exist before we can read the version.
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version "
            "(version INTEGER NOT NULL, applied_at TEXT NOT NULL)"
        )
        self._conn.commit()

        current = self.schema_version()
        for number, sql in _discover_migrations():
            if number <= current:
                continue
            with self._conn:
                self._conn.executescript(sql)
                self._conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (number, _utc_now().isoformat()),
                )

    # ----- write path -----

    def put_envelope(
        self,
        envelope: Envelope,
        *,
        registry: Mapping[str, type[ProviderBase]],
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        now: datetime | None = None,
    ) -> str:
        """Persist ``envelope`` and return the new ``run_id``.

        Writes one row to ``raw_payloads`` (the full envelope JSON), one
        row per provider to ``provenance``, and upserts the ``companies``
        latest-pointer. Old rows are kept intact for audit — ``--refresh``
        is a shadow-write, not a replace.
        """
        host = normalize_host(envelope.data.site)
        run_id = uuid.uuid4().hex
        now = now or _utc_now()
        expires = now + timedelta(seconds=ttl_seconds)
        payload_json = envelope.model_dump_json()
        psh = provider_set_hash(registry)

        with self._conn:
            self._conn.execute(
                "INSERT INTO raw_payloads "
                "(run_id, normalized_host, provider_set_hash, schema_version, "
                " status, payload_json, fetched_at, expires_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    host,
                    psh,
                    envelope.schema_version,
                    envelope.status,
                    payload_json,
                    envelope.data.fetched_at.isoformat(),
                    expires.isoformat(),
                    now.isoformat(),
                ),
            )
            for slug, meta in envelope.provenance.items():
                self._conn.execute(
                    "INSERT INTO provenance "
                    "(normalized_host, provider_slug, run_id, status, latency_ms, "
                    " error, provider_version, cost_incurred, fetched_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        host,
                        slug,
                        run_id,
                        meta.status,
                        meta.latency_ms,
                        meta.error,
                        meta.provider_version,
                        meta.cost_incurred,
                        envelope.data.fetched_at.isoformat(),
                    ),
                )
            self._conn.execute(
                "INSERT INTO companies "
                "(normalized_host, site, latest_run_id, latest_status, "
                " latest_fetched_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(normalized_host) DO UPDATE SET "
                " site = excluded.site, "
                " latest_run_id = excluded.latest_run_id, "
                " latest_status = excluded.latest_status, "
                " latest_fetched_at = excluded.latest_fetched_at, "
                " updated_at = excluded.updated_at",
                (
                    host,
                    envelope.data.site,
                    run_id,
                    envelope.status,
                    envelope.data.fetched_at.isoformat(),
                    now.isoformat(),
                ),
            )
        return run_id

    # ----- read path -----

    def get_envelope(
        self,
        site: str,
        *,
        registry: Mapping[str, type[ProviderBase]],
        now: datetime | None = None,
    ) -> Envelope | None:
        """Return the freshest non-expired envelope for ``site`` or ``None``.

        Misses (no row, expired row, mismatched ``provider_set_hash``) all
        return ``None``. The caller decides how to react — the orchestrator
        falls through to a fresh fetch; ``--from-cache`` exits non-zero.
        """
        host = normalize_host(site)
        psh = provider_set_hash(registry)
        now = now or _utc_now()
        cur = self._conn.execute(
            "SELECT payload_json, expires_at FROM raw_payloads "
            "WHERE normalized_host = ? AND provider_set_hash = ? "
            "ORDER BY fetched_at DESC LIMIT 1",
            (host, psh),
        )
        row = cur.fetchone()
        if row is None:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= now:
            return None
        return Envelope.model_validate_json(row["payload_json"])

    # ----- list / clear -----

    def list_entries(self) -> list[CacheEntry]:
        """Enumerate latest envelope rows across all hosts (one per host)."""
        cur = self._conn.execute(
            "SELECT c.normalized_host, c.site, c.latest_status, "
            "       c.latest_run_id, r.fetched_at, r.expires_at, "
            "       r.schema_version "
            "FROM companies c "
            "JOIN raw_payloads r ON r.run_id = c.latest_run_id "
            "ORDER BY c.normalized_host"
        )
        return [
            CacheEntry(
                normalized_host=str(row["normalized_host"]),
                site=str(row["site"]),
                status=str(row["latest_status"]),
                fetched_at=datetime.fromisoformat(row["fetched_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                schema_version=str(row["schema_version"]),
                run_id=str(row["latest_run_id"]),
            )
            for row in cur.fetchall()
        ]

    def clear(
        self,
        *,
        site: str | None = None,
        older_than: timedelta | None = None,
        now: datetime | None = None,
    ) -> int:
        """Delete cache rows. Returns the count of ``raw_payloads`` rows removed.

        ``site`` and ``older_than`` may be combined; both default to ``None``
        meaning "all rows". An empty matcher (no flags) clears the entire
        cache — the CLI guards against that, but the core API is honest.
        """
        now = now or _utc_now()
        clauses: list[str] = []
        params: list[object] = []
        if site is not None:
            clauses.append("normalized_host = ?")
            params.append(normalize_host(site))
        if older_than is not None:
            clauses.append("fetched_at < ?")
            params.append((now - older_than).isoformat())
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

        with self._conn:
            cur = self._conn.execute(
                f"SELECT run_id, normalized_host FROM raw_payloads{where}", params
            )
            rows = cur.fetchall()
            if not rows:
                return 0
            run_ids = [r["run_id"] for r in rows]
            hosts = {r["normalized_host"] for r in rows}
            qmarks = ",".join("?" for _ in run_ids)
            self._conn.execute(f"DELETE FROM provenance WHERE run_id IN ({qmarks})", run_ids)
            self._conn.execute(f"DELETE FROM raw_payloads WHERE run_id IN ({qmarks})", run_ids)
            # Drop the companies pointer when no rows remain for the host.
            for host in hosts:
                cur2 = self._conn.execute(
                    "SELECT 1 FROM raw_payloads WHERE normalized_host = ? LIMIT 1",
                    (host,),
                )
                if cur2.fetchone() is None:
                    self._conn.execute("DELETE FROM companies WHERE normalized_host = ?", (host,))
                else:
                    # Re-point latest to the freshest surviving row.
                    cur3 = self._conn.execute(
                        "SELECT run_id, status, fetched_at FROM raw_payloads "
                        "WHERE normalized_host = ? "
                        "ORDER BY fetched_at DESC LIMIT 1",
                        (host,),
                    )
                    survivor = cur3.fetchone()
                    if survivor is not None:
                        self._conn.execute(
                            "UPDATE companies SET "
                            " latest_run_id = ?, latest_status = ?, "
                            " latest_fetched_at = ?, updated_at = ? "
                            "WHERE normalized_host = ?",
                            (
                                survivor["run_id"],
                                survivor["status"],
                                survivor["fetched_at"],
                                now.isoformat(),
                                host,
                            ),
                        )
            return len(run_ids)

    # ----- introspection -----

    def provenance_for(self, run_id: str) -> dict[str, ProviderRunMetadata]:
        """Reconstruct the per-provider metadata map for one run."""
        cur = self._conn.execute(
            "SELECT provider_slug, status, latency_ms, error, provider_version, cost_incurred "
            "FROM provenance WHERE run_id = ? ORDER BY provider_slug",
            (run_id,),
        )
        return {
            str(row["provider_slug"]): ProviderRunMetadata(
                status=row["status"],
                latency_ms=int(row["latency_ms"]),
                error=row["error"],
                provider_version=str(row["provider_version"]),
                cost_incurred=int(row["cost_incurred"]),
            )
            for row in cur.fetchall()
        }


def parse_age(text: str) -> timedelta:
    """Parse ``cache clear --older-than`` arguments like ``7d``, ``12h``, ``30m``.

    Supported units: ``s`` (seconds), ``m`` (minutes), ``h`` (hours),
    ``d`` (days). Bare integers are rejected — explicit units only — to
    avoid the ``--older-than 7`` "is that minutes or days?" trap.
    """
    match = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", text)
    if match is None:
        raise ValueError(
            f"invalid age {text!r}: expected '<int><unit>' where unit is s, m, h, or d"
        )
    n, unit = int(match.group(1)), match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return timedelta(seconds=n * multipliers[unit])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _discover_migrations() -> list[tuple[int, str]]:
    """Return ``(number, sql)`` pairs for every migration on disk, sorted.

    Filenames must match ``NNNN_<slug>.sql``; stray files are ignored to
    keep accidental editor backups (``.swp``, ``.bak``) from breaking the
    runner. The sort is by number, not lexicographically, so a future
    re-numbering past 9999 doesn't silently re-order.
    """
    out: list[tuple[int, str]] = []
    package = resources.files(MIGRATIONS_PACKAGE)
    for entry in package.iterdir():
        match = _MIGRATION_FILENAME_RE.match(entry.name)
        if match is None:
            continue
        out.append((int(match.group(1)), entry.read_text(encoding="utf-8")))
    out.sort(key=lambda pair: pair[0])
    return out


# Re-exported for tests that want to drive an explicit migration without
# touching the discovery path. Not part of the public surface.
def apply_migration_sql(conn: sqlite3.Connection, number: int, sql: str) -> None:
    """Apply one migration SQL block + bump the version table."""
    with conn:
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (number, _utc_now().isoformat()),
        )


__all__ = [
    "CACHE_DB_FILENAME",
    "DEFAULT_TTL_SECONDS",
    "SCHEMA_VERSION",
    "CacheEntry",
    "CacheKey",
    "FetchCache",
    "apply_migration_sql",
    "normalize_host",
    "parse_age",
    "provider_set_hash",
]
