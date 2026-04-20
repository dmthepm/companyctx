# research-pack

**A deterministic research-pack collector for outreach pipelines. Domain in, JSON out.**

`research-pack` replaces the "LLM reads HTML to extract facts" step of an outreach
research pipeline with a deterministic, schema-locked, cached, mockable Python CLI.
You give it a prospect domain, it returns a pydantic-validated JSON pack: cleaned
site text, structured site metadata, review counts and ratings, social handles
(and follower counts where ToS-safe), media mentions, and a bucket of raw
cross-reference observations a downstream synthesis model can reason over.

The collector surfaces **observations**. Inference happens in the synthesis layer
that consumes the JSON.

> Status: v0.1 in development. Not yet on PyPI. Schema and CLI surface are
> committed in [`docs/SPEC.md`](docs/SPEC.md); see [`docs/VALIDATION.md`](docs/VALIDATION.md)
> for the gating protocol.

## The problem

Outreach research pipelines that pay an LLM to read raw HTML for every prospect
burn through tokens on work that is fundamentally deterministic — fetch the page,
parse the about section, count the reviews, discover the social handles, scan
for a copyright year. At ~8 prospects/night that is real money. At 10x–20x
nightly volume it dominates the budget.

The fix is not "a better LLM." The fix is to do the deterministic work
deterministically and hand the LLM a clean, schema-locked input.

## The shape

```
research-pack fetch acmebakery.com --json
```

```json
{
  "domain": "acmebakery.com",
  "fetched_at": "2026-04-20T18:42:11Z",
  "site": { "homepage_text": "...", "services": [...], "tech_stack": [...] },
  "reviews": { "count": 142, "rating": 4.6, "source": "google_places" },
  "social": { "handles": {"instagram": "@acmebakery"}, "follower_counts": {} },
  "mentions": [],
  "signals": {
    "copyright_year": 2024,
    "last_blog_post_at": "2026-02-11T00:00:00Z",
    "team_size_claim": "team of 6",
    "tech_vs_claim_mismatches": []
  },
  "provenance": {
    "site_text_trafilatura": { "status": "ok", "latency_ms": 412, "error": null },
    "reviews_google_places":  { "status": "degraded", "latency_ms": 0, "error": "GOOGLE_PLACES_API_KEY not set" }
  }
}
```

Every field is optional except `domain` and `fetched_at`. Missing providers
degrade to `provenance[slug].status: "degraded"` with a clear reason — they do
not raise, they do not poison the pack.

## The install

> Not yet published. During v0.1 development:

```bash
git clone https://github.com/dmthepm/research-pack.git
cd research-pack
pip install -e ".[dev,extract,reviews,youtube]"
research-pack --help
```

Once v0.1.0 ships:

```bash
pipx install research-pack
research-pack fetch example.com --mock --json
```

## Design invariants

- **Collector surfaces observations; inference lives in the synthesis layer.**
  The `signals: CrossReferenceSignals` bucket carries raw fields (copyright year,
  last-blog-post timestamp, team-size claim) — not judgments.
- **Every provider is optional and degrades gracefully.** Missing API keys
  produce `status: "degraded"` in `provenance`, never an uncaught exception.
- **Every deterministic call class is a pluggable provider** discovered via
  Python entry points (`research_pack.providers`). Day-one bus-factor mitigation:
  `trafilatura` and `readability-lxml` both wired for site text.
- **Network behavior is fully mockable** via `fixtures/<domain>/`. `--mock`
  reproduces results byte-identically modulo `fetched_at`.
- **robots.txt is respected by default.** `--ignore-robots` is an explicit
  CLI flag and is not settable via TOML config.

## Providers (committed for v0.1)

| Slug | Class | Cost | Status |
|---|---|---|---|
| `site_text_trafilatura` | site text (primary) | free | M3 |
| `site_text_readability` | site text (fallback) | free | M3 |
| `site_meta_extruct` | JSON-LD / OG / `sameAs` | free | M3 |
| `reviews_google_places` | Google Places | per-1k | M3 (env-gated) |
| `reviews_yelp_fusion` | Yelp Fusion | per-call | M3 (env-gated) |
| `social_discovery_site` | platform handles via HTML + `sameAs` | free | M3 |
| `social_counts_youtube` | YouTube channel `channels.list` | free w/ quota | M3 (env-gated) |
| `signals_site_heuristic` | copyright year, last blog post, team-size claim, tech-stack | free | M3 |
| `mentions_brave_stub` | mentions provider plumbing | n/a | M3 stub |

Out of v0.1 scope: LinkedIn / Crunchbase, IG/FB/TikTok follower counts,
Apify actors beyond stubs, web UI.

## Layout

```
research_pack/         # package
  cli.py               # Typer app
  schema.py            # pydantic v2 models — the JSON contract
  config.py            # pydantic-settings + TOML, XDG-compliant paths
  cache.py             # SQLite fetch cache (opt-in)
  http.py              # requests-cache + tenacity foundation
  robots.py            # robots.txt enforcement
  providers/
    __init__.py        # plugin loader (importlib.metadata.entry_points)
    base.py            # ProviderBase, ProviderError, ProviderRunMetadata
docs/
  SPEC.md              # snapshot — canonical in noontide-projects
  VALIDATION.md        # snapshot — canonical in noontide-projects
  REFERENCES.md        # OSS deps + inspiration repos
fixtures/              # per-domain raw HTML + API responses + expected.json
tests/                 # pytest, hypothesis where useful
```

## Validation

Two phases (full text in [`docs/VALIDATION.md`](docs/VALIDATION.md)):

- **Phase A — blind-eval.** 10 prospects, side-by-side against an Opus-reads-HTML brief. Pass: ≥8/10 same-or-better, no unanimously-worse prospects.
- **Phase B — 2-week live A/B on booked calls.** ±10% reply-rate threshold.

`research-pack` v0.1 produces the inputs Phase A consumes. Phase B is a
collaboration with the downstream pipeline owner.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Conventional commits, one PR per
milestone, ruff + mypy strict + pytest ≥70% cov.

## License

[MIT](LICENSE).
