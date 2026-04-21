<p align="center">
  <img src="docs/assets/hero.jpg" alt="companyctx — context-aware, open-source — retro CRT terminal showing the companyctx wordmark and logo" width="820">
</p>

# companyctx

**Deterministic B2B context router. Zero keys. Schema-locked JSON your agent pipelines can actually trust.**

```bash
pipx install --pip-args="--pre" companyctx   # v0.1.0.dev0 on PyPI — CLI is still stubs (see Status)
companyctx fetch acme-bakery.com --json
```

```json
{
  "status": "ok",
  "data": {
    "site": "acme-bakery.com",
    "fetched_at": "2026-04-20T18:42:11Z",
    "pages":   { "homepage_text": "...", "services": ["cakes", "catering"], "tech_stack": ["WordPress", "Elementor"] },
    "reviews": { "count": 142, "rating": 4.6, "source": "reviews_google_places" },
    "social":  { "handles": { "instagram": "@acmebakery" }, "follower_counts": {} },
    "signals": { "copyright_year": 2024, "last_blog_post_at": "2026-02-11T00:00:00Z", "team_size_claim": "team of 6" }
  },
  "provenance": {
    "site_text_trafilatura": { "status": "ok",            "latency_ms": 412, "error": null,                       "provider_version": "0.1.0" },
    "reviews_google_places": { "status": "not_configured","latency_ms": 0,   "error": "GOOGLE_PLACES_API_KEY not set", "provider_version": "0.1.0" }
  }
}
```

One site in. One schema-locked JSON object out. No API keys for the
zero-key path. Graceful partials on anti-bot blocks. A local SQLite cache
that compounds into a queryable B2B dataset over time.

> **Status:** `v0.1.0.dev0` is on PyPI as a pre-release — name reserved,
> OIDC publish pipeline validated. **The CLI itself is still stubs**: every
> command exits `2`. The first working provider (`site_text_trafilatura`)
> lands in Milestone 2, alongside a measured stealth-fetcher pick. Schema
> + CLI surface are committed in [`docs/SPEC.md`](docs/SPEC.md) and
> [`docs/SCHEMA.md`](docs/SCHEMA.md); architecture in
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## What this is (and isn't)

### IS

- **A schema-locked context router.** The Pydantic v2 envelope is the
  product. Providers come and go; the contract agents consume does not.
- **A Deterministic Waterfall.** Zero-key stealth fetch first →
  smart-proxy provider (if configured) → direct-API provider (if
  configured). Every attempt returns the same shape.
- **A local-first memory layer.** The SQLite cache is not just speed — it
  compounds into a queryable local B2B dataset as a byproduct of normal use.
- **A narrow muscle in the brains-and-muscles pattern.** Your frontier
  model is the brain; `companyctx` is one of many CLIs it pipes through.

### ISN'T

- **Not a scraper competing on scale.** Residential-proxy / headless-browser
  infrastructure is a commodity layer — we compose it via a
  `SmartProxyProvider` interface, we don't out-build it.
- **Not an agent framework.** Orchestration lives upstream.
- **Not a hosted service.** Local pipx CLI. No rented infra. No credits.
- **Not a synthesis engine.** Our output is the input *for* synthesis.
- **Not a Cloudflare bypass.** Zero-key covers the majority of small-biz
  homepages. It won't defeat serious anti-bot — see the
  [coverage matrix](docs/ZERO-KEY.md).
- **Not a people-data tool.** Companies only. Contact enrichment belongs
  upstream (Apollo, Clearbit, manual).
- **Not an MCP server — ever, in our roadmap.** MCP's ~50k-token schema
  dump defeats a muscle built to *save* tokens. Agents find us via
  [`SKILL.md`](SKILL.md); the CLI + `jq` + stdout are the composition
  layer. See [`decisions/2026-04-20-skill-md-not-mcp.md`](decisions/2026-04-20-skill-md-not-mcp.md).

## The Deterministic Waterfall

