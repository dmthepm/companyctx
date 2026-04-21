# Durability report — 100-site D100 run

**Run date:** 2026-04-21.
**Related issue:** [#22](https://github.com/dmthepm/companyctx/issues/22) /
Linear COX-13.
**Release-readiness ADR:**
[`decisions/2026-04-21-v0.1.0-release-readiness.md`](../decisions/2026-04-21-v0.1.0-release-readiness.md).
**Raw evidence (slug-only, committed):**
[`research/2026-04-21-durability-sample-raw.jsonl`](../research/2026-04-21-durability-sample-raw.jsonl)
— 100 rows, reproducible from `classify()` in
[`scripts/run-durability-batch.py`](../scripts/run-durability-batch.py).
**Headline:** **97 / 100** sites returned envelope `status: ok`; of
those, **76** returned ≥ 1 KB of extracted `homepage_text` and **21**
returned a thin/empty extract (FM-7). 3 sites returned `status:
degraded` via FM-13 network timeout. Well above the 60% `v0.1.0`
release-gate.

## Reproducing every number in this report

Each row in
[`research/2026-04-21-durability-sample-raw.jsonl`](../research/2026-04-21-durability-sample-raw.jsonl)
has `slug`, `niche`, `status`, `fm_code`, `outcome`, `homepage_bytes`,
`latency_ms`, `wall_ms`, `provider_status`, `provider_error`. The
committed classifier in
[`scripts/run-durability-batch.py`](../scripts/run-durability-batch.py)
(`classify()` + `FM7_THIN_BYTES`) is what produced every `fm_code`
here. Regenerate the aggregate with:

```bash
python3 -c "
import json, collections
rows = [json.loads(l) for l in open('research/2026-04-21-durability-sample-raw.jsonl')]
print('outcome:', dict(collections.Counter(r['outcome'] for r in rows)))
print('fm_code:', dict(collections.Counter(r['fm_code'] for r in rows)))
print('status :', dict(collections.Counter(r['status']  for r in rows)))
"
```

Domain-to-slug mapping is **not** committed — it lives only in
`.context/durability/` (gitignored) and in Joel's private seed CSVs.

## Methodology

- **Seed source.** Joel's D100 prospect lists at
  `new-signal-studio/research/*-prospect-list.md` — 12 niche files with
  explicit `**Website:**` fields.
- **Sampling.** Stratified stride sample — 10 hosts per niche × 10
  niches = 100. Stride sampling picks evenly-spaced positions within
  each niche's eligible list, avoiding the alphabetical-first-N the
  TLS spike drew. Deterministic for a given seed list.
- **TLS-spike overlap.** The TLS spike drew from the
  `d100-*-instantly.csv` series with a local-only slug-to-URL map
  (`research/.slug-map.local.csv`) not present on this machine. We
  dropped the alphabetical-first-2-or-3 per niche (matching the
  spike's first-N rule) before stride-sampling. Exact-URL exclusion is
  not provable without the slug-map.
- **Fetch.**
  [`scripts/run-durability-batch.py`](../scripts/run-durability-batch.py)
  shells out to `python -m companyctx.cli fetch <host> --json` per
  row, captures the full envelope + wall-clock latency +
  `len(pages.homepage_text.encode("utf-8"))`. `robots.txt` honored
  throughout (no `--ignore-robots`). 2-second pacing floor; 45-second
  subprocess timeout; provider network timeout defaults to 10s (per
  `companyctx.core.DEFAULT_TIMEOUT_S`).
- **Classification.** Every `fm_code` in the raw JSONL is produced by
  [`classify()` in `scripts/run-durability-batch.py`](../scripts/run-durability-batch.py).
  FM codes map 1:1 to [`docs/RISK-REGISTER.md`](../docs/RISK-REGISTER.md).
  Extensions are `RB-blocked` (robots disallow) and `HTTP-4xx` /
  `HTTP-5xx` (non-403 HTTP errors); neither fired in this run. The
  `FM7_THIN_BYTES` threshold is 1024 — extracted `homepage_text` below
  1 KB is flagged as FM-7 per the register's "thin-but-extracted"
  definition.
- **Privacy.** Per-site hosts and envelopes live only in
  `.context/durability/` (gitignored). The committed raw JSONL carries
  slugs, not hosts. Joel's raw prospect list never touches this repo.
- **Vertical skew — acknowledged.** The sample is **100%
  medical/aesthetic SMBs**. RISK-REGISTER was mined from gutter /
  roofing / IV-therapy transcripts. FM codes are site-shape-driven
  (WordPress / SPA / Cloudflare-fronted), not niche-driven — the
  taxonomy transfers, but frequencies describe medical/aesthetic SMBs
  only. Other verticals untested at scale.

## Sample shape

Exactly 10 hosts per niche × 10 niches. Niches:
bariatric-surgery, business-immigration, cosmetic-dentistry,
full-arch-dental, hair-transplant, hnw-divorce, ivf-fertility,
orthodontics, plastic-surgery, private-lending.

## Aggregate rates

| Envelope outcome | Count | Rate |
|---|---:|---:|
| `status: ok`, `homepage_text` ≥ 1 KB | 76 | 76% |
| `status: ok`, `homepage_text` < 1 KB (FM-7 thin/empty) | 21 | 21% |
| `status: ok` (any) — **release-gate measure** | **97** | **97%** |
| `status: partial` | 0 | 0% |
| `status: degraded` (FM-13 timeout) | 3 | 3% |

The 60% release-gate applies to `status: ok`, which this cohort hits
at 97%.

`partial` cannot fire today — the M2 orchestrator ships with a single
provider, so an envelope is either `ok` or `degraded`. `partial`
becomes meaningful once Attempt-2 (smart-proxy) or Attempt-3
(direct-API) providers land.

### Per-niche breakdown

| Niche | ok + non-thin | FM-7 thin | FM-13 degraded | status=ok rate |
|---|---:|---:|---:|---:|
| bariatric-surgery | 8 | 1 | 1 | 90% |
| business-immigration | 8 | 2 | 0 | 100% |
| cosmetic-dentistry | 8 | 2 | 0 | 100% |
| full-arch-dental | 9 | 1 | 0 | 100% |
| hair-transplant | 9 | 1 | 0 | 100% |
| hnw-divorce | 6 | 4 | 0 | 100% |
| ivf-fertility | 8 | 1 | 1 | 90% |
| orthodontics | 5 | 5 | 0 | 100% |
| plastic-surgery | 9 | 1 | 0 | 100% |
| private-lending | 6 | 3 | 1 | 90% |

No niche falls below 90% `status: ok`. The FM-7 (thin-extract) tail
weights toward `orthodontics` (5 / 10) and `hnw-divorce` (4 / 10) —
small-practice verticals where websites tend to be one-page
brochureware. This matches the register's FM-7 signature description.

## Failure-mode histogram (from raw JSONL)

| FM | Pattern | Count | Rate |
|---|---|---:|---:|
| FM-7 | `status: ok`, thin/empty extract (< 1 KB) | 21 | 21% |
| FM-13 | Network timeout | 3 | 3% |
| FM-1 | CDN anti-bot 403 | 0 | 0% |
| FM-5 | Under-construction / cross-brand redirect | 0 | 0% |
| FM-6 | Raw text captured, structured fields missed | 0 | 0% |
| RB-blocked | robots.txt disallow | 0 | 0% |
| HTTP-4xx / HTTP-5xx | Non-403 HTTP errors | 0 | 0% |

**FM-6 note.** The register's FM-6 is "raw text captured, structured
extraction missed" — a signal that pairs with a `signals_site_heuristic`
provider (which is not yet wired in M2). With only
`site_text_trafilatura` shipped, "structured extraction missed" can't
be distinguished from "site simply has no `/services` route." The
classifier reports 0 FM-6 honestly rather than lumping brochureware
into it. When `signals_site_heuristic` ships, re-run this measurement
to get a real FM-6 rate.

### FM-7 — 21 sites, two HTML-fixturable shapes + 19 brochureware

FM-7 dominates the failure tail. Three shapes account for it:

- **Shape A — JS-redirect root** (1 site, 0 bytes extracted). One
  `<script>` in `<head>` does `window.location.href="/lander"`; no
  `<body>` for trafilatura to extract. Promoted to
  [`fixtures/fm7-js-redirect-root/`](fm7-js-redirect-root/).
- **Shape B — Maintenance page** (1 site, 19 bytes extracted). Server
  returns a 200 body consisting of a single `<h1>` ("Site Temporarily
  Unavailable"). Promoted to
  [`fixtures/fm7-maintenance-page/`](fm7-maintenance-page/).
- **Shape C — Brochureware / small-practice site** (19 sites, 50–935
  bytes extracted). Fetch + extract both succeeded; the site just has
  thin marketing copy. Not fixture-promoted individually — the shape
  is well-covered by the existing synthetic corpus (`acme-bakery` et
  al.) plus the two extreme FM-7 fixtures above.

### FM-13 — 3 sites, all 10-second network timeouts

Three sites returned `network error: Timeout` from
`curl_cffi.requests.get`:

| slug | niche | provider_latency_ms | wall_ms |
|---|---|---:|---:|
| bariatric-08 | bariatric-surgery | 10119 | 10443 |
| fertility-23 | ivf-fertility | 20052 | 20265 |
| lending-18 | private-lending | 10111 | 10328 |

**The `fertility-23` row is anomalous.** Provider latency is ~20 s,
but the configured timeout is 10 s and `_from_network` exits on
homepage timeout before attempting `/about` — there is no code path
that stacks two 10-second timeouts on this host. A clean re-probe
(`curl_cffi.requests.get` to the same URL at 10 s timeout) returns at
10 s as expected (`curl: (28) Connection timed out after 10002 ms`).
The ~20 s is therefore a transient effect — likely slow DNS
resolution happening before libcurl's timer starts, or resolver
retries — rather than a reproducible provider anomaly. It is **not**
evidence of `/about` also timing out. Described honestly here rather
than explained away.

**Mechanism — not conclusively identified.** Three data points is too
few to infer a specific shared fingerprint (CDN, hosting, CMS).
Possible drivers: heavy first-byte latency on medical / aesthetic
homepages; geo-restricted CDN nodes; shared flaky hosting. A vertical-
diverse rerun is the right follow-up, not a register edit (see
[`docs/RISK-REGISTER.md`](../docs/RISK-REGISTER.md) §"Candidate
refinements").

## Latency (from raw JSONL)

| Cohort | Median | p90 | Max |
|---|---:|---:|---:|
| OK + thin (97 sites) | 3828 ms | 7720 ms | 23590 ms |

The p90 is 7.7 s; the provider's 10 s default timeout is tight but
adequate on the happy path. The 23.59 s max is a single ok-site
outlier (long TTFB, still completed); no retries inflated it.

## RISK-REGISTER taxonomy diff

The register says FM-13 has **0 observed** timeouts and instructs "do
not over-invest." The 100-site run measured **3 / 100 = 3%** — below
the 5% refinement threshold, mechanism unidentified, and the sample is
100% medical / aesthetic. Per the decision rule for this PR, the
register's main FM-13 body is **unchanged**; a non-normative
candidate-refinement footer was appended in
[`docs/RISK-REGISTER.md`](../docs/RISK-REGISTER.md) (see "Candidate
refinements — needs vertical-diverse replication").

The register's FM-7 description ("One-page / brochureware /
relationship-driven B2B site … Providers that succeed at their
extractor job return `ok` — the fetch worked; the site just has
nothing to extract") is **confirmed at 21%** in this cohort. No
register edit needed — the register already captures the shape; it
just hadn't attached a frequency to it.

## Committed-fixture promotions

Two fixtures promoted, both HTML-capturable FM-7 shapes from the run.
No mock-block hook required.

| Slug | Failure mode | Source |
|---|---|---|
| [`fm7-js-redirect-root`](fm7-js-redirect-root/) | FM-7 — JS redirect away from root | Shape observed on one medical/aesthetic site. HTML is structurally generic (no identifying content). |
| [`fm7-maintenance-page`](fm7-maintenance-page/) | FM-7 — "Temporarily unavailable" 200 response | Shape observed on one legal-services site. HTML carries only a generic maintenance notice. |

Both fixtures:
- Carry only `homepage.html` + `expected.json` (no about / services /
  provider JSON).
- Commit a shape-match of real observations with generic content — no
  business names, contact data, or attributable content.
- Wired into the byte-diff regression suite via
  [`tests/test_regression_corpus.py`](../tests/test_regression_corpus.py)
  (`REGRESSION_SLUGS`) and the shape-check suite via
  [`tests/test_fixtures_corpus.py`](../tests/test_fixtures_corpus.py)
  (`FAILURE_FIXTURE_SLUGS`).

The regression they guard: if the extractor or the envelope-status
aggregator changes such that a thin-or-empty HTML starts producing
non-empty `homepage_text`, or a `degraded` envelope on what was
actually a successful fetch, one of these two fixtures fails on
byte-diff.

**Not promoted:**

- **FM-13 timeout.** Requires a provider mock-block hook (fixture-side
  sentinel that triggers a simulated network error). Tracked as
  [issue #40](https://github.com/dmthepm/companyctx/issues/40).
- **FM-1 CDN anti-bot 403.** Zero occurrences; the 97% status=ok rate
  is itself the evidence for `curl_cffi@chrome146` being effective
  against this cohort's CDN population.
- **FM-5 cross-brand redirect.** Zero observed.

## Acceptance against issue #22

- [x] Per-site data captured — 100 envelopes summarised in
      [`research/2026-04-21-durability-sample-raw.jsonl`](../research/2026-04-21-durability-sample-raw.jsonl).
- [x] Aggregate rates computed — reproducible from the committed JSONL.
- [x] FM histogram produced and tied to the register — every observed
      mode maps to a register row with matching semantics.
- [x] Failure details described — all three FM-13 sites enumerated by
      slug + latency; no per-host naming.
- [x] ≥ 2 HTML-capturable fixtures committed (`fm7-js-redirect-root`,
      `fm7-maintenance-page`).
- [x] No PII committed; fixtures contain only generic HTML.
- [x] Joel's raw prospect list never landed in the repo.
- [x] Release-readiness ADR committed alongside
      ([`decisions/2026-04-21-v0.1.0-release-readiness.md`](../decisions/2026-04-21-v0.1.0-release-readiness.md)).

## Reproducing the fetch path

```bash
python3 scripts/run-durability-batch.py \
    --sample path/to/seed-sample.csv \
    --label your-label
```

Input CSV columns: `niche,position,slug,host,heading` (header
required). The harness never fetches directly; it always goes through
`python -m companyctx.cli fetch <host> --json`.
