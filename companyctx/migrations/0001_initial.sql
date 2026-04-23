-- Initial cache schema (COX-6 / #9).
--
-- Three user-domain tables:
--   companies     — latest envelope per host, keyed on normalized_host.
--   raw_payloads  — full serialized envelope JSON per run, keyed on run_id.
--   provenance   — one row per provider run, mirrors ProviderRunMetadata.
--
-- The fourth table named in the issue scope, ``schema_version``, is
-- managed by the migration runner itself — it is created during bootstrap
-- in ``cache.py`` so the runner has somewhere to record this very
-- migration's application. It deliberately does not appear in this file.
--
-- Read key shape: (normalized_host, provider_set_hash) + TTL via expires_at.
-- A run's provider_set_hash is derived from sorted (slug, provider_version)
-- pairs of the registry that produced it; bumping a provider's version
-- invalidates old rows without an explicit DELETE.

CREATE TABLE companies (
    normalized_host  TEXT NOT NULL PRIMARY KEY,
    site             TEXT NOT NULL,
    latest_run_id    TEXT NOT NULL,
    latest_status    TEXT NOT NULL,
    latest_fetched_at TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE raw_payloads (
    run_id             TEXT NOT NULL PRIMARY KEY,
    normalized_host    TEXT NOT NULL,
    provider_set_hash  TEXT NOT NULL,
    schema_version     TEXT NOT NULL,
    status             TEXT NOT NULL,
    payload_json       TEXT NOT NULL,
    fetched_at         TEXT NOT NULL,
    expires_at         TEXT NOT NULL,
    created_at         TEXT NOT NULL
);

CREATE INDEX raw_payloads_lookup_idx
    ON raw_payloads (normalized_host, provider_set_hash, fetched_at DESC);

CREATE TABLE provenance (
    normalized_host   TEXT NOT NULL,
    provider_slug     TEXT NOT NULL,
    run_id            TEXT NOT NULL,
    status            TEXT NOT NULL,
    latency_ms        INTEGER NOT NULL,
    error             TEXT,
    provider_version  TEXT NOT NULL,
    cost_incurred     INTEGER NOT NULL DEFAULT 0,
    fetched_at        TEXT NOT NULL,
    PRIMARY KEY (normalized_host, provider_slug, run_id)
);

CREATE INDEX provenance_run_idx ON provenance (run_id);
