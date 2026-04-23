---
type: research
date: 2026-04-23
topic: reviews-extraction method survey — desktop landscape + probe methodology
category: provider-selection
status: slice-a-complete-slice-b-pending
linked_decisions:
  - decisions/2026-04-23-reviews-provider-selection.md
linked_issues:
  - https://github.com/dmthepm/companyctx/issues/116
raw_evidence: research/2026-04-23-reviews-probe-raw.jsonl
---

# Reviews-extraction method survey (Slice A — desktop)

## One-sentence summary

Across eight candidate methods surveyed desktop-only (no live probe yet), the **three finalists that go forward into the Slice B live probe** are **Google Places API (New) Enterprise SKU** (first-party, authoritative, migration target for our legacy integration), **Yelp Fusion Plus** (first-party, $9.99/1k, free at partner volume during 30-day trial, US-only but matches the partner corpus), and **Apify `compass/crawler-google-places`** (lowest nominal cost but carries post-Feb-2026 scraper fragility + residential-proxy surcharge that this doc flags honestly); SerpAPI is eliminated pre-probe on active Google DMCA litigation (Dec 2025), Google Places Essentials is eliminated because the fields we need (`rating`, `userRatingCount`) are in the Enterprise tier of the New API, Outscraper is eliminated as it wraps the same scraped-Google data as Apify without adding control, BrightData is eliminated on setup friction for a pipx CLI user, and direct Yelp scraping is eliminated on ToS posture.

## Scope

