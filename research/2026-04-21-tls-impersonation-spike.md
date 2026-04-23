---
type: research
date: 2026-04-21
topic: TLS-impersonation library spike for the zero-key stealth fetcher
category: zero-key-feasibility
status: complete
supersedes_placeholder_in:
  - decisions/2026-04-20-zero-key-stealth-strategy.md
  - docs/ZERO-KEY.md
linked_issues:
  - https://github.com/dmthepm/companyctx/issues/21
raw_evidence: research/2026-04-21-tls-impersonation-spike-raw.jsonl
---

# TLS-impersonation library spike

## One-sentence summary

At each library's **latest** bundled Chrome fingerprint, `curl_cffi`, `primp`,
and `rnet` all returned HTTP 200 on 20 of 20 D100-class SMB homepages; at a
~6-month-stale Chrome 131 fingerprint three Cloudflare-fronted sites blocked
`curl_cffi` and `rnet` identically (same 75,193-byte challenge body), so the
operational bottleneck is **fingerprint freshness**, not library identity —
making license, API fit, and maturity the load-bearing selection axes, and
`curl_cffi` the winner (`rnet` is GPL-3.0 which contaminates our MIT
distribution).

## Scope

Resolves the open questions parked in `decisions/2026-04-20-zero-key-stealth-strategy.md`:

1. Which specific TLS-impersonation library wins the zero-key fetcher slot?
2. What's the measured zero-key success rate on a real D100-class probe set?

## Candidate libraries

The ADR listed four candidates; we tested three.

| Library    | Tested | Reason |
|------------|--------|--------|
| `curl_cffi` | yes    | ADR lead candidate. libcurl-impersonate Python bindings, MIT. |
| `primp`     | yes    | Rust-backed, MIT, growing fingerprint matrix. |
| `rnet`      | yes    | Substituted for `tls-client` per the ADR's own "distribution friction" flag against the `tls-client` Go-sidecar requirement. `rnet` is a single pip wheel, stays libcurl-impersonate-family. |
| `tls-client`| no     | Eliminated pre-measurement: the ADR already documents that its Go-sidecar requirement adds distribution friction unacceptable for a pipx-installed CLI. No measurement needed to confirm a known packaging disqualifier. |

Rejected at the ADR layer (not tested): stdlib `requests` / `httpx`
defaults — the very Python fingerprint this spike exists to replace.

## Probe-set design

**20 slugs, 8 D100-adjacent B2B niches.** Niche distribution (2–3 slugs each):
cosmetic dentistry, plastic surgery, bariatric surgery, IVF/fertility,
orthodontics, business immigration, high-net-worth divorce, private lending.
Seed domains sampled deterministically (alphabetical first-N) from
the external partner's D100 instantly-sequence CSVs at
`<partner-outputs-dir>/2026-04-08-d100-*-instantly.csv`.

**Sanitization.** The committed probe set references sites by slug only
(`bariatric-01`, `cos-dent-02`, …). The slug → real-URL mapping lives in a
local-only file, `research/.slug-map.local.csv` (gitignored under
`research/*.local.*`). Raw measurement records (JSONL, 120 rows) likewise
carry slugs, not URLs. The external partner's seed list is private; the research artifact
must not leak it.

**Site-class coverage.** The probe was not pre-classified by WAF; classes
surfaced empirically from behavior (see "Hostile cluster" below). The
chrome131 run revealed three Cloudflare-fronted sites (hostile cluster) and
17 un-fronted small-business sites — satisfying the issue's "2+
known-hostile" requirement without pre-staging the mix.

**Tech-stack composition (empirical, from the committed raw JSONL).** Per
the cheap HTML-surface heuristic in the harness (`classify_tech`), the 20
latest-native curl_cffi rows break down as:

| Marker             | Slugs |
|--------------------|-------|
| WordPress          | 16    |
| &nbsp;&nbsp;…of which Elementor | 7 |
| Shopify            | 1     |
| Squarespace        | 1     |
| no-detectable-CMS  | 3     |
| Wix / Webflow / SPA-root | 0 |