```
  Attempt 1 — Zero-key stealth       (TLS+HTTP/2 impersonation + trafilatura + extruct)
            ↓  403 / challenge / timeout?
  Attempt 2 — Smart-proxy provider   (user-keyed, vendor-agnostic)
            ↓  still blocked?
  Attempt 3 — Direct-API provider    (user-keyed — Google Places, Yelp Fusion, YouTube)
            ↓
  { status, data, provenance, error?, suggestion? }
```

Every attempt maps to the **same** Pydantic schema. Downstream pipelines
never branch on which attempt succeeded — they branch on the envelope's
`status: ok | partial | degraded`.

On full block with no Attempt-2/3 providers configured:

```json
{
  "status": "partial",
  "data": { "site": "example.com", "fetched_at": "...", "pages": null, "reviews": null, ... },
  "provenance": { "site_text_trafilatura": { "status": "failed", "error": "blocked_by_antibot (HTTP 403)", ... } },
  "error": "blocked_by_antibot",
  "suggestion": "configure a smart-proxy provider key or skip this prospect"
}
```

Never raises. Never crashes your pipeline. Every run comes back well-formed.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full picture and
[`docs/ZERO-KEY.md`](docs/ZERO-KEY.md) for honest anti-bot scoping.

## Zero-key coverage — honestly

| Site class | Zero-key outcome |
|---|---|
| Small-biz WordPress / Squarespace / Wix / Webflow / agency custom | Full payload. Measured **20/20 `status: "ok"`** on a 20-site probe across eight ICP niches at the latest Chrome fingerprint.* |
| Cloudflare Turnstile / DataDome / Akamai / PerimeterX | Clear at a fresh fingerprint; flips to `blocked_by_antibot (HTTP 403)` as the pinned fingerprint ages. Returns `status: "partial"` with actionable `suggestion`. |
| JS-heavy SPAs needing a real browser | HTML shell only. Render-dependent fields come back null. Configure a smart-proxy provider to fill the gap. |
| Aggregator pages (Yelp / Houzz / G2 / Birdeye) | Not the target — use the direct-API providers (`reviews_google_places`, `reviews_yelp_fusion`) instead. |

\* Stealth fetcher: `curl_cffi` pinned to `impersonate="chrome146"`. Spike
method, raw JSONL, and stale-fingerprint decay analysis in
[`docs/ZERO-KEY.md`](docs/ZERO-KEY.md) +
[`research/2026-04-21-tls-impersonation-spike.md`](research/2026-04-21-tls-impersonation-spike.md).
Numbers come from measurement, not marketing.

## Brains-and-muscles pipe

```bash
companyctx fetch acme-bakery.com --json \
  | jq '.data | {site, signals, reviews}' \
  | claude -p "write a 6-section outreach brief from this context"
```

```python
import json, subprocess
ctx = json.loads(subprocess.check_output(["companyctx", "fetch", "acme-bakery.com", "--json"]))
if ctx["status"] == "partial":
    print(f"heads up: {ctx['error']} — {ctx['suggestion']}")
brief = synthesize(ctx["data"])   # your synthesis call, your prompts, your weights
```

`companyctx` never calls an LLM. The brain upstream decides what the
context means.

## Install

Pre-release (name-reservation dev build — CLI commands are stubs that
exit `2`; useful for pipeline wiring, not for real context yet):

```bash
pipx install --pip-args="--pre" companyctx
companyctx --version   # companyctx 0.1.0.dev0
companyctx --help
```

From source (recommended while M2 is in flight):

```bash
git clone https://github.com/dmthepm/companyctx.git
cd companyctx
pip install -e ".[dev,extract,reviews,youtube]"
companyctx --help
```

Once `v0.1.0` ships (first working provider + real `fetch`):

```bash
pipx install companyctx
companyctx fetch example.com --mock --json
```

## Design invariants

