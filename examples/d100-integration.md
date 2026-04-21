# D100 integration — dropping `companyctx` into a D100-class cold-outreach pipeline

This recipe shows the exact diff needed to replace the "LLM reads raw
HTML" step in a D100-class cold-outreach pipeline with the
deterministic `companyctx` envelope.

It is the canonical reference for the brains-and-muscles pattern that
motivates this repo's existence: the frontier model stays as the
**brain** (synthesis, brief-writing, sequence generation), and
`companyctx` becomes the **muscle** that feeds it structured context.

## What changes in the D100 pipeline

**Before.** The agent crawls a prospect's homepage, dumps raw HTML
(or a rough trafilatura pass) into the frontier model, and asks it
to extract services, tech stack, review posture, and size — all in
one call. The problems:

- Non-deterministic output. The same page, same prompt, same model
  produces different JSON keys on different days.
- Token burn. The model reads tens of kilobytes of HTML boilerplate
  to find a handful of fields.
- Error modes hidden in prose. When the fetch gets blocked, the
  model hallucinates plausible-sounding fields instead of surfacing
  a clean "blocked" signal.
- No cache. Every re-run pays the token bill again.

**After.** The pipeline runs `companyctx fetch <domain> --json` as a
preceding step. The envelope is schema-locked, provenance-typed,
status-aware, and cached locally. The frontier model only sees
pre-extracted structured context and focuses on synthesis — where
it's actually good.

## The diff

In the pipeline script that performs phase-1 prospect research,
replace the homepage-read + LLM-extract step with:

```python
# ---- before (one-shot HTML + LLM extract) ----
html = fetch_html(domain)                           # brittle
raw = call_llm(f"Extract services, tech_stack, reviews from: {html}")
context = try_parse_json(raw)                        # non-deterministic

# ---- after (deterministic muscle feeding the brain) ----
import subprocess, json
result = subprocess.run(
    ["companyctx", "fetch", domain, "--json"],
    capture_output=True, text=True, check=False,
)
envelope = json.loads(result.stdout)

if envelope["status"] == "ok":
    context = envelope["data"]
elif envelope["status"] == "partial":
    context = envelope["data"]                       # still safe — schema-locked partial
    log(f"{domain}: {envelope['error']} → {envelope['suggestion']}")
else:
    context = None
    log(f"{domain}: degraded — skipping")
```

The synthesis step downstream (brief generation, email drafting,
sequence step composition) stays unchanged — it already consumed
`context` as structured input. It now gets a better, cheaper,
deterministic version of the same thing.

## Why you can trust the drop-in

- **The envelope is versioned.** `data.pages`, `data.reviews`,
  `data.social`, `data.signals`, `data.mentions` do not drift — the
  schema ships with `extra="forbid"` and schema-version bumps are
  explicit. Your pipeline code doesn't need defensive parsing.
- **`status` is the only branch you ever need.** `ok` → use all of
  `data`. `partial` → use what's populated, honor the `suggestion`.
  `degraded` → log and skip. No try/except around the fetch itself.
- **Provenance tells you which provider did what.** If a later run
  shows `reviews` went from populated to null, `provenance.reviews_*`
  tells you whether the direct-API provider lost its key, hit a
  quota, or wasn't configured.
- **Cache is built in.** The second run against the same domain
  (within the TTL window) hits SQLite and skips the network
  entirely. No rate-limit worries in a 100-domain batch.

## The zero-key default

The default fetch path is zero-key — no API credentials required for
the homepage-derived fields (`data.pages.*`) or the heuristic signals
(`data.signals.copyright_year`, `.last_blog_post_at`, etc.). The
D100 pipeline can run the muscle against an entire batch without any
credentials setup.

For `data.reviews`, `data.social.follower_counts`, and the media
mentions fields, configure the direct-API providers your ICP needs
(Google Places for local-biz reviews, YouTube Data API for social
counts, Brave Search API for press mentions). See
[`../docs/PROVIDERS.md`](../docs/PROVIDERS.md).

## Graceful-partial — handling antibot blocks

For prospects behind Cloudflare Turnstile / DataDome / Akamai, the
zero-key path may return `status: "partial"` with
`error: "blocked_by_antibot"`. The pipeline should not treat this as
a fatal error:

```python
if envelope["status"] == "partial" and envelope.get("error") == "blocked_by_antibot":
    # We still have provenance, we still have whatever did work
    # (e.g., direct-API reviews if a key was configured). Continue.
    context = envelope["data"]
    reason = envelope["suggestion"]   # e.g. "configure a smart-proxy provider key"
    route_to_queue(domain, reason=reason)
```

This is the whole point of the envelope — your pipeline branches on
`status` once, not on try/except around every provider call.

## Batch pattern

For a 100-domain D100 batch:

```bash
# Fan out the muscle. --refresh bypasses the cache for a fresh run;
# drop it on subsequent passes to reuse cached payloads.
while IFS= read -r domain; do
  companyctx fetch "$domain" --json --refresh > "out/${domain}.json"
done < d100-batch.csv

# Then in your Python pipeline, iterate the envelopes.
```

Or, when it lands, `companyctx batch d100-batch.csv --out-dir out/`.

## Related recipes in this gallery

- [`03-brains-and-muscles.sh`](03-brains-and-muscles.sh) — the
  minimal form of the pattern (`companyctx | llm`).
- [`04-sales-meeting-prep.sh`](04-sales-meeting-prep.sh) — what a
  human rep does with the same envelope right before a call.
- [`05-pe-rollup-screener.sh`](05-pe-rollup-screener.sh) — filter
  logic over a batch, same envelope shape.

## Full pipeline diagram

```
┌──────────────┐   domain    ┌──────────────────────┐   envelope   ┌──────────────┐
│  D100 list   │ ──────────▶ │    companyctx        │ ───────────▶ │  frontier    │
│  (CSV)       │             │    (the muscle)      │              │  LLM         │
└──────────────┘             │                      │              │  (the brain) │
                             │  zero-key path       │              │              │
                             │  ↓ block?            │              │  synthesis:  │
                             │  smart-proxy path    │              │  - brief     │
                             │  ↓ still blocked?    │              │  - email     │
                             │  direct-API path     │              │  - sequence  │
                             └──────────────────────┘              └──────────────┘
                                    │                                    │
                                    ▼                                    ▼
                             SQLite cache                         Instantly / Smartlead
                             (Vertical Memory)
```

The envelope is the contract between the muscle and the brain. Swap
either side independently — the contract doesn't change.