This is the honest scoping against issue #21's scope item 2, which asked
for a mix including WordPress, Squarespace/Wix, and SPAs. The D100 seed
lists we sampled from are dominated by WordPress/Elementor small-biz
sites; alphabetical deterministic sampling from those CSVs did not
surface Wix, Webflow, or React/Vue SPA homepages in this 20-site draw.
**The 20/20 result is therefore evidence for the WordPress-heavy
small-biz segment the D100 lists actually contain, not for the full
site-class matrix the issue scope anticipated.** Closing that gap is
tracked as follow-up work in "Out-of-scope" below.

## Measurement method

Each (slug, library) cell records one GET to `https://<domain>/` with:

- Browser impersonation set to the library-native Chrome variant (two
  passes — see runs below).
- `robots.txt` enforced via Python's `urllib.robotparser`. `robots_unfetchable`
  conservatively allows (matches urllib defaults) and is noted per row.
- 15s timeout, redirects followed (all libraries), 2s pacing floor between
  requests.
- No custom `User-Agent` header: supplying one defeats the library's
  impersonation surface.

Outputs per row: HTTP status, total elapsed ms, response bytes, trafilatura
extract length, library version, impersonation string, `outcome` enum
(`ok` | `blocked_403` | `redirect_NNN` | `network_error` | `skipped_*`),
run label.

Harness source: `research/_scratch/probe.py` (gitignored scratch).
Python 3.13.7 on macOS arm64; library versions:
`curl_cffi 0.15.0`, `primp 1.2.3`, `rnet 2.4.2`, `trafilatura 2.0.0`.

Two runs, same 20 slugs:

- **Run A — latest-native** (each library at its latest bundled Chrome):
  `curl_cffi@chrome146`, `primp@chrome_146`, `rnet@Chrome137`.
- **Run B — stale-chrome131** (forcing all three to the same ~6-month-old
  Chrome 131 fingerprint): `curl_cffi@chrome131`, `primp@chrome_131`,
  `rnet@Chrome131`. `primp` logged "Impersonate 'chrome_131' does not
  exist, using 'random'" — `primp` silently falls back to a random pool
  when it lacks a bundled fingerprint for the requested version; recorded
  as-is.

## Results

### Aggregate

| Run              | Library   | 200 ok | blocked | redirect | error | p50 ms | p95 ms |
|------------------|-----------|--------|---------|----------|-------|--------|--------|
| latest-native    | curl_cffi | 20/20  | 0       | 0        | 0     | 459    | 2153   |
| latest-native    | primp     | 20/20  | 0       | 0        | 0     | 361    | 1843   |
| latest-native    | rnet      | 20/20  | 0       | 0        | 0     | 428    | 1786   |
| stale-chrome131  | curl_cffi | 17/20  | 3       | 0        | 0     | 524    | 2112   |
| stale-chrome131  | primp (†) | 20/20  | 0       | 0        | 0     | 338    | 1534   |
| stale-chrome131  | rnet      | 17/20  | 3       | 0        | 0     | 533    | 1772   |

† `primp` did not have a `chrome_131` fingerprint bundled and fell back to
its random pool. The 20/20 result is therefore **`primp` random**, not
`primp@chrome_131`.

### Hostile cluster (chrome131 blocks)

All three blocks shared an identical `bytes=75193, status=403` response —
the Cloudflare "Just a moment…" challenge HTML. `curl_cffi@chrome131` and
`rnet@Chrome131` were blocked on the same three slugs, suggesting the JA3
signature they emit for Chrome 131 is indexed in Cloudflare's bot
classifier. Moving to the libraries' latest Chrome fingerprints (146 /
146 / 137) eliminated the block.

| Slug            | Status (chrome131) | Status (latest-native) |
|-----------------|--------------------|------------------------|
| bariatric-03    | 403 (cf-challenge) | 200                    |
| cos-dent-02     | 403 (cf-challenge) | 200                    |
| hnw-divorce-01  | 403 (cf-challenge) | 200                    |

### Install weight

Measured against the same `research/_scratch/venv` install.

| Library    | PyPI wheel (macOS arm64) | Installed on-disk | Extra Python deps |
|------------|--------------------------|-------------------|-------------------|
| curl_cffi  | ~3.1 MB                  | 6.4 MB            | cffi, certifi, rich |
| primp      | 4.0 MB                   | 7.8 MB            | none              |
| rnet       | 3.4 MB                   | 6.9 MB            | none              |

