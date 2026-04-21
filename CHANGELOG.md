# Changelog

All notable changes to `companyctx` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
