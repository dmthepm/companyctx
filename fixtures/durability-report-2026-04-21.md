# Durability report — 100-site D100 run

**Run date:** 2026-04-21.
**Related issue:** [#22](https://github.com/dmthepm/companyctx/issues/22) /
Linear COX-13.
**Release-readiness ADR:**
[`decisions/2026-04-21-v0.1.0-release-readiness.md`](../decisions/2026-04-21-v0.1.0-release-readiness.md).
**Headline:** **95 / 100** sites returned `status: ok` with non-empty
`homepage_text` — well above the 60% `v0.1.0` release-gate threshold.

## Methodology

- **Seed source.** Joel's D100 prospect lists at
  `new-signal-studio/research/*-prospect-list.md` — 12 niche files with
  explicit `**Website:**` fields, 260 unique prospect URLs. Two niches (hair
  transplant, full-arch dental) contain 20+ prospects; all others contain
  20–31.
- **Sampling.** Stratified stride sample — 10 hosts per niche across 10
  niches = 100. Stride sampling picks evenly-spaced positions within each
  niche's eligible list, avoiding the alphabetical-first-N the TLS spike
  drew. Sample is deterministic for a given seed list.
- **TLS-spike overlap.** The TLS spike
  ([`research/2026-04-21-tls-impersonation-spike.md`](../research/2026-04-21-tls-impersonation-spike.md))
  drew from the `d100-*-instantly.csv` series (a different surface) with a
  local-only slug-to-URL map (`research/.slug-map.local.csv`) that was not
  present on this machine. Heuristic exclusion: dropped the alphabetical-
  first-2-or-3 per niche (matching the spike's first-N rule) before
  stride-sampling. Exact-URL exclusion is not provable without the slug-map.
- **Fetch.** `scripts/run-durability-batch.py` shells out to
  `python -m companyctx.cli fetch <host> --json` per row, captures the full
  envelope + wall-clock latency + `len(pages.homepage_text.encode("utf-8"))`.
  `robots.txt` honored throughout (no `--ignore-robots`). 2-second pacing
  floor; 45-second subprocess timeout; provider network timeout defaults to
  10s (per `companyctx.core.DEFAULT_TIMEOUT_S`).
- **Classification.** Each envelope mapped to one of the FM codes in
  [`docs/RISK-REGISTER.md`](../docs/RISK-REGISTER.md), extended with two
  observed-but-register-absent codes:
  - `RB-blocked` — `robots.txt` disallow.
  - `HTTP-4xx` / `HTTP-5xx` — non-403/401 HTTP errors.
  (Neither fired in this run.)
- **Privacy.** Per-site hosts and envelopes live only in
  `.context/durability/` (gitignored). This report aggregates by FM-code
  and by niche; no individual hosts are named.
- **Vertical skew — ACKNOWLEDGED UP FRONT.** The sample is **100% medical /
  aesthetic SMBs**. The RISK-REGISTER taxonomy was mined from gutter /
  roofing / IV-therapy transcripts (small-biz home services). FM codes are
  site-shape-driven (WordPress / SPA / Cloudflare-fronted / JS-rendered),
  not niche-driven — so the taxonomy transfers. But **frequencies below
  describe medical/aesthetic SMBs only**. Gutter / roofing / IV /
  waste-management verticals may weight modes differently.

## Sample shape

Exactly 10 hosts per niche, across 10 niches:

- bariatric-surgery, business-immigration, cosmetic-dentistry,
  full-arch-dental, hair-transplant, hnw-divorce, ivf-fertility,
  orthodontics, plastic-surgery, private-lending.

Pilot (25) and follow-on batch (75) combined into the full 100-site
aggregate after deterministic stride-sampling.

## Aggregate rates

| Envelope outcome | Count | Rate |
|---|---:|---:|
| `status: ok` with non-empty `homepage_text` | 95 | **95%** |
| `status: ok` with empty-or-near-empty `homepage_text` (FM-6) | 2 | 2% |
| `status: partial` | 0 | 0% |
| `status: degraded` | 3 | 3% |

Success rate well above the 60% release-gate threshold.

`partial` cannot fire today because the M2 orchestrator ships with a single
provider (`site_text_trafilatura`); with no second provider to degrade
against, an envelope is either `ok` or `degraded`. The `partial` rate becomes
meaningful once Attempt-2 (smart-proxy) or Attempt-3 (direct-API) providers
land.

### Per-niche breakdown

| Niche | ok | ok-empty | degraded | ok-rate |
|---|---:|---:|---:|---:|
| bariatric-surgery | 9 | 0 | 1 | 90% |
| business-immigration | 10 | 0 | 0 | 100% |
| cosmetic-dentistry | 9 | 1 | 0 | 90% |
| full-arch-dental | 10 | 0 | 0 | 100% |
| hair-transplant | 10 | 0 | 0 | 100% |
| hnw-divorce | 9 | 1 | 0 | 90% |
| ivf-fertility | 9 | 0 | 1 | 90% |
| orthodontics | 10 | 0 | 0 | 100% |
| plastic-surgery | 10 | 0 | 0 | 100% |
| private-lending | 9 | 0 | 1 | 90% |

No niche drops below 90% ok-rate. The failure tail is spread thinly — no
concentrated per-niche hot spot that would implicate a niche-specific
fetcher or extractor gap.

## Failure-mode histogram

| FM | Pattern | Count | Rate |
|---|---|---:|---:|
| FM-13 | Site-fetch timeout / transient failure | 3 | 3% |
| FM-6 | Homepage fetched, extraction returned empty | 2 | 2% |
| FM-1 | CDN anti-bot 403 on homepage | 0 | 0% |
| FM-2 | Yelp 403 | n/a | (no review provider wired yet) |
| FM-4 | Google review count unreachable | n/a | (no review provider) |
| FM-5 | Under-construction / cross-brand redirect | 0 | 0% |
| FM-7 | One-page / brochureware (thin-but-extracted) | 19 | 19% |
| RB-blocked | robots.txt disallow | 0 | 0% |
| HTTP-4xx / HTTP-5xx | Non-403 HTTP errors | 0 | 0% |

### FM-6 — 2 sites, two distinct shapes

Both FM-6 sites returned `status: ok` because the provider fetched HTTP 200
successfully; extraction is the weak link.

- **Shape A — JS-redirect root.** One `<script>` in `<head>` does
  `window.location.href="/lander"`. The HTML payload is ~115 bytes;
  there is no `<body>` for trafilatura to extract. Promoted to
  [`fixtures/fm6-js-redirect-root/`](fm6-js-redirect-root/).
- **Shape B — Maintenance page.** Server returns a 200 body consisting of a
  single `<h1>` ("Site Temporarily Unavailable") and ~180 bytes of HTML.
  Extraction returns the bare text; too thin for synthesis. Promoted to
  [`fixtures/fm6-maintenance-page/`](fm6-maintenance-page/).

### FM-13 — 3 sites, all network-level timeouts

All three returned `network error: Timeout` from `curl_cffi.requests.get`
at the 10-second default provider timeout. One site (`fertility-23`)
took ~20 s total because the `/about` follow-up fetch also timed out.

**Mechanism — not conclusively identified.** Three data points is too
few to infer a specific shared fingerprint (CDN, hosting, CMS). Possible
drivers: heavy first-byte latency on visually-rich medical/aesthetic
homepages; geo-restricted CDN nodes; shared flaky hosting. Repeating this
measurement on a gutter/roofing/waste-management cohort would either
confirm a vertical-specific artifact or show the 3% is baseline network
weather — **companyctx is not the right vehicle for that investigation**;
flagged as register-candidate only (see below).

### FM-7 — 19 sites, thin-but-extracted

19 of the 95 ok sites returned under 1 KB of extracted `homepage_text`
(smallest 370 bytes; median across ok 2.8 KB; mean 3.6 KB). These sites
fetched cleanly; the extractor did its job; the sites just have thin
marketing copy. The envelope correctly emits `status: ok` with the short
text — downstream synthesis is on notice to expect thin inputs. This
matches the RISK-REGISTER FM-7 description: "empty-but-extracted is
valid data."

## Latency

| Cohort | Median | Max |
|---|---:|---:|
| OK-only (95) | 3.83 s | 23.59 s |
| p90 OK-only | 7.72 s | — |

The p90 of ok-only latency is ~7.7 s — the provider's 10-second default
timeout is tight but adequate. The 23.59 s max is a single ok-site outlier
(long TTFB then successful extract); no retries inflated that number.

## RISK-REGISTER taxonomy diff

The register says FM-13 has **0 observed** timeouts and instructs "do not
over-invest." The 100-site run measured **3 / 100 = 3%**.

**No main-body register edit.** Per the decision rule on this PR:

- The 5% threshold for register refinement is not crossed.
- Mechanism is not explained beyond "3 isolated 10-second timeouts" — no
  shared fingerprint identified.
- The sample is 100% medical/aesthetic; other verticals are untested.

A non-normative **candidate-refinement** footer is appended to
`docs/RISK-REGISTER.md` noting the observation + calling for vertical-
diverse replication before any rewording of the FM-13 main body.

## Committed-fixture promotions

Two fixtures promoted — both from HTML-capturable FM-6 signatures in the
100-site run. No mock-block hook required.

| Slug | Failure mode | Source |
|---|---|---|
| [`fm6-js-redirect-root`](fm6-js-redirect-root/) | FM-6 — JS redirect away from root, empty `<head>`-only HTML | Shape observed on one real medical/aesthetic site. HTML is structurally generic (no identifying content). |
| [`fm6-maintenance-page`](fm6-maintenance-page/) | FM-6 — "Temporarily unavailable" 200 response with a single `<h1>` | Shape observed on one real legal-services site. HTML carries only a generic maintenance notice. |

Both fixtures:
- Carry only `homepage.html` + `expected.json` (no about / services /
  provider JSON) — the failure shape is in the homepage response alone.
- Commit real shape with generic content — they contain no business
  names, contact data, or content attributable to the observed sites.
  The shape-match earns the regression guard; the sanitization earns the
  public-OSS commit.
- Wired into the byte-diff regression suite via
  [`tests/test_regression_corpus.py`](../tests/test_regression_corpus.py)
  and the shape-check suite via
  [`tests/test_fixtures_corpus.py`](../tests/test_fixtures_corpus.py).

The regression they guard: if the extractor or the envelope-status
aggregator changes such that an empty-body HTML starts producing
non-empty `homepage_text`, or starts producing a `degraded` envelope,
one of these two fixtures fails on byte-diff. That's the whole point —
honest signalling on empty-but-successful fetches must stay honest.

**Not promoted:**

- **FM-13 timeout.** Requires a provider mock-block hook (fixture-side
  sentinel that triggers a simulated network error). That hook is
  provider code and belongs in its own PR — tracked as a follow-up issue.
- **FM-1 CDN anti-bot 403.** Zero occurrences in this run. The 95% success
  rate is itself the evidence for `curl_cffi@chrome146` being effective
  against the medical/aesthetic SMB CDN population. Other verticals
  pending.
- **FM-5 cross-brand redirect.** Zero observed.

## Full-100 acceptance against issue #22

- [x] Per-site data captured (100 envelopes; private, in `.context/`).
- [x] Aggregate rates computed (95 / 2 / 3).
- [x] FM histogram produced and tied to the register.
- [x] Top broken sites described — all three FM-13 sites are enumerated by
      mechanism above; no per-host naming.
- [x] ≥2 HTML-capturable fixtures committed (`fm6-js-redirect-root`,
      `fm6-maintenance-page`).
- [x] No PII committed (fixtures contain only generic HTML).
- [x] Joel's raw prospect list never landed in the repo.
- [x] Release-readiness ADR committed alongside.
- [n/a] "≥5% failure pattern gets a dedicated fixture" — no single mode
        crossed 5% in the 100-site run (FM-7 does at 19% but is `status: ok`,
        not a failure in the envelope sense). Fixture promotion rule still
        satisfied via the "≥2 real-world failure signatures" floor.

## Reproducing this report

```bash
python3 scripts/run-durability-batch.py \
    --sample path/to/seed-sample.csv \
    --label your-label
```

Input CSV columns: `niche,position,slug,host,heading` (header required).
The harness never fetches directly; it always goes through
`python -m companyctx.cli fetch <host> --json`.
