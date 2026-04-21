---
type: decision
date: 2026-04-20
topic: zero-key stealth fetcher strategy + Deterministic Waterfall contract
status: proposed
linked_decisions:
  - decisions/2026-04-20-name-change-to-companyctx.md
linked_docs:
  - docs/ARCHITECTURE.md
  - docs/ZERO-KEY.md
---

# Zero-key stealth strategy + Deterministic Waterfall contract

## Status

**Proposed.** The shape of the contract is decided; the specific
TLS-impersonation library is a candidate pending an M1 spike against the
30-prospect fixtures corpus. This ADR updates to **accepted** when the
library choice is measured, not estimated.

## Context

`companyctx`'s adoption wedge is `pipx install companyctx && companyctx
<site>` returning a schema-locked JSON payload with **no API keys, no
configuration, no rented infrastructure.** See `docs/ZERO-KEY.md` for the
user-facing doc and `docs/ARCHITECTURE.md` for the Deterministic Waterfall
architecture.

The tension: the modern web's anti-bot layer is real. Cloudflare Turnstile,
DataDome, Akamai, PerimeterX actively detect `requests`/`httpx` default
TLS+HTTP fingerprints and block on first contact. Zero-key mode cannot
out-engineer Cloudflare. We need a posture that:

1. Gets us past the passive TLS/HTTP-signature check on the large majority
   of small-biz homepages (the primary ICP).
2. **Fails gracefully** on the aggressively protected minority — never
   crashes, always emits a well-formed envelope with an actionable
   `suggestion`.
3. Routes to user-keyed fallbacks (smart-proxy, direct-API) cleanly when
   zero-key can't cover a site.

## Decision

### 1. Deterministic Waterfall (contract)

Every `companyctx <site>` call attempts providers in a fixed order. Each
attempt, if it succeeds, returns the same `CompanyContext` envelope shape.

```
Attempt 1 — Zero-Key Stealth
  TLS+HTTP/2 fingerprint impersonation fetcher
  → trafilatura / readability-lxml (site text)
  → extruct (JSON-LD / OG / sameAs)
  → BS4 + regex (social handles, tech fingerprint, signals)

Attempt 2 — Smart-Proxy Provider (optional, user-keyed)
  Routed on 403 / challenge HTML / timeout from Attempt 1.
  Vendor-agnostic SmartProxyProvider interface — user supplies their
  residential-proxy / headless-browser credentials.

Attempt 3 — Direct-API Provider (optional, user-keyed)
  Google Places, Yelp Fusion, YouTube Data API. Fills review counts,
  ratings, social follower counts where the homepage can't.
