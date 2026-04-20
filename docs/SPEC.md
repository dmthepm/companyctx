# SNAPSHOT — canonical at `noontide-projects/boston-v1/decisions/2026-04-20-research-pack-spec-location-and-shape.md`; do not maintain here

> This file is a frozen snapshot taken at scaffolding time (Milestone 1).
> Future spec edits land in the canonical workspace and flow back via a new
> handoff cycle, not via PRs against this file.

---

# research-pack — v0.1 spec

## Purpose

Take a prospect domain, emit a structured research-pack JSON. One synthesis
LLM call per prospect reads the JSON and writes a 6-section brief
(Differentiator / Audience / Content & Social / Credentials & Proof / Gap /
5 Script Angles) — matching the downstream consumer's Phase 1 output contract.

The collector surfaces **observations**. Inference happens in the synthesis
layer that consumes the JSON.

## CLI surface

Built with Typer. Conforms to clig.dev.

| Command | Behavior |
|---|---|
| `research-pack fetch <domain>` | Run all providers for one domain; print or write result. |
| `research-pack batch <csv>` | Run fetch over CSV of domains, write each result to a file. |
| `research-pack validate <json>` | Validate a research-pack JSON against the pydantic schema. |
| `research-pack cache list` | Inspect cache entries. |
| `research-pack cache clear [--domain X] [--older-than 7d]` | Prune the cache. |
| `research-pack providers list` | Show available providers + their status. |

Global flags: `--out <path>`, `--json` / `--markdown`, `--verbose`,
`--no-cache`, `--config <toml>`, `--mock` (loads from `fixtures/<domain>/`
instead of network).

## Data model (pydantic v2)

```
ResearchPack
├─ domain: str                         # required
├─ fetched_at: datetime                # required
├─ site: SiteSignals
│    ├─ homepage_text: str             # cleaned, extractor-agnostic
│    ├─ about_text: str | None
│    ├─ services: list[str]
│    ├─ tech_stack: list[str]          # detected, not claimed
├─ reviews: ReviewSignals | None
│    ├─ count: int
│    ├─ rating: float | None
│    ├─ source: str                    # provider slug
├─ social: SocialSignals
│    ├─ handles: dict[platform, handle]
│    ├─ follower_counts: dict[platform, int]
├─ mentions: list[MediaMention]        # award, press, podcast, etc.
├─ signals: CrossReferenceSignals      # raw observations only
│    ├─ team_size_claim: str | None    # e.g. "team of 6"
│    ├─ linkedin_employee_count: int | None
│    ├─ hiring_page_active: bool | None
│    ├─ last_funding_round: FundingRound | None
│    ├─ copyright_year: int | None
│    ├─ last_blog_post_at: datetime | None
│    ├─ tech_vs_claim_mismatches: list[str]
├─ provenance: dict[provider_slug, ProviderRunMetadata]
     ├─ status: "ok" | "degraded" | "failed"
     ├─ latency_ms: int
     ├─ error: str | None
     ├─ provider_version: str
```

The `signals` bucket carries **raw observations only**. The synthesis layer
does cross-reference inference (e.g. "team-size claim vs LinkedIn employee
count" or "WordPress detected vs custom-engineering positioning"). The
collector never computes a judgment.

Every field is optional except `domain` and `fetched_at`. Missing providers
degrade — never raise — and surface their reason via
`provenance[slug].status`.

## Provider-plugin interface

Each deterministic call class is a pluggable provider, discovered via Python
entry points:

```toml
[project.entry-points."research_pack.providers"]
site_text_trafilatura  = "research_pack.providers.trafilatura_site:Provider"
site_text_readability  = "research_pack.providers.readability_site:Provider"
site_meta_extruct      = "research_pack.providers.extruct_meta:Provider"
reviews_google_places  = "research_pack.providers.google_places:Provider"
reviews_yelp_fusion    = "research_pack.providers.yelp_fusion:Provider"
social_discovery_site  = "research_pack.providers.social_discovery:Provider"
social_counts_youtube  = "research_pack.providers.youtube_counts:Provider"
signals_site_heuristic = "research_pack.providers.site_heuristic_signals:Provider"
mentions_brave_stub    = "research_pack.providers.brave_search_stub:Provider"
```

Provider contract:

- `class Provider(ProviderBase)`
- `slug: ClassVar[str]`
- `category: ClassVar[Literal["site_text", "site_meta", "reviews", "social_discovery", "social_counts", "signals", "mentions"]]`
- `cost_hint: ClassVar[Literal["free", "per-call", "per-1k"]]`
- `def fetch(self, domain: str, *, timeout_s: float, ctx: FetchContext) -> tuple[SignalsModel | None, ProviderRunMetadata]`
- Providers **never raise uncaught**. All failure modes map to
  `ProviderRunMetadata.status in {"degraded", "failed"}`.

### Day-one providers (committed for v0.1)

- **Site text:** `trafilatura` (primary) + `readability-lxml` (fallback) —
  bus-factor mitigation, both wired day-one.
- **Site metadata:** `extruct` — JSON-LD, microdata, OpenGraph, RDFa,
  schema.org `Organization` + `LocalBusiness` + `sameAs` social handle
  discovery.
- **Reviews:** Google Places via `googlemaps`; Yelp Fusion via `yelpapi`.
  Env-gated; missing key → `status: "degraded"`.
- **Social discovery:** BeautifulSoup + regex against platform URL shapes
  + extruct `sameAs`.
- **Social counts:** YouTube via `google-api-python-client` `channels.list`
  (ToS-safe). IG / FB / TikTok follower counts stay nullable in v0.1.
- **Signals:** site-heuristic provider — `copyright_year`,
  `last_blog_post_at`, `team_size_claim` (regex), tech-stack detection
  (WordPress / Shopify / Webflow / Wix / Squarespace / custom).
- **Mentions:** Brave Search stub — plumbing only, returns
  `status: "not_configured"` so `providers list` surfaces a clear TODO.

## Cache

Optional SQLite fetch cache keyed on `(domain, provider_slug, fetched_at)`
with per-provider TTL. Off by default; opt-in via `--cache` flag or TOML.

## Observability

- Structured run-log: one line per provider invocation with latency + status.
- Stderr in `--verbose`; optional log file.
- Exit code: `0` if at least one provider succeeded; non-zero only if the
  domain itself was invalid or all providers failed hard.
- Lightweight by design — deep transcripts belong in the downstream pipeline.

## Security and safety

- No credentials in code. All provider secrets via env or TOML config.
  `.env.example` documents required keys per provider. XDG-compliant config
  paths.
- robots.txt respected by default. `--ignore-robots` exists but must be set
  explicitly; **not** available via TOML.
- No writes outside `$PWD`, `--out`, and the cache dir.

## Distribution

Python 3.10+. `pyproject.toml` + setuptools. MIT license.
`pipx install research-pack`. Dockerfile for reproducibility.
CI: ruff + mypy strict + pytest with coverage. `.claude-plugin/plugin.json`
for Claude Code marketplace compatibility.