### Wheel coverage (cpython support)

| Library    | 3.10 | 3.11 | 3.12 | 3.13 | Wheel scheme |
|------------|------|------|------|------|--------------|
| curl_cffi  | ✓    | ✓    | ✓    | ✓    | abi3 (one wheel per OS/arch covers all) |
| primp      | ✓    | ✓    | ✓    | ✓    | abi3 (one wheel per OS/arch covers all) |
| rnet       | ✓    | ✓    | ✓    | ✓    | per-cpython-version wheel |

### License

| Library    | License    | Compatible with MIT-distributed CLI? |
|------------|-----------|--------------------------------------|
| curl_cffi  | MIT       | yes                                  |
| primp      | MIT       | yes                                  |
| **rnet**   | **GPL-3.0** | **no — strong-copyleft contamination risk** |

`rnet`'s GPL-3.0 license disqualifies it as a default dep in a permissively-
licensed (MIT) CLI published to PyPI. Adding it would force a GPL linking
argument on every downstream user of `companyctx`; the MIT posture on
`pyproject.toml` is deliberate, not incidental.

## Decision

**`curl_cffi` is the accepted zero-key stealth fetcher.**

### Decision matrix

| Axis                                  | curl_cffi | primp | rnet |
|---------------------------------------|-----------|-------|------|
| 20/20 ok at latest fingerprint        | ✓         | ✓     | ✓    |
| MIT-compatible license                | ✓         | ✓     | **✗ (GPL-3.0)** |
| Cross-platform wheels 3.10–3.12       | ✓         | ✓     | ✓    |
| Zero Python deps                       | (3 deps)  | ✓     | ✓    |
| Drop-in `requests`-shaped API         | ✓ (`from curl_cffi import requests as r; r.get(url, impersonate="chromeN")`) | ✗ (custom `Client`) | ✗ (custom `BlockingClient`) |
| Explicit fingerprint control (no silent random fallback) | ✓ | ✗ (silent random fallback on unknown versions) | ✓ |
| Project maturity (PyPI release count) | 38        | 30    | 1    |
| ADR lead candidate                    | ✓         | —     | —    |

### Rationale

1. **License forces the choice.** `rnet` is GPL-3.0; the companyctx CLI
   is MIT. Adopting `rnet` as a default dep contaminates the downstream
   license story. Eliminated on this axis alone — no operational advantage
   would overturn it.
2. **`curl_cffi` wins the remaining two-way on API-match.** PR #19's
   placeholder `_stealth_fetch` uses stdlib `requests.get(url, headers=…,
   timeout=…)`. `curl_cffi.requests.get(url, impersonate=…, timeout=…)`
   is a near drop-in with one new kwarg. `primp` would require
   restructuring to the client-object pattern — a larger diff for no
   block-resistance gain on the probe set.
3. **Maturity.** `curl_cffi` has a 3-year release history and broad
   adoption across scraping ecosystems. `primp` is younger (first PyPI
   release 2024). `rnet` has one PyPI release (2.4.2) and is effectively
   untested at third-party scale.
4. **Explicit fingerprint.** `curl_cffi` errors on unknown impersonation
   strings; `primp` silently falls back to a random pool with a
   process-scoped warning that's easy to miss. Determinism is a contract
   (`--mock` runs are byte-identical modulo `fetched_at`), and silent
   fingerprint variation erodes that.

### Risks + mitigations

- **Fingerprint staleness is the real failure mode.** The chrome131 run
  proved a ~6-month-old fingerprint gets indexed. The provider pins to
  the newest `chromeNNN` each `curl_cffi` release exposes; minor bumps
  track library releases, not product releases.
  *Mitigation:* pin in the provider as a constant, not a config knob,
  and bump alongside `curl_cffi` upgrades.
- **`curl_cffi` brings `rich` as a transitive dep.** Unneeded UI baggage
  for a headless CLI. ~1.2 MB wheel.
  *Mitigation:* acceptable for v0.1; if footprint tightens, file an issue
  upstream to make `rich` optional.
