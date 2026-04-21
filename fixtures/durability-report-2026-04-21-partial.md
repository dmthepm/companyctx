# Durability report — pilot-25 (partial)

**Status:** partial — pilot batch of 25 sites only. Full 100-site run follows
in commit 2.
**Run date:** 2026-04-21.
**Related issue:** [#22](https://github.com/dmthepm/companyctx/issues/22) /
Linear COX-13.
**Go/no-go:** preliminary — on the pilot alone, success rate is well above the
60% `v0.1.0` release-gate threshold. Confirmation awaits the remaining 75-site
run.

## Methodology

- **Source.** Joel's D100 seed list at
  `new-signal-studio/research/*-prospect-list.md` — 12 niche files, 260 total
  prospects with explicit `**Website:**` fields. The `outputs/2026-04-08-d100-*-instantly.csv`
  series (which the TLS spike drew from) has no explicit website column, so
  we stick to the curated `research/` files.
- **Sampling.** Stratified stride sampling across 10 niches. 3 slugs from 5
  niches + 2 slugs from the other 5 niches = 25. Stride sampling picks
  evenly-spaced positions within each niche's eligible list, which avoids
  re-drawing the alphabetical-first-N set the TLS spike used.
- **TLS-spike overlap.** The spike drew from the `d100-*-instantly.csv` series
  (a different surface) with slug-to-URL mapping in a local-only file
  (`research/.slug-map.local.csv`) which is not present on this machine.
  Heuristic mitigation: we dropped the alphabetical-first-N per niche in the
  `research/` lists (matching the spike's first-N sampling rule). Exact-URL
  exclusion is not provable without the slug-map; caveat noted.
- **Privacy.** Sampled hosts stay in `.context/durability/` (gitignored). This
  report aggregates by FM-code and by niche; no individual hosts are named.
  Per-site raw envelopes live outside the repo.
- **Harness.** `scripts/run-durability-batch.py` shells out to `python -m
  companyctx.cli fetch <host> --json` for each row, captures the envelope,
  records latency and `len(pages.homepage_text.encode("utf-8"))`. `robots.txt`
  honored throughout (no `--ignore-robots`). Pacing floor of 2s between
  requests. Subprocess timeout 45s.
- **Classification.** Each run mapped to one of the FM codes in
  [`docs/RISK-REGISTER.md`](../docs/RISK-REGISTER.md), plus two new codes
  added for observed-but-register-absent patterns:
  - `RB-blocked` — robots.txt disallow.
  - `HTTP-4xx` / `HTTP-5xx` — non-403/401 HTTP errors.
  (Neither fired in the pilot.)
- **Niche skew caveat.** The RISK-REGISTER was mined from gutter / roofing /
  IV-therapy transcripts (small-biz home services). This seed list is
  medical / aesthetic SMBs. FM modes are site-shape-driven (WordPress / SPA /
  Cloudflare-fronted / JS-rendered), not niche-driven — so the register's
  taxonomy remains applicable, but **frequencies in this report are specific
  to medical/aesthetic SMBs**. Gutter/roofing/IV verticals may weight the
  modes differently. Follow-up if the skew proves load-bearing: separate
  issue.

## Pilot sample shape

| Niche | Pilot count |
|---|---:|
| bariatric-surgery | 3 |
| business-immigration | 3 |
| cosmetic-dentistry | 3 |
| full-arch-dental | 3 |
| hair-transplant | 3 |
| hnw-divorce | 2 |
| ivf-fertility | 2 |
| orthodontics | 2 |
| plastic-surgery | 2 |
| private-lending | 2 |
| **Total** | **25** |

## Aggregate rates

| Envelope outcome | Count | Rate |
|---|---:|---:|
| `status: ok` with non-empty `homepage_text` | 21 | **84%** |
| `status: ok` with empty `homepage_text` (FM-6 shape) | 1 | 4% |
| `status: partial` | 0 | 0% |
| `status: degraded` | 3 | 12% |

**Success rate (ok + non-empty): 84%.** Well above the 60% release-gate
threshold.

Note on `partial`: with the M2 orchestrator shipping only one provider
(`site_text_trafilatura`), the envelope cannot emit `partial` — there's
nothing to be "partial" between. When Attempt-2 / Attempt-3 providers land,
the partial rate becomes the number of real interest.

## Failure-mode histogram

| FM | Pattern | Count | Rate |
|---|---|---:|---:|
| FM-13 | Site-fetch timeout / transient failure | 3 | **12%** |
| FM-6 | Homepage fetched but extraction returned empty | 1 | 4% |
| FM-1 | CDN anti-bot 403 on homepage | 0 | 0% |
| FM-2 | Yelp 403 | n/a | — (no review provider wired) |
| FM-4 | Google review count unreachable | n/a | — (no review provider) |
| FM-5 | Under-construction / cross-brand redirect | 0 | 0% |
| FM-7 | One-page / brochureware | (see below) | — |
| RB-blocked | robots.txt disallow | 0 | 0% |
| HTTP-4xx / HTTP-5xx | Non-403 HTTP errors | 0 | 0% |

### FM-7 "thin-data" sub-observation

4 of the 21 `ok` sites returned under 1 KB of extracted `homepage_text`
(smallest 594 bytes; median 2.2 KB; mean 3.8 KB). These sites fetched
cleanly and extracted, but extraction is thin — small-team clinics with
short marketing copy. The envelope emits `status: ok`, which is correct;
downstream synthesis is on notice to expect thin inputs. This matches
the RISK-REGISTER FM-7 description ("empty-but-extracted is valid data").

## Latency

| Cohort | Median | Mean | Max |
|---|---:|---:|---:|
| All 25 sites | 3.9 s | 5.3 s | 20.1 s |
| OK-only (21) | 3.8 s | 4.3 s | 11.4 s |

The long tail on the "all" cohort is driven by the three timeout sites
(10 s default timeout, one site took 20 s total because the about-page
fetch also timed out). OK-only latency looks reasonable for an untuned
default — a follow-up to trim the default timeout from 10 s to something
like 6-8 s could be worthwhile, but that's outside this issue's scope.

## RISK-REGISTER taxonomy diff

The register predicted FM-13 (timeouts) at "0 occurrences … do not over-invest."
The pilot measured 3/25 = 12%. **Refinement candidate.** Two possibilities:

1. D100 log-mining undercounts transient site timeouts because the sub-agent
   re-tries or substitutes in-LLM before the event is recorded as a
   failure, whereas our one-shot harness surfaces them directly.
2. The niche skew (medical/aesthetic) over-represents sites with heavier
   front-end stacks (full-page visual builders, video hero sections) that
   take longer to first-byte than the register's gutter/roofing corpus.

Either way, FM-13 deserves a re-weighting in the register based on the full
100 — not this 25. **No register edits yet.** If the full-100 confirms FM-13
is ≥5%, the update lands in commit 2 along with the final report.

## Committed-fixture promotions

**None promoted in commit 1.** Of the two failure modes observed:

- **FM-13 (timeout, 12%)** is the dominant observed mode but is **not
  HTML-fixturable** — the failure is a network-level timeout, there's no
  HTML response to snapshot. Promoting this as a regression fixture
  requires a provider-level hook to simulate a blocked fetch in `--mock`
  mode (e.g., a `fixture-block.txt` sentinel inside the fixture dir). That
  hook is a provider change and belongs in its own focused PR; tracked as
  a follow-up.
- **FM-6 (empty extraction, 4%)** is HTML-fixturable — the site returns
  200 with an SPA shell that trafilatura can't extract from. One pilot
  site exhibited this shape. Fixture promotion deferred to commit 2 so
  sanitization + bucket-slug naming can be reviewed alongside the full-100
  evidence.

Neither FM-1 nor FM-5 (the modes the issue originally anticipated promoting)
fired in the pilot.

Acceptance bullet ("≥2 real-world failure signatures get new committed
fixtures") currently reads **0 / 2**. Path to `2 / 2`:

- Option A: land a provider mock-block hook (small, contained) and use it
  to fixture FM-13 alongside an HTML fixture for FM-6. Two fixtures from
  pilot evidence alone.
- Option B: wait for the full-100 to surface FM-1 / FM-5 / HTTP-error
  shapes that are natively HTML-fixturable, then promote from the
  combined evidence base.

Decision deferred to the `v0.1.0` release-readiness ADR in commit 2.

## Preliminary release-readiness signal

- Success rate **84%** against a real D100-adjacent seed list, on an
  M2 single-provider orchestrator, with `robots.txt` honored throughout.
- No anti-bot blocks observed in the pilot draw (curl_cffi at `chrome146`,
  fresh fingerprint).
- Failure tail is dominated by network timeouts, not by extraction
  regressions or CDN blocks.

Nothing in this pilot argues against `v0.1.0` shipping. Final signal after
the full 100.

## Reproducing this report

With access to a private seed CSV (format `niche,position,slug,host,heading`):

```bash
python3 scripts/run-durability-batch.py \
    --sample path/to/seed-sample.csv \
    --label pilot-25
```

The harness never touches the network without going through
`companyctx fetch`; no standalone fetching.
