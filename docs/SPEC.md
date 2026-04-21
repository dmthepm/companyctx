# SNAPSHOT — canonical at `noontide-projects/boston-v1/decisions/`; do not maintain here

> This file is a frozen snapshot taken at scaffolding time (Milestone 1).
> The canonical spec lives in the upstream design workspace under the
> `companyctx` spec-location/shape decision (schema + CLI shape) and the
> `companyctx` scope-and-brand-lock decision (output contract, Deterministic
> Waterfall, Vertical Memory, `status` enum).
>
> Future spec edits land upstream and flow back via a new handoff cycle, not
> via PRs against this file.

---

# companyctx — v0.1 spec

## Purpose

Take a prospect domain, emit a structured, schema-locked JSON payload about
the **company** at that domain. One downstream synthesis LLM call per prospect
reads the JSON and writes its brief — `companyctx` is the deterministic muscle
that replaces the "LLM reads HTML to extract facts" step.

The collector surfaces **observations**. Inference happens in the synthesis
layer that consumes the JSON. No people data in v0.1 (company side only).

## CLI surface

Built with Typer. Conforms to clig.dev.

| Command | Behavior |
|---|---|
| `companyctx fetch <domain>` | Run all providers for one domain; print or write result. |
| `companyctx batch <csv>` | Run fetch over CSV of domains, write each result to a file. |
| `companyctx validate <json>` | Validate a JSON payload against the pydantic schema. |
| `companyctx cache list` | Inspect cache entries. |
| `companyctx cache clear [--domain X] [--older-than 7d]` | Prune the cache. |
| `companyctx providers list` | Show available providers + their status + cost hint. |

Global flags on `fetch`:

- `--out <path>`, `--json` / `--markdown`, `--verbose`
- `--no-cache` — bypass the cache read path for this run.
- `--refresh` — ignore cache, re-fetch every provider, write fresh back.
- `--from-cache` — return only the cached payload, never hit the network;
  exit non-zero on miss. (First-class Vertical-Memory flag.)
- `--config <toml>`, `--mock` (loads from `fixtures/<domain>/` instead of network).
- `--ignore-robots` — explicit CLI-only; **not** settable via TOML or env.

## Output contract

Every `companyctx fetch` invocation emits one envelope, regardless of whether
the run succeeded, partially succeeded, or was degraded by cache / anti-bot /
missing keys. Downstream pipelines branch on `status`, never on try/except
around a crash.

```
{
  "status": "ok" | "partial" | "degraded",
  "data":   CompanyContext,        // the schema payload (always present, may
                                   //   have nullable fields on partial)
  "provenance": {                  // per-field / per-provider attempt lineage
    <provider_slug>: ProviderRunMetadata,
    ...
  },
  "error":      str | None,        // present when status != "ok"
  "suggestion": str | None         // actionable next step when status != "ok"
}
```

Status semantics:

- **`ok`** — every required provider succeeded and no per-field fallback fired.
- **`partial`** — one or more providers degraded (missing key, anti-bot block,
  timeout), but `data` is still schema-conformant. `error` names the primary
  cause; `suggestion` names the fix (`"configure a smart-proxy provider key"`,
  `"skip this prospect"`, etc.).
- **`degraded`** — result came from cache past its TTL and was used anyway.
  `error` states the cache age; the downstream agent decides whether to trust it.

## Data model (pydantic v2)

```
CompanyContext
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
│    ├─ linkedin_employee_count: int | None   # company-page signal only
│    ├─ hiring_page_active: bool | None
│    ├─ last_funding_round: FundingRound | None
│    ├─ copyright_year: int | None
│    ├─ last_blog_post_at: datetime | None
│    ├─ tech_vs_claim_mismatches: list[str]
```

`ProviderRunMetadata` (in the top-level `provenance` dict, not on the model):

```
ProviderRunMetadata
├─ status: "ok" | "degraded" | "failed" | "not_configured"
├─ latency_ms: int
├─ error: str | None
├─ provider_version: str
```