- **Schema is the product.** Providers are replaceable; the
  [`CompanyContext`](docs/SCHEMA.md) envelope is not. Raw observations
  only — inference lives in the downstream synthesis layer.
- **Graceful-partial always.** Providers never raise uncaught. Every
  failure maps to `ProviderRunMetadata.status` per provider and the
  top-level `status` on the envelope.
- **Vertical Memory.** Every run persists the full normalized payload to
  SQLite under [XDG paths](https://specifications.freedesktop.org/basedir-spec/).
  `--refresh` forces a re-fetch; `--from-cache` is a cache-only read.
  A `companyctx query ...` DSL on the cache is v0.2 scope, not v0.1.
- **Provider pluggability.** Every deterministic call class is discovered
  via Python entry points (`companyctx.providers`). Day-one providers
  include bus-factor fallbacks (`trafilatura` + `readability-lxml` both
  wired for site text). See [`docs/PROVIDERS.md`](docs/PROVIDERS.md).
- **robots.txt respected by default.** `--ignore-robots` is an explicit
  CLI-only flag; never settable via TOML or env.
- **Deterministic mocks.** `fixtures/<site>/` drives `--mock`; re-runs
  produce byte-identical output modulo `fetched_at`.

## Providers (committed for v0.1)

| Slug | Layer | Category | Key | Cost |
|---|---|---|---|---|
| `site_text_trafilatura` | Zero-key | site_text | — | free |
| `site_text_readability` | Zero-key | site_text (fallback) | — | free |
| `site_meta_extruct` | Zero-key | site_meta | — | free |
| `social_discovery_site` | Zero-key | social_discovery | — | free |
| `signals_site_heuristic` | Zero-key | signals | — | free |
| `reviews_google_places` | Direct-API | reviews | `GOOGLE_PLACES_API_KEY` | per-1k |
| `reviews_yelp_fusion` | Direct-API | reviews | `YELP_API_KEY` | per-call |
| `social_counts_youtube` | Direct-API | social_counts | `YOUTUBE_API_KEY` | free w/ quota |
| `mentions_brave_stub` | Direct-API | mentions | `BRAVE_SEARCH_API_KEY` | per-call |

Full table + `SmartProxyProvider` interface in
[`docs/PROVIDERS.md`](docs/PROVIDERS.md).

## Layout

```
companyctx/            # package
  cli.py               # Typer app
  schema.py            # pydantic v2 models — the JSON contract
  config.py            # pydantic-settings + TOML, XDG-compliant paths
  cache.py             # SQLite fetch cache (Vertical Memory)
  http.py              # stealth fetcher foundation
  robots.py            # robots.txt enforcement
  providers/
    __init__.py        # plugin loader (importlib.metadata.entry_points)
    base.py            # ProviderBase, ProviderError, ProviderRunMetadata
SKILL.md               # ~150-token agent-discovery surface (not MCP)
docs/
  SPEC.md              # frozen v0.1 spec snapshot
  SCHEMA.md            # Pydantic envelope in detail
  ARCHITECTURE.md      # brains-and-muscles + Deterministic Waterfall + Vertical Memory
  ZERO-KEY.md          # honest anti-bot coverage + graceful-partial contract
  PROVIDERS.md         # provider list + SmartProxyProvider interface
  VALIDATION.md        # two-phase acceptance protocol
  REFERENCES.md        # upstream OSS deps
decisions/             # in-repo ADRs (walks-the-walk for OSS readers)
fixtures/              # per-site raw HTML + API responses + expected.json
tests/                 # pytest, hypothesis where useful
```

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Conventional commits, ~400 LOC per
PR, one PR per milestone or provider. ruff + mypy strict + pytest ≥70% cov.
Architecture-shape changes go through `decisions/` first.

## License

[MIT](LICENSE). Copyright 2026 Noontide Collective LLC.

## Support

`companyctx` is open source and free to use. If it earns a place in your
pipeline, consider supporting development by joining Noontide's Main Branch
community on Skool (there's a free trial): <https://skool.com/main>.
