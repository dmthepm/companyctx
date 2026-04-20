"""SQLite-backed fetch cache (opt-in).

Milestone 1: scaffolding only. Implementation — connection, schema, TTL,
key shape `(domain, provider_slug, fetched_at)` — lands in Milestone 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CACHE_DB_FILENAME = "research-pack.sqlite3"


@dataclass(frozen=True)
class CacheKey:
    domain: str
    provider_slug: str


class FetchCache:
    """Placeholder fetch cache. Concrete behavior in M4."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def get(self, key: CacheKey) -> bytes | None:
        raise NotImplementedError

    def put(self, key: CacheKey, payload: bytes, *, ttl_seconds: int) -> None:
        raise NotImplementedError

    def list_entries(self) -> list[CacheKey]:
        raise NotImplementedError

    def clear(self, *, domain: str | None = None, older_than_seconds: int | None = None) -> int:
        raise NotImplementedError


__all__ = ["CACHE_DB_FILENAME", "CacheKey", "FetchCache"]
