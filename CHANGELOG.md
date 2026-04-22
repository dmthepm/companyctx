# Changelog

All notable changes to `companyctx` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed — envelope schema bump (v0.3)

- **`schema_version` bumped to `"0.3.0"`.** Adding the `empty_response`
  code to the closed `EnvelopeError.code` Literal is a minor schema
  bump. v0.2.0 envelopes still validate under the old Literal but the
  orchestrator now emits `"0.3.0"` on every run.
- **New `empty_response` error code (COX-44 / #79).** Zero-key
  `site_text_trafilatura` now checks the extracted homepage text
  against `EMPTY_RESPONSE_BYTES = 64`; below that, the provider
  surfaces `status: "failed"`, `error: "empty_response"`, and the
  orchestrator lands `error.code: "empty_response"` at the envelope
  top level with an actionable suggestion. Retires the
  "empty-body silent-success" disclosure added to v0.2.0 Known
  Limitations. Automatic smart-proxy retry on empty is intentionally
  out of scope — the recovery path skips `empty_response` rows.

### Added

- **`companyctx providers list --json`** — registry introspection as a JSON
  array (one dict per provider). Columns: `slug`, `tier`
  (`zero-key` / `smart-proxy` / `direct-api`), `category`, `cost_hint`,
  `status` (`ready` / `not_configured`), `reason`. Text-mode output gains
  the same columns. Closes #68 Part B.
- **Optional `required_env` class var** on providers. `smart_proxy_http`
  declares `COMPANYCTX_SMART_PROXY_URL`; the CLI surfaces missing entries
  as `not_configured` + a human-readable reason.

### Changed

- **Docs honesty pass (post-v0.2-tag).** README hero envelope, status
  block, provider tables, `docs/SPEC.md`, `docs/SCHEMA.md`, `SKILL.md`,
  and every file in `examples/` now describe the actual shipped v0.2
  surface (zero-key + smart-proxy + `schema_version` + structured
  `EnvelopeError`). Reserved-but-deferred features (SQLite cache,
  `--from-cache` / `--refresh`, `batch`, direct-API providers,
  `signals_site_heuristic`, `--markdown`) are labelled with tracking
  issues. Every example's expected-output block and bash / Python
  script runs clean against `v0.2.0`. Closes #67.
- **`fetch --markdown` help text** explicitly labels the flag
  experimental + not implemented in v0.2 (already rejects at runtime).
- **Examples now resolve `fixtures/` relative to the script** instead of
  `Path("fixtures")` so `06-competitor-monitor.py`,
  `07-inbound-webhook-enrichment/main.py`, and `08-support-ticket-context.py`
  run clean from any CWD.

## [0.2.0] — 2026-04-22

### Changed — BREAKING (envelope schema)

- **Envelope `error` changed from `str | None` to a structured
  `EnvelopeError | None`** with machine-readable `code`, human-readable
  `message`, and actionable `suggestion`. Agents branching on the old
  free-text `error` substring will need to switch to `error.code`. The
  former top-level `suggestion` field is removed; it now lives inside
  `EnvelopeError.suggestion`. SemVer-major for the envelope contract;
  SemVer-minor for the package. See COX-37 / #70.
- `error.code` is a closed Literal: `ssrf_rejected | network_timeout |
  blocked_by_antibot | path_traversal_rejected | response_too_large |
  no_provider_succeeded | misconfigured_provider`. New codes land in
  minor releases and bump `schema_version`.

### Added

- **New top-level `schema_version: Literal["0.2.0"]` envelope field.**
  Consumers can branch on shape without substring-parsing. v0.1 envelopes
  lack this field and fail validation under `extra="forbid"`.
- **`companyctx schema` CLI verb.** Dumps the envelope's Draft 2020-12 JSON
  Schema to stdout. Agents validate against our shape without importing
  `companyctx`.
- **`companyctx/py.typed` marker (PEP 561).** Ships in wheel + sdist so
  downstream `mypy` users see concrete Pydantic types instead of `Any`.
- **Public-API re-exports in `companyctx/__init__.py`.** `from companyctx
  import Envelope` (and every other public model) now works without
  reaching into `companyctx.schema`. Closes #56.

### Changed (CLI honesty — #68 Part A)

- `--from-cache` / `--refresh` / `--no-cache` / `--config` previously were
  accepted silently and ignored. They now raise `typer.BadParameter` with a
  link to the tracking issue (#9 — SQLite cache schema + migrations; the
  v0.2.0 messages originally named a phantom tracking number, corrected in
  the Unreleased block below). No silent-pass behavior for contracts the
  tool does not honour.
- `batch` / `cache list` / `cache clear` previously exited 2 with no output.
  They now print `<command> is not implemented in v0.2.0 — see #N` to
  stderr before exiting non-zero.
- Dev-dep version bounds tightened from `>=` to `~=` (compatible-release)
  for `ruff`, `mypy`, `pytest`, `pytest-cov`, `hypothesis` — matches the
  `curl_cffi` policy already in core deps.

## [0.1.0] — 2026-04-21

### Added

- **M2 envelope + orchestrator + first working provider (#15).** `companyctx
  fetch <site> --mock --json` now emits a schema-valid `Envelope` instead of
  exiting 2. Full `{status, data, provenance, error?, suggestion?}` shape per
  `docs/SPEC.md`, every model `extra="forbid"`.
- **Deterministic Waterfall orchestrator** (`companyctx/core.py`). Discovers
  providers via `importlib.metadata.entry_points("companyctx.providers")`,
  runs them in deterministic slug order, aggregates per-provider status into
  top-level `ok | partial | degraded`, attaches actionable `suggestion` on
  non-ok. Never raises at the boundary — a provider that throws still lands
  as a `failed` row.
- **First zero-key provider `site_text_trafilatura`**. Extracts
  `pages.homepage_text` / `about_text` / `services` / `tech_stack` from the
  fixture corpus (`--mock` path) and from live HTTP (Attempt 1 of the
  waterfall). Graceful-partial on 401/403/timeout.
- `companyctx providers list` walks registered entry points and prints slug /
  category / cost hint (was exit-2 stub).
- `companyctx validate <path>` round-trips a JSON file through the envelope
  (was exit-2 stub).
- `ProviderRunMetadata.cost_incurred` (int cents, default `0`) so the
  envelope can surface per-provider spend.
- `trafilatura` moved from the `[extract]` extra into core dependencies —
  zero-key text extraction is now the default install path.
- **Regression-corpus validation** (`tests/test_regression_corpus.py`). Five
  fixtures — `acme-bakery`, `coastal-fitness`, `midtown-auto`,
  `mapleridge-contractor`, `oakleaf-bakery` — are pinned as a byte-diff
  regression suite. Together they touch every detectable tech-stack branch
  plus the empty-`tech_stack` (no-markers) case across three niches. These
  are regression snapshots, not real golden oracles; the rationale + coverage
  table lives in `fixtures/README.md`.
- **`scripts/build-fixtures.py` now generates `expected.json` by running the
  orchestrator** against the just-written HTML, so the committed fixtures
  stay in lockstep with `companyctx.core.run` as regression snapshots. This
  is useful for drift detection, not as an independent oracle. All 30
  `expected.json` files regenerated to the M2 shape (raw observations in
  `pages`; non-`pages` slots null until their providers land).

### Notes / follow-ups

- TLS-impersonation library choice (issue #15 acceptance checkbox) remains
  blocked on the 10-site network spike; `decisions/2026-04-20-zero-key-stealth-strategy.md`
  stays **proposed**. The provider's `_stealth_fetch` currently uses
  `requests` + a realistic Chrome UA as a placeholder; swap to `curl_cffi`
  once the spike lands.

## [0.1.0.dev0] - 2026-04-20

First PyPI publish. Pre-release dev marker. Reserves the `companyctx` name
and validates the OIDC trusted-publisher pipeline end-to-end. Every CLI
command still exits `2` — the first working provider lands in Milestone 2.

### Added

- **PyPI trusted-publisher release pipeline.** `.github/workflows/publish.yml`
  triggers on `release: published`, builds sdist+wheel, and uploads via
  `pypa/gh-action-pypi-publish@release/v1` using short-lived OIDC — no
  long-lived PyPI token in the repo. The `publish` job is gated on a
  `pypi` GitHub Environment with Devon as required reviewer; deployments
  are restricted to `v*` tags.
- Repo scaffolding (Milestone 1): `pyproject.toml`, package skeleton, CI, docs,
  issue/PR templates, MIT license, contributor covenant.
- `fetch --refresh` and `fetch --from-cache` CLI stubs (surface only; behavior
  wired in M4 alongside the real cache). These are first-class Vertical-Memory
  flags, not afterthought `--no-cache` inversions.
- `docs/SPEC.md` snapshot now specifies the top-level
  `{status: ok | partial | degraded, data, provenance, error?, suggestion?}`
  envelope and the Deterministic Waterfall provider attempt order.
- `docs/ARCHITECTURE.md` — brains-and-muscles framing, Deterministic
  Waterfall diagram, Vertical Memory cache posture.
- `docs/SCHEMA.md` — Pydantic envelope in detail (`CompanyContext` +
  sub-models + `ProviderRunMetadata`).
- `docs/ZERO-KEY.md` — honest anti-bot coverage matrix, graceful-partial
  contract, M1 stealth-fetcher spike deliverables.
- `docs/PROVIDERS.md` — day-one provider table with cost hints,
  `SmartProxyProvider` interface shape, write-your-own-provider guide.
- In-repo `decisions/` folder with the three load-bearing ADRs:
  `2026-04-20-name-change-to-companyctx.md` (accepted),
  `2026-04-20-zero-key-stealth-strategy.md` (proposed — library choice
  pending an M1 spike), and `2026-04-20-skill-md-not-mcp.md` (accepted).
  Walks-the-walk artifact for the OSS audience.
- `SKILL.md` at the repo root — ~150-token agent-discovery surface
  (purpose, commands, rules for agents, one bash example). Noontide-wide
  posture: CLI + `SKILL.md`, not MCP.
- README rewritten around zero-key hero + IS/ISN'T values +
  Deterministic Waterfall diagram + honest coverage matrix +
  brains-and-muscles pipe example + single Main Branch breadcrumb. ISN'T
  list now includes the explicit "Not an MCP server — ever, in our
  roadmap" line.

### Changed

- **Renamed `research-pack` → `companyctx`.** GitHub repo and PyPI package.
  See `decisions/2026-04-20-name-change-to-companyctx.md` (in-repo ADR landing
  in the same M1 PR).
- **Vocabulary swap `domain` → `site` across user-facing surfaces.** CLI
  positional arg (`companyctx fetch <site>`), schema identifier field
  (`CompanyContext.site`), cache-clear option (`--site`), fixture layout
  (`fixtures/<site>/`), and all docs prose. Avoids the collision with
  "problem domain" / "domain-driven design" / "domain expertise." The
  existing `site: SiteSignals` sub-model — which held homepage-derived
  content — moves to `pages: SiteSignals` to free up `site` for the
  identifier. Internal normalized forms stay as `host` / `origin`.

### Fixed