This document resolves **Slice A** of [issue #116](https://github.com/dmthepm/companyctx/issues/116):

1. Enumerate and score the candidate reviews-extraction methods.
2. Nominate the top three for a live 10-site probe.
3. Document the probe methodology, site mix, and decision rule so Slice B is a one-command execution.

**Slice B — deferred pending key + budget provisioning**: run the probe
(30 calls, $5–15 spend across three providers × 10 sites), promote the ADR
from `proposed` → `accepted`, open the implementation issue if the
recommendation is to switch/compose.

## Why this wasn't done in v0.3

The v0.3 release shipped `reviews_google_places` (Google Places Legacy
Place Details) as the reviews provider without a head-to-head probe. The
issue body frames that as "chosen by assumption, not evidence"; in fairness,
an informal desktop survey did happen in v0.1 (see
`noontide-projects/research/2026-04-20-research-pack-reviews-business-claude-code.md`)
— what was missing was a **measured, same-corpus comparison**. The TLS
spike (#21 / `research/2026-04-21-tls-impersonation-spike.md`) is the
pattern we should have mirrored: pick candidates, run all of them against
the same sample, decide on numbers. This doc puts that pattern in place
for reviews.

## Partner-shaped requirements

Distilled from the partner's pipeline logs
(`new-signal-studio/logs/d100-run-*.md` session transcripts):

1. **Only two fields consumed downstream.** The partner's research briefs
   use `rating` and `review_count` as social-proof tokens for script-angle
   selection. Review snippets, categories, hours, photos, and sentiment are
   never consumed. **Conclusion: richness weighting is LOW.**
2. **Multi-source fallback is the partner's own posture.** When Google
   data returns "INSUFFICIENT DATA," the partner's own workflow falls back
   to Yelp / HomeAdvisor / Angi / BBB / Trustindex. The pipeline is
   designed to tolerate a missing source, not to stall on one.
   **Conclusion: composite fallback beats single-provider.**
3. **Volume:** ~100 prospects/day, ~3000/month. Monthly cost delta
   between 5.4¢/call and 1.0¢/call is $132/month ($175 vs $30 floor).
4. **No cost complaints on file.** The partner has not flagged Google
   Places as expensive in any session transcript or comment. The
   cost-reduction pressure comes from the issue author (Devon), not the
   downstream consumer. **Conclusion: don't optimize prematurely — measure
   first.**

## Candidate matrix (desktop)

Eight method categories, scored on the axes named in the issue (cost,
coverage, data shape, ToS, maintenance). Scores are desktop-only signals;
probe numbers replace them in Slice B.

| # | Method | Type | Cost/call (estimate) | Rating+count returned? | ToS posture | Maintenance signal | Status |
|---|---|---|---|---|---|---|---|
| 1 | **Google Places Legacy** (current) | First-party API | ~5.4¢ (Text Search 3.2¢ + Details Atmosphere 2.2¢) | Yes | Clean (first-party) | **Legacy** — cannot be enabled for new projects since 2025-03-01 | Probe as current baseline, but **migration-required regardless** |
| 2 | **Google Places API (New) Essentials** | First-party API | ~$2/1k (0.2¢) | **No** — `rating`/`userRatingCount` are in Enterprise tier, not Essentials | Clean | Active | **Eliminated pre-probe** — missing required fields |
| 3 | **Google Places API (New) Pro** | First-party API | ~$17/1k (1.7¢) — field mask | Partial — `displayName`, `primaryType`; **not** `rating` | Clean | Active | **Eliminated pre-probe** — missing required fields |
| 4 | **Google Places API (New) Enterprise** | First-party API | ~$25/1k (2.5¢) + Text Search separate | **Yes** — `rating`, `userRatingCount`, `websiteUri`, hours | Clean | Active | **Finalist — probe slot #1** |
| 5 | **Apify `compass/crawler-google-places`** (and peers) | Scraper actor | ~$2.10/1k nominal; +2-4¢ residential proxy after Feb-2026 lockdown | Yes (`reviewsCount`, `totalScore`) | Gray (Google ToS redistribution risk) | Active, multi-maintainer; breakage wave in Feb-2026 | **Finalist — probe slot #3** |
| 6 | **Apify Yelp actors** (`tri_angle/yelp-scraper` etc.) | Scraper actor | ~$1/1k biz + $1 start (91.3% success) | Yes | Gray (Yelp ToS prohibits scraping) | Active, variable success | Evaluated; not finalist (duplicates Yelp Fusion's signal at worse ToS) |
| 7 | **Outscraper Google Maps API** | Scraper-wrapper API | ~$1–3/1k | Yes | Gray (inherits scraper ToS + redistribution issue) | Aggregator, opaque source-chain | **Eliminated pre-probe** — wraps the same scraped data as Apify without adding ToS protection or control |
| 8 | **Yelp Fusion Plus** | First-party API | ~$9.99/1k = 1¢/call; 30-day free trial; 500 calls/day cap | Yes (rating, review_count, 3 excerpts) | **Clean (first-party)** | Active; Jul-2024 pricing change controversy subsided | **Finalist — probe slot #2** |
| 9 | **BrightData Web Scraper IDE** (Yelp/Google) | Enterprise scraping | Custom + proxy usage | Yes (configurable) | Gray | Active but enterprise | **Eliminated pre-probe** — setup friction incompatible with pipx-CLI user |
| 10 | **SerpAPI Google Maps** | SERP wrapper | ~1.5¢/call effective | Yes | **Active Google DMCA lawsuit filed Dec-2025** (motion-to-dismiss hearing 2026-05-19) | Active but legally contested | **Eliminated pre-probe** — naming SerpAPI in a public OSS ADR during live Google litigation is a ship-and-regret risk. Reconsider post-ruling. |
| 11 | **DataForSEO Google Maps** | Aggregator API | Pay-as-you-go, ~$50/mo entry; Maps SERP variable | Yes | Cleaner than SerpAPI (no active litigation on file); still relies on scraped data | Active enterprise | Evaluated; not finalist (insufficient pricing transparency for a 10-site probe, adds a fourth provider beyond the $15 budget envelope) |
| 12 | **Direct Yelp page scraping** | Homebrew | ~0¢ (proxy costs) | Yes | **Yelp ToS explicitly prohibits** | N/A | **Eliminated** — named for completeness only; would never ship |

### Eliminations, reasoned

- **Google Places (New) Essentials / Pro.** Google's New API tier system
  puts `rating` and `userRatingCount` in the **Enterprise** Place Details
  SKU. Essentials returns address/location/types only; Pro adds
  display-name/phone but still not the rating. Our required fields
  force Enterprise. The "downgrade to Essentials" outcome the issue
  listed is architecturally impossible for our use case.
- **SerpAPI.** Google sued SerpAPI in Dec-2025 under the DMCA alleging
  SearchGuard bypass; motion-to-dismiss hearing set for 2026-05-19. For
  a public OSS project to name SerpAPI as an `accepted` reviews provider
  during active litigation is a reputational and legal-exposure risk
  disproportionate to the ~0.8¢/call potential savings. Revisit post-
  ruling; not during this ADR cycle.
- **Outscraper.** Wraps scraped Google Maps data. Inherits the same
  Feb-2026 limited-view fragility as Apify actors and the same
  Google-ToS redistribution gray zone, without giving us either lower
  cost than Apify direct or ToS clarity over Apify direct. Adds a fourth
  provider to the probe without buying any axis we don't already have
  covered. Eliminated to keep the probe inside the $15 envelope.
- **BrightData.** Enterprise Web Scraper IDE requires BrightData account
  setup, proxy-unit management, and custom scraper development. Setup
  friction for a `pipx install companyctx` user is too high for a
  default-path provider. If we ever need it, it slots into the
  `SmartProxyProvider` Attempt-2 layer, not the reviews slot.

### Finalists — probe slot justification

**Slot #1: Google Places API (New) Enterprise.** First-party,
authoritative rating, migration target for our legacy integration (which
Google has flagged as non-enablable for new projects since 2025-03-01).
Even if we decide to switch the default, the Enterprise SKU becomes the
ToS-clean escape hatch. Must be measured.

**Slot #2: Yelp Fusion Plus.** First-party, US-only (matches partner
corpus — medical-aesthetic and home-services are US-heavy), 500 calls/day
cap is above the partner's 100/day volume so the 30-day trial is
effectively free, $9.99/1k thereafter is cheaper than Google New
Enterprise. Honest coverage gap: businesses not listed on Yelp at all
(more common in home-services than aesthetic). Must be measured.

**Slot #3: Apify `compass/crawler-google-places`.** The scraper-actor
category the issue specifically asks about. Most-used Google Maps actor
on Apify (`compass/` prefix is Apify's most-maintained third-party
namespace). Headline price ~$2.10/1k looks like a 20× savings over
Google Enterprise, but the probe must measure **effective cost with
residential proxies** (the Feb-2026 limited-view rollout broke most
legacy scrapers and survivors need residential-proxy rotation). If the
effective cost lands above ~2¢/call the advantage evaporates. Must be
measured.

(Apify also has cheaper newer actors — e.g. `kaix/google-maps-places-scraper`
at ~$0.10/1k nominal — but they have far lower monthly-user counts
(44 total users, 28 monthly). Using the higher-usage `compass/` actor
gives the probe a signal about actor-stability, which is the load-bearing
question for the whole scraper-actor category. If `compass/` fails, no
other actor is likely to succeed under the same Google-side pressure.)

## Probe methodology (for Slice B)

### Probe-set design

**10 slugs**, sanitized, distributed across the partner's actual ICP mix:

| Slot | Category | Rationale |
|---|---|---|
| 1-4 | Medical/aesthetic (SMB) | Highest Google Places coverage expected — baseline |
| 5-7 | Home-services (gutter / roofing / similar) | Lower Google Places coverage; stresses coverage axis |
| 8-9 | No-website-just-Facebook | Edge case — tests ZERO_RESULTS handling |
| 10 | Deliberately obscure prospect | Coverage-gap stress test |

Slugs sampled deterministically (alphabetical first-N with category
filter) from the partner's 209-site v0.4 validation corpus documented
in `research/2026-04-23-v0.4-partner-integration-revalidation.md`. The
slug → real-URL mapping lands in `research/.slug-map-cox64.local.csv`
(gitignored under `research/*.local.*`).

### Measurement harness

A Python CLI, `scripts/probe_reviews.py` (committed under this PR), takes
the slug list and a provider set, runs one call per (slug, provider)
cell, and appends a row to `research/2026-04-23-reviews-probe-raw.jsonl`
per cell. Row shape:

```json
{
  "slug": "med-aesth-01",
  "provider": "google_places_new_enterprise | yelp_fusion_plus | apify_compass_crawler",
  "run_id": "2026-04-23-<uuid4>",
  "run_date": "2026-04-23",
  "status": "ok | zero_results | blocked | error",
  "rating": 4.7,
  "review_count": 142,
  "data_source_name": "Business Display Name",
  "latency_ms": 1184,
  "cost_incurred_cents": 3,
  "notes": "...optional free-text...",
  "error_code": null,
  "error_message": null,
  "proxy_used": "residential | none",
  "raw_response_hash": "sha256:..."
}
```

Provider credentials live in the operator's local env (`GOOGLE_PLACES_API_KEY`,
`YELP_FUSION_API_KEY`, `APIFY_TOKEN`) and are never committed. The harness
is provider-agnostic: adding a fourth provider is one adapter class.

### Site mix: why 10 and not 100

Per `docs/ARCHITECTURE.md`'s measurement culture (see the 20-site TLS
spike that sized #21), **10 sites is a cost-and-fit sanity check, not a
coverage benchmark**. At n=10, a single ZERO_RESULTS swings coverage by
10 percentage points. We cannot tell 85% from 95% at this n. What we
**can** tell:

- Which providers return `rating+count` at all vs. ZERO_RESULTS on a
  representative slice.
- The **effective billed cost per successful call** (nominal + proxy +
  actor-start overheads).
- Whether ratings **agree within ±0.3 stars** across providers for the
  same business (divergence = data-quality signal).
- Which providers return results for the two no-website-just-Facebook
  edge cases.

If two providers disagree hard at n=10, we expand to n=30 or drop the
divergent one; that's a Slice B branch, not a Slice A commitment.

### Decision rule (pre-committed)

The recommendation after the probe follows this rule, pre-registered
before measurement to avoid motivated interpretation:

```
effective_cost_per_successful_call(p) =
    (nominal_cost_cents(p) + proxy_cost_cents(p) + actor_start_cents(p))
    / coverage_rate(p)

Recommend KEEP Google Places (migrate Legacy → New Enterprise) if:
    effective_cost(google_new_enterprise) ≤ 1.5 × effective_cost(cheapest_other)
    AND coverage(google_new_enterprise) ≥ 0.8

Recommend COMPOSITE (Google New Enterprise → Yelp Fusion fallback) if:
    coverage(google_new_enterprise) < 0.8
    AND coverage(google OR yelp) ≥ 0.9
    AND effective_cost(composite_expected) ≤ 1.2 × effective_cost(google_only)

Recommend SWITCH to cheapest viable if:
    effective_cost(cheapest) < 0.5 × effective_cost(google_new_enterprise)
    AND coverage(cheapest) ≥ coverage(google_new_enterprise) - 0.05
    AND ToS posture is first-party or Gold-tier Apify actor

Else: KEEP Legacy temporarily, reopen probe with different shortlist.
```

All three branches land in the ADR; the probe numbers pick which.

## Decision matrix (pre-probe, weights only)

Weights ratify the issue spec, with one change flagged below:

| Axis | Weight | Notes |
|---|---|---|
| Effective cost per successful call | 3× | Merged "cost" + "coverage" into one axis since they combine multiplicatively |
| ToS / redistribution posture | **3×** | **Raised from issue's 2×.** Adversarial review flagged that scraped-Google-Maps data redistribution in partner reports is the most plausible real-world blow-up. First-party > Gold-Apify > Outscraper/BrightData > direct scraping. |
| Data consistency vs baseline | 2× | Ratings diverging >0.3 between providers = data-quality signal |
| Setup friction for partners | 1× | How many env vars + how much account setup |
| Data richness | 1× | Partner consumes rating+count only — lowest weight |

Coverage rate was folded into "effective cost" because a provider that
covers 80% of sites at 1¢/call is cheaper per **successful** call
(1.25¢) than one that covers 100% at 2¢ (2¢). Separating the two axes
double-counts the signal.

## Out of scope

- **Live probe execution, cost capture, ADR promotion to `accepted`.**
  Requires operator to provision Google Places (New) Enterprise key,
  Yelp Fusion Plus key, and Apify token + residential-proxy allocation.
  Total probe budget $5–15 per [issue #116 acceptance](https://github.com/dmthepm/companyctx/issues/116).
  Tracked as Slice B — see the follow-up issue linked from the
  PR description.
- **Implementation of the chosen provider(s).** A switch from Legacy
  Google Places to New Enterprise, or to a composite, is a provider
  change — a `reviews_google_places_new.py` file, a new
  `reviews_yelp_fusion.py` file, updated tests, updated fixtures,
  updated `PROVIDERS.md`, a `CHANGELOG.md` entry under an unreleased
  v0.5 section. Out of scope for a research/ADR ticket; tracked as the
  implementation follow-up issue.
- **Extending beyond 10 sites.** Covered in methodology above. If the
  probe reveals ambiguity (two providers tied within 10%), we go to 30
  sites before promoting the ADR, and that's a Slice B branch.
- **Non-review providers** (social signals, categories, hours). Out of
  scope per the issue.

## Reproducibility

- **Harness:** `scripts/probe_reviews.py` — committed under this PR.
- **Slug mapping:** `research/.slug-map-cox64.local.csv` — gitignored
  under `research/*.local.*`. The sampling procedure (deterministic
  alphabetical-first-N from the 209-site v0.4 corpus, filtered by
  category label) is reproducible without the slug file.
- **Raw evidence (Slice B):** `research/2026-04-23-reviews-probe-raw.jsonl`
  — appended by the harness; sanitized (slugs only, no hostnames).
- **Credentials:** operator-provided env vars, never committed.

## References

- Issue: [#116](https://github.com/dmthepm/companyctx/issues/116)
- Linked ADR: `decisions/2026-04-23-reviews-provider-selection.md` (status: **proposed**)
- Prior art: `noontide-projects/research/2026-04-20-research-pack-reviews-business-claude-code.md` (private)
- Partner posture: `new-signal-studio/logs/d100-run-*.md` (private)
- Pattern precedent: `research/2026-04-21-tls-impersonation-spike.md`
