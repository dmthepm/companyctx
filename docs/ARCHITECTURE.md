# Architecture

`companyctx` is a narrow deterministic **muscle** in the brains-and-muscles
pattern. A frontier LLM (Opus / Sonnet / Gemini / DeepSeek) plays orchestrator
brain upstream; `companyctx` is one of many CLIs the brain composes via pipes.

```
  ┌──────────────────┐     companyctx <site>       ┌──────────────────┐
  │  orchestrator    │ ──────────────────────────→ │   companyctx     │
  │  (frontier LLM)  │                             │  (this tool)     │
  │                  │ ←── schema-locked JSON ──── │                  │
  └──────────────────┘                             └──────────────────┘
         │
         ├─→ other muscles (evaluation, synthesis, delivery…)
         └─→ final output
```

## Design commitments

1. **Schema is the product.** The Pydantic v2 envelope (`CompanyContext` +
   `ProviderRunMetadata` + the `{status, data, provenance, error?, suggestion?}`
   wrapper, see `docs/SCHEMA.md`) is the contract. Providers are replaceable.
2. **Never raise at the boundary.** Every failure — anti-bot block, missing
   API key, cache miss, timeout — maps to the `status` enum on the envelope
   and/or `ProviderRunMetadata.status` per provider. Downstream pipelines
   branch on `status`, never on try/except.
3. **Deterministic Waterfall before anything clever.** See below.
4. **Local-first, cache as compound asset.** The SQLite cache is not just a
   speed optimization — every run accumulates into a queryable vertical-memory
   moat (see Vertical Memory below).
5. **Provider isolation.** Providers don't import each other; lint enforces
   this. Each provider owns exactly one deterministic call class.

## The Deterministic Waterfall

Every `companyctx <site>` call attempts providers in a fixed, layered order.
Each layer, if configured, returns the *same* `CompanyContext` shape — a
downstream agent never branches on which layer succeeded.

```
  ┌───────────────────────────────────────────────────────────────────────┐
  │                   Attempt 1 — Zero-Key Stealth                        │
  │                                                                       │
  │   TLS+HTTP/2 fingerprint impersonation fetcher                        │
  │   → trafilatura / readability-lxml (site text, bus-factor fallback)   │
  │   → extruct (JSON-LD / OpenGraph / sameAs)                            │
  │   → BeautifulSoup + regex (social handles, tech fingerprint)          │
  │                                                                       │
  │   Covers ~85–95% of small-biz homepages. No keys, no cost.            │
  └───────────────────────────┬───────────────────────────────────────────┘
                              │  403 / challenge / timeout?
                              ▼
  ┌───────────────────────────────────────────────────────────────────────┐
  │           Attempt 2 — Smart-Proxy Provider (optional, user-keyed)     │
  │                                                                       │
  │   SmartProxyProvider interface — vendor-agnostic. User supplies       │
  │   their own residential-proxy / headless-browser credentials.         │
  │   We don't ship a specific vendor; we ship the contract.              │
  └───────────────────────────┬───────────────────────────────────────────┘
                              │  still blocked / not applicable?
                              ▼
  ┌───────────────────────────────────────────────────────────────────────┐
  │         Attempt 3 — Direct-API Provider (optional, user-keyed)        │
  │                                                                       │
  │   Google Places / Yelp Fusion / YouTube Data API. ToS-safe.           │
  │   Fills review counts, ratings, social follower counts where the      │
  │   homepage can't.                                                     │
  └───────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────────┐
              │   Envelope emission               │
              │   {status, data, provenance, …}   │
              └───────────────────────────────────┘
```

Failure mode is a **structured partial**, never a crash — see `docs/SPEC.md`
for the envelope shape and `docs/ZERO-KEY.md` for the honest anti-bot
coverage matrix.

## Vertical Memory

The SQLite cache is a byproduct that compounds into a local data asset.

- **What's written.** The full normalized `CompanyContext` payload plus
  `ProviderRunMetadata` per provider — not raw HTML snippets.
- **Where it lives.** `~/.cache/companyctx/` (XDG-respecting via
  `platformdirs`).
- **Keyed on.** `(normalized_host, provider_set_hash, provider_slug)` plus
  TTL.
- **Schema is versioned.** Migrations are first-class; the cache survives
  provider upgrades.

Over time a user accumulates a queryable local B2B dataset as a side effect
of normal use — the differentiator against hosted actors (Apify / Clearbit /
Firecrawl) where the JSON evaporates per call.

v0.1 ships persistence + `--refresh` / `--from-cache` flags. A
`companyctx query "SELECT …"` DSL is v0.2 scope and intentionally not
committed here.

## Brains-and-muscles example

```bash
# Brain upstream composes narrow muscles:
companyctx acme-bakery.com --json \
  | jq '.data | {site, signals, reviews}' \
  | claude -p "write a 6-section outreach brief from this context"
```

Or from Python:

```python
import json, subprocess
ctx = json.loads(subprocess.check_output(["companyctx", "acme-bakery.com", "--json"]))
if ctx["status"] == "partial":
    print(f"heads up: {ctx['error']} — {ctx['suggestion']}")
brief = synthesize(ctx["data"])  # your synthesis call, your prompts
```

`companyctx` never synthesizes, never prompts, never calls an LLM. The brain
upstream decides what the context means.

## Non-goals

- Not a scraper competing on scale. Residential-proxy infrastructure is a
  commodity layer we compose via a `SmartProxyProvider` interface.
- Not an agent framework. Orchestration lives upstream.
- Not a hosted service. Local pipx CLI.
- Not a synthesis engine. Our output is the input *for* synthesis.
- Not a multi-page crawler. One site in, one structured object out.

## Agent discovery

Agents find `companyctx` via [`SKILL.md`](../SKILL.md) at the repo root — a
~150-token surface listing purpose, commands, rules, and one bash
example. MCP is explicitly off the roadmap; see
[`decisions/2026-04-20-skill-md-not-mcp.md`](../decisions/2026-04-20-skill-md-not-mcp.md)
for the reasoning (token economics, Unix fluency, intelligence
boundary).

## Further reading

- `docs/SCHEMA.md` — the Pydantic envelope in detail.
- `docs/ZERO-KEY.md` — honest anti-bot coverage + graceful-partial contract.
- `docs/PROVIDERS.md` — the day-one provider list with cost hints.
- `docs/SPEC.md` — the full frozen v0.1 spec snapshot.
- `decisions/` — in-repo ADRs for the load-bearing choices.
