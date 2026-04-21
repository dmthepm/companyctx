# Zero-Key Mode

`companyctx <domain>` returning a schema-locked JSON payload with **no API
keys, no configuration, no rented infrastructure** is the first thing the
README shows. It's the adoption wedge.

This doc is the honest scoping. Zero-key mode does not magically defeat the
internet's anti-bot layer — and pretending otherwise would poison first-run
trust faster than an install bug.

## What zero-key covers

**The stealth fetcher.** A TLS + HTTP/2 fingerprint impersonation HTTP client
(browser-identity class — the specific library lands in
[`decisions/2026-04-20-zero-key-stealth-strategy.md`](../decisions/2026-04-20-zero-key-stealth-strategy.md)
after the M1 spike). It clears the passive TLS/HTTP-signature check most
basic anti-bot layers start with.

Backing that, the day-one zero-key providers:

| Provider slug             | What it extracts                       |
|---------------------------|----------------------------------------|
| `site_text_trafilatura`   | Cleaned body text (primary extractor)  |
| `site_text_readability`   | Cleaned body text (bus-factor fallback)|
| `site_meta_extruct`       | JSON-LD / OG / Twitter cards / `sameAs`|
| `social_discovery_site`   | Platform handles via HTML + `sameAs`   |
| `signals_site_heuristic`  | Copyright year, last blog post date, team-size claim, tech-stack fingerprint |

No key required for any of these. They are the `pipx install companyctx &&
companyctx acme-bakery.com` experience.

## The honest coverage matrix

| Site class | Zero-key expected outcome |
|---|---|
| **Small-biz WordPress / Squarespace / Wix / Webflow / small-agency custom** | Full payload on the homepage. This is the sweet spot — the TLS-impersonation fetcher clears the passive checks, and most small-biz stacks don't run aggressive anti-bot. Expected `status: "ok"` on ~85–95% of prospects in this segment.* |
| **Sites behind Cloudflare Turnstile, DataDome, Akamai, or PerimeterX** | Often blocked on zero-key. Returns `status: "partial"` with `error: "blocked_by_antibot"` and `suggestion: "configure a smart-proxy provider key or skip this prospect"`. The payload will contain whatever *did* succeed (e.g. `extruct` on a cached preview) — not a crash. |
| **JS-heavy SPAs that need a real browser** | Zero-key fetcher returns the HTML shell only. The schema fields that need rendered content (often `site.about_text`, some JSON-LD) come back null. `status: "partial"`; configure a smart-proxy + headless-browser provider to fill the gap. |
| **Aggregator pages (Yelp / Houzz / G2 / Birdeye)** | Zero-key will not get these — ToS + anti-bot posture make them a bad target. The right path is the `reviews_google_places` / `reviews_yelp_fusion` **direct-API** providers (user-keyed) under Attempt 3 of the Deterministic Waterfall. README must not imply otherwise. |

\* The 85–95% number will be measured against the 30-prospect fixtures
corpus during the M1 stealth-fetcher spike, not estimated. If measurement
comes in lower, this doc updates and the README headline numbers update with
it. Honesty before hype.

## The graceful-partial contract

When zero-key can't fully succeed, `companyctx` does not crash, does not
`sys.exit(1)`, does not raise. It emits the partial envelope:

```json
{
  "status": "partial",
  "data": {
    "domain": "example.com",
    "fetched_at": "2026-04-20T18:42:11Z",
    "site": null,
    "reviews": null,
    "social": { "handles": {"instagram": "@example"}, "follower_counts": {} },
    "signals": null
  },
  "provenance": {
    "site_text_trafilatura": {
      "status": "failed",
      "latency_ms": 2100,
      "error": "blocked_by_antibot (HTTP 403)",
      "provider_version": "0.1.0"
    },
    "site_meta_extruct": {
      "status": "ok",
      "latency_ms": 180,
      "error": null,
      "provider_version": "0.1.0"
    }
  },
  "error": "blocked_by_antibot",
  "suggestion": "configure a smart-proxy provider key or skip this prospect"
}
```

Downstream pipelines branch on `status`:

```python
ctx = fetch_companyctx(domain)
if ctx["status"] == "ok":
    synthesize(ctx["data"])
elif ctx["status"] == "partial":
    log.warning("partial: %s — %s", ctx["error"], ctx["suggestion"])
    synthesize_with_caveat(ctx["data"])   # pipeline-safe, not a skip
else:  # degraded (stale cache used)
    synthesize(ctx["data"])               # or --refresh and retry
```

No try/except around a crash. No `None` return values bubbling through
nothing. The envelope is always well-formed.

## What to do when zero-key isn't enough

**Option A — configure a smart-proxy provider.** `companyctx` ships a
`SmartProxyProvider` interface, vendor-agnostic. You supply your own
residential-proxy / headless-browser credentials (Bright Data, Oxylabs,
ScrapingBee, ZenRows, Apify — whichever you already have). We route the
anti-bot-blocked fetches through it. We do not ship a specific vendor; we
ship the contract.

**Option B — configure direct-API providers.** For review counts / ratings /
social follower counts, the right path is the platform's own API, not
scraping. Google Places (`GOOGLE_PLACES_API_KEY`), Yelp Fusion
(`YELP_API_KEY`), YouTube Data API (`YOUTUBE_API_KEY`). Each is env-gated;
if the key isn't set, the provider reports
`provenance[slug].status: "not_configured"` and the envelope still comes back
well-formed.

**Option C — skip this prospect.** If zero-key returns partial and you
don't want to pay for smart-proxy access, the envelope's
`suggestion: "skip this prospect"` is a valid pipeline decision. Log it,
move on, don't bend the tool.

## What zero-key is *not*

- **Not a promise of 100% coverage.** See the matrix above.
- **Not a Cloudflare bypass tool.** If the site is serious about blocking
  bots, we report the block and route to user-keyed providers. We don't
  out-engineer Cloudflare.
- **Not a scraper for ToS-protected aggregators.** Yelp / Houzz / G2 don't
  get scraped via zero-key; they get queried via direct-API providers.
- **Not a guarantee of field completeness on small-biz sites either.**
  Some homepages just don't have a team-size claim, a copyright footer,
  or recent blog posts — those stay null without it being a failure.

## M1 spike deliverables

Before any README claims a specific zero-key success rate, the stealth
fetcher gets measured:

- Run the candidate TLS-impersonation library against the 30-prospect
  fixtures corpus.
- Record `status: "ok"` vs `status: "partial"` distribution.
- Publish the measured number in this doc + the README hero block.
- The specific library choice + the evaluation lives in
  [`decisions/2026-04-20-zero-key-stealth-strategy.md`](../decisions/2026-04-20-zero-key-stealth-strategy.md).

If measurement disappoints, the honesty stance is to update the coverage
matrix and rewrite the README hero — not to stretch the number.