The `signals` bucket carries **raw observations only**. The synthesis layer
does cross-reference inference (e.g. "team-size claim vs LinkedIn employee
count" or "WordPress detected vs custom-engineering positioning"). The
collector never computes a judgment.

Every field on `CompanyContext` is optional except `domain` and `fetched_at`.
Missing providers degrade — never raise — and surface their reason via
`provenance[slug].status`. The top-level envelope's `status` aggregates these
into a single pipeline-branchable value.

## Provider-plugin interface

Each deterministic call class is a pluggable provider, discovered via Python
entry points:

```toml
[project.entry-points."companyctx.providers"]
site_text_trafilatura  = "companyctx.providers.trafilatura_site:Provider"
site_text_readability  = "companyctx.providers.readability_site:Provider"
site_meta_extruct      = "companyctx.providers.extruct_meta:Provider"
reviews_google_places  = "companyctx.providers.google_places:Provider"
reviews_yelp_fusion    = "companyctx.providers.yelp_fusion:Provider"
social_discovery_site  = "companyctx.providers.social_discovery:Provider"
social_counts_youtube  = "companyctx.providers.youtube_counts:Provider"
signals_site_heuristic = "companyctx.providers.site_heuristic_signals:Provider"
mentions_brave_stub    = "companyctx.providers.brave_search_stub:Provider"
```

Provider contract:

- `class Provider(ProviderBase)`
- `slug: ClassVar[str]`
- `category: ClassVar[Literal["site_text", "site_meta", "reviews", "social_discovery", "social_counts", "signals", "mentions"]]`
- `cost_hint: ClassVar[Literal["free", "per-call", "per-1k"]]`
- `def fetch(self, domain: str, *, ctx: FetchContext) -> tuple[SignalsModel | None, ProviderRunMetadata]`
- Providers **never raise uncaught**. All failure modes map to
  `ProviderRunMetadata.status in {"degraded", "failed", "not_configured"}`.

Providers sit on the **Deterministic Waterfall** (see `docs/ARCHITECTURE.md`):

1. Zero-key stealth fetch first (default).
2. Smart-proxy provider (user-configured) on anti-bot block.
3. Direct-API provider (user-configured) for review/credential fields.

Every attempt maps to the same `CompanyContext` shape. Pipelines never branch
on which attempt succeeded — they branch on the envelope's `status`.

### Day-one providers (committed for v0.1)

- **Site text:** `trafilatura` (primary) + `readability-lxml` (fallback) —
  bus-factor mitigation, both wired day-one.
- **Site metadata:** `extruct` — JSON-LD, microdata, OpenGraph, RDFa,
  schema.org `Organization` + `LocalBusiness` + `sameAs` social handle
  discovery.
- **Reviews:** Google Places via `googlemaps`; Yelp Fusion via `yelpapi`.
  Env-gated; missing key → `status: "not_configured"`.
- **Social discovery:** BeautifulSoup + regex against platform URL shapes
  + extruct `sameAs`.
- **Social counts:** YouTube via `google-api-python-client` `channels.list`
  (ToS-safe). IG / FB / TikTok follower counts stay nullable in v0.1.
- **Signals:** site-heuristic provider — `copyright_year`,
  `last_blog_post_at`, `team_size_claim` (regex), tech-stack detection
  (WordPress / Shopify / Webflow / Wix / Squarespace / custom).
- **Mentions:** Brave Search stub — plumbing only, returns
  `status: "not_configured"` so `providers list` surfaces a clear TODO.

## Cache (Vertical Memory)

SQLite fetch cache under XDG-compliant paths. Opt-in via `--cache` flag or
TOML; disabled by default in v0.1.

- Key: `(normalized_domain, provider_set_hash, provider_slug)` + TTL per
  provider.
- Payload: the full normalized `CompanyContext` payload + `provenance`
  (not raw HTML snippets).
- Schema is versioned alongside the Pydantic model; migrations are
  first-class.
- `companyctx --refresh` forces re-fetch; `companyctx --from-cache` is the
  cache-only mode.

The cache is designed to compound into a queryable local B2B dataset over
normal use. A `companyctx query ...` DSL is v0.2 scope, not v0.1.

## Observability

- Structured run-log: one line per provider invocation with latency + status.
- Stderr in `--verbose`; optional log file.
- Exit code:
  - `0` — envelope `status: "ok"`.
  - `0` — envelope `status: "partial"` (still pipeline-safe, suggestion provided).
  - `1` — envelope `status: "degraded"` (stale cache used) when `--strict` is set.
  - `2` — domain invalid, unreachable, or every provider failed hard.
- Lightweight by design — deep transcripts belong in the downstream pipeline.

## Security and safety

- No credentials in code. All provider secrets via env or TOML config.
  `.env.example` documents required keys per provider. XDG-compliant config
  paths.
- robots.txt respected by default. `--ignore-robots` exists but must be set
  explicitly on the CLI; **not** available via TOML or env.
- No writes outside `$PWD`, `--out`, and the cache dir.

## Distribution

Python 3.10+. `pyproject.toml` + setuptools. MIT license.
`pipx install companyctx`. Dockerfile for reproducibility.
CI: ruff + mypy strict + pytest with coverage. `.claude-plugin/plugin.json`
for Claude Code marketplace compatibility.