- **Single-library concentration.** If `curl_cffi` upstream stalls, the
  zero-key floor collapses.
  *Mitigation:* `_stealth_fetch` is a single function in one provider
  module. Swap cost is ~50 lines. `primp` remains the documented reserve
  candidate (MIT, 20/20 at latest fingerprint in this spike).
- **20 sites is a small N.** True. The 100-site durability report (issue
  #22) widens the measurement. Its findings may refine but are unlikely
  to overturn the license + API-match rationale that anchors this
  decision.

## Downstream changes

This decision drives, in the same PR:

1. ADR `decisions/2026-04-20-zero-key-stealth-strategy.md` promoted from
   `status: proposed` to `status: accepted`, citing this research.
2. `pyproject.toml` adds `curl_cffi>=0.15` to the default dependency set.
3. `companyctx/providers/site_text_trafilatura.py` swaps its
   `_stealth_fetch` stdlib-`requests` placeholder for `curl_cffi.requests`
   pinned to `impersonate="chrome146"`. One-function replacement; provider
   API surface unchanged.
4. `docs/ZERO-KEY.md` coverage matrix replaces the placeholder 85–95%
   estimate with the measured 20/20 at-latest-fingerprint number and cites
   this research doc. Stale-fingerprint footnote documents the real decay
   mode.
5. README hero coverage copy updated with the measured number.
6. One existing test (`test_ignore_robots_bypasses_robots_check`) is
   updated to patch the new `curl_cffi.requests.get` symbol.

## Reproducibility

- Raw evidence: `research/2026-04-21-tls-impersonation-spike-raw.jsonl`
  (120 rows: 20 slugs × 3 libraries × 2 runs). Slug-only, no real URLs.
- Slug mapping: `research/.slug-map.local.csv` (gitignored; recoverable
  from `<partner-outputs-dir>/2026-04-08-d100-*-instantly.csv` via
  the deterministic sampling procedure documented above).
- Harness: `research/_scratch/probe.py` (gitignored; regenerable — the
  procedure is fully documented in this file).
- Run date: 2026-04-21 (see `run_date` on each JSONL row).

Re-running the spike requires only the D100 CSVs (private to the external partner) and
the probe harness; no companyctx-specific infrastructure.

## Out of scope (deferred to other issues)

- **Site-class mix evidence for Wix / Webflow / SPA homepages.** The D100
  seed lists we sampled from are WordPress-dominated; the 20-slug draw
  contained 16 WordPress, 1 Shopify, 1 Squarespace, 3 no-detectable-CMS,
  and 0 Wix / 0 Webflow / 0 SPA-root. The library-selection rationale
  (license + API-match + silent-fallback avoidance) is independent of
  site class, so the chosen library does not change. But the **measured
  "20/20" number does not yet evidence zero-key coverage on Wix,
  Webflow, or JS-heavy SPA homepages**. Closing that evidence gap is a
  targeted follow-up: deliberately seed ~5 Wix / Webflow / SPA slugs
  (e.g. from a Wix-showcase directory, Webflow's own
  `made-in-webflow` gallery, and a handful of React-SSR SPA
  small-business sites) and re-run the probe, folding the result into
  the 100-site durability report below.
- 100-site durability report (#22) — widens the N; this spike does the
  library-selection job at a sampling depth matching the acceptance
  checklist of #21.
- SmartProxyProvider implementation (#6) — the Attempt-2 fallback the
  ADR routes to when zero-key fails.
- Direct-API providers (#7 and sibling issues) — Attempt-3.
- Golden corpus expansion with `expected.json` shape contracts (#24).

## Open questions (for later)

1. Does `curl_cffi`'s `chromeNNN` pin need to be a config knob (TOML /
   env), or does a build-time constant suffice? Current answer: constant,
   revisit if the 100-site durability report shows version sensitivity.
2. Should the provider swap itself be versioned in provenance? Probably
   yes once multiple stealth-fetcher backends coexist; not needed while
   `curl_cffi` is the sole default.
3. How often does `curl_cffi` ship a new Chrome fingerprint? Empirically
   ~every 1–2 months; formalize a renovate-style upgrade cadence when the
   tool matures past v0.1.