```

Every attempt maps to the same Pydantic schema. Downstream pipelines never
branch on which attempt succeeded — they branch on the envelope's
`status: ok | partial | degraded`.

### 2. Zero-key fetcher — candidate libraries

The stealth fetcher must:

- Impersonate a current browser's TLS ClientHello (JA3/JA4 fingerprint).
- Impersonate a current browser's HTTP/2 SETTINGS frame + header order.
- Support cookies, redirects, custom User-Agent, timeouts, robots.txt
  checks.
- Be actively maintained, permissively licensed (MIT / Apache-2.0 / BSD),
  and not carry a heavy headless-browser dependency in the zero-key path.

Candidates tracked for the M1 spike (in rough order of current fit, pending
measurement):

- **`curl_cffi`** — Python bindings over libcurl-impersonate. Active
  maintenance, broad browser-fingerprint coverage, small dep footprint.
  Current lead candidate.
- **`primp`** — Rust-backed, exposes `impersonate="chrome_131"` etc.
  Newer; fingerprint matrix narrower but very clean API.
- **`tls-client`** — pure-Python, wraps the bogdanfinn Go client via a
  local sidecar. Works but the sidecar adds distribution friction for a
  pipx-installed CLI.
- **`httpx` with manual `httpx.HTTPTransport` + `h2` tweaks** —
  insufficient; the JA3 fingerprint still leaks as `python-requests`
  / `httpx` defaults. Rejected as the primary.

### 3. Graceful-partial contract (strict)

When Attempt 1 fails and no Attempt-2/3 provider is configured, the
framework does **not** raise. It emits:

```json
{
  "status": "partial",
  "data": { "site": "…", "fetched_at": "…", "pages": null, … },
  "provenance": { "<slug>": {"status": "failed", "error": "blocked_by_antibot (HTTP 403)", …} },
  "error": "blocked_by_antibot",
  "suggestion": "configure a smart-proxy provider key or skip this prospect"
}
```

`status != "ok"` is always accompanied by an actionable `suggestion`. No
bare errors, no stack traces bubbling out to the shell, no non-zero exit
on partial (exit-0 on partial is on purpose — the envelope is well-formed
pipeline input).

### 4. README honesty

No README, launch copy, or docs headline commits a zero-key success-rate
number until the M1 spike measures it against the 30-prospect fixtures
corpus. Numbers come from measurement, not from vendor marketing, not from
estimates. See `docs/ZERO-KEY.md` for the coverage matrix.

## Rationale

- **Waterfall shape makes the zero-key path honest.** Users get zero-key
  first-run; when it doesn't cover a site, they get a clear, actionable
  path forward (configure a smart-proxy provider, configure a direct-API
  provider, or skip). The CLI is usable for free and scales up to paid
  infrastructure without rewriting pipelines.
- **Schema-first prevents shape-shifting across layers.** Every attempt
  emits the same `CompanyContext`. The downstream agent never learns that
  Attempt 2 was used — it reads one shape.
- **`SmartProxyProvider` is an interface, not a vendor.** We don't compete
  with Bright Data / Oxylabs / ScrapingBee / Apify — we compose them.
  Residential-proxy infrastructure is a commodity layer; the schema + cache
  + waterfall is the defensible surface.
- **Graceful-partial is non-negotiable.** Anti-bot reality means some
  percentage of fetches will always fail. Crashes in that case would
  destroy trust faster than anything else. The envelope always comes back
  well-formed.

## Alternatives considered

| Option | Why rejected |
|---|---|
| "requests" / "httpx" defaults + retry | TLS+HTTP fingerprint leaks as Python, blocked by modern anti-bot on first request. |
| Headless Chromium (playwright / puppeteer) in the zero-key path | Heavy dependency (~500MB); bad fit for a pipx CLI; even Chromium gets fingerprinted now. Belongs in a smart-proxy provider under Attempt 2. |
| "Just scrape via Apify actors" | Apify is a commodity infrastructure layer; we compose it via `SmartProxyProvider` rather than taking a hard dependency. Users with other preferred vendors shouldn't pay the Apify tax. |
| "Skip zero-key, require keys from day one" | Kills the adoption wedge. `pipx install` + instant value is the whole point of the first-run experience. |
| "Promise 99% coverage" | Overclaim. Cloudflare-fronted sites will block zero-key. Honest scoping beats inflated marketing. |
| "Rewrite the fetcher stack in Go/Rust" | Premature. The library ecosystem already has good impersonation options; building our own is scope creep. |

## Risks

- **Anti-bot layers evolve faster than fingerprint-impersonation
  libraries.** Mitigation: the `SmartProxyProvider` interface is the escape
  hatch. When zero-key decays, users configure a smart-proxy key and the
  envelope shape stays the same. Decay is expected and routed, not
  catastrophic.
- **Measured zero-key coverage comes in below expectation.**
  Mitigation: `docs/ZERO-KEY.md` and the README hero update to the measured
  number. We don't stretch numbers; we update copy.
- **Library choice proves to be unmaintained within 18 months.**
  Mitigation: the stealth-fetcher module is provider-shaped; swapping the
  underlying library is a contained change that doesn't touch the
  contract. Bus-factor belongs in `docs/REFERENCES.md` tracking.
- **Users assume zero-key defeats Cloudflare.** Mitigation: the
  `docs/ZERO-KEY.md` coverage matrix is explicit; the README states the
  limits above the fold.

## Open questions (resolved in M1 spike)

- Which specific TLS-impersonation library wins?
- What's the measured zero-key `status: "ok"` rate on the 30-prospect
  fixtures corpus?
- Does any fixture class need a dedicated provider (e.g. a separate
  `site_text_playwright` behind a smart-proxy), or is the three-layer
  waterfall sufficient?

This ADR updates to **accepted** when those are answered.
