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

Across thirteen candidate methods surveyed desktop-only (no live probe yet), the **five finalists that go forward into the Slice B live probe** are **Google Places API (New) Enterprise SKU** (first-party baseline with strict Enterprise-only field mask to avoid the Atmosphere tier), **Apify `compass/crawler-google-places`** (scraper-actor category, probe measures effective cost including residential-proxy surcharge), **WebSearch + LLM parsing** (the agentic alternative — if this wins the outcome is "remove `reviews_google_places` entirely and document the pattern in `examples/`"), **DataForSEO Google Reviews API** (aggregator-family, claimed ~$0.00075/10 reviews pending 2026-pricing verification), and **Yelp Fusion Plus** (first-party US-only backup, free during 30-day trial, first-to-drop if Slice B budget tightens); SerpAPI is eliminated pre-probe on active Google DMCA litigation (Dec 2025), Google Places Essentials/Pro are eliminated because the fields we need (`rating`, `userRatingCount`) are in the Enterprise tier, Outscraper is eliminated as it wraps the same scraped-Google data as Apify without adding control, BrightData is eliminated on setup friction, and direct Yelp scraping is eliminated on ToS posture.

## Scope

This document resolves **Slice A** of [issue #116](https://github.com/dmthepm/companyctx/issues/116):

1. Enumerate and score the candidate reviews-extraction methods.
2. Nominate the finalists for a live 10-site probe.
3. Document the probe methodology, site mix, and decision rule so Slice B is a one-command execution.

**Slice B — deferred pending key + budget provisioning**: run the probe
(50 cells, $5–15 spend across five finalists × 10 sites), promote the ADR
from `proposed` → `accepted`, open the implementation issue if the
recommendation is to switch/compose.

## Why this wasn't done in v0.3

The v0.3 release shipped `reviews_google_places` (Google Places Legacy
Place Details) as the reviews provider without a head-to-head probe.
The issue body frames that as "chosen by assumption, not evidence." An
informal desktop landscape review did happen earlier, but what was
missing is a **measured, same-corpus comparison**. The TLS-impersonation
spike (#21 / `research/2026-04-21-tls-impersonation-spike.md`) is the
pattern this work mirrors: pick candidates, run all of them against the
same sample, decide on numbers. This doc puts that pattern in place for
reviews.

## Consumer-shape constraint

The reviews category populates two fields on the output envelope:
`rating` and `review_count`. Typical downstream consumption of this
category is "rating + count as a social-proof signal"; review text,
snippets, categories, hours, and photos are not in the current
`ReviewsSignals` shape. This constrains the probe:

- **Richness is not a load-bearing axis.** A provider that returns only
  rating + count is not penalized vs. one returning full reviews.
  Weighted at 1× in the decision matrix below.
- **Google Places SKU selection follows from this.** The `rating` /
  `userRatingCount` / `websiteUri` fields live in the Enterprise tier
  of Google Places API (New). Full review text and review-summary
  fields would trigger the pricier Atmosphere tier ($25/1k vs. $20/1k
  Enterprise), and we do not need them. Outcome A in the companion ADR
  encodes this as a hard field-mask constraint.

## Candidate matrix (desktop)

Thirteen method categories surveyed. The original eight from the issue
body have been expanded twice during thread review: **WebSearch + LLM
parsing** (agentic alternative added mid-thread per scope-expansion
comment) and **DataForSEO Google Reviews API** (added from a
cross-issue prompt in the COX-63 parallel audit). Both are load-bearing
additions — one reframes the decision as "do we need a provider at
all?", the other adds a materially cheaper aggregator candidate.
Scores are desktop-only signals; probe numbers replace them in Slice B.

| # | Method | Type | Cost/call (estimate) | Rating+count returned? | ToS posture | Maintenance signal | Status |
|---|---|---|---|---|---|---|---|
| 1 | **Google Places Legacy** (current) | First-party API | ~5.4¢ (Text Search 3.2¢ + Details Atmosphere 2.2¢) | Yes | Clean (first-party) | **Legacy** — cannot be enabled for new GCP projects since 2025-03-01 | Probe as current baseline, but **migration-required regardless** |
| 2 | **Google Places API (New) Essentials** | First-party API | ~$2/1k (0.2¢) | **No** — `rating`/`userRatingCount` are in Enterprise tier, not Essentials | Clean | Active | **Eliminated pre-probe** — missing required fields |
| 3 | **Google Places API (New) Pro** | First-party API | ~$17/1k (1.7¢) — field mask | Partial — `displayName`, `primaryType`; **not** `rating` | Clean | Active | **Eliminated pre-probe** — missing required fields |
| 4 | **Google Places API (New) Enterprise** (rating/count/website field mask) | First-party API | **Text Search Enterprise $35/1k + Place Details Enterprise $20/1k = $55/1k ≈ 5.5¢/site**; 1k/mo free on each SKU. At 3k/mo volume: ~$110/mo after free caps. | **Yes** — `rating`, `userRatingCount`, `websiteUri`, phone (Enterprise tier only; **do NOT request `reviews` or `reviewSummary` — those trigger the pricier Atmosphere tier at $25/1k**) | Clean | Active | **Finalist — probe slot #1** |
| 5 | **Apify `compass/crawler-google-places`** (and peers) | Scraper actor | ~$2.10/1k nominal; +2-4¢ residential proxy after Feb-2026 lockdown | Yes (`reviewsCount`, `totalScore`) | Gray (Google ToS redistribution risk) | Active, multi-maintainer; tens-of-thousands of monthly users; breakage wave in Feb-2026 | **Finalist — probe slot #2** |
| 6 | **Apify Yelp actors** (`tri_angle/yelp-scraper` etc.) | Scraper actor | ~$1/1k biz + $1 start (91.3% success) | Yes | Gray (Yelp ToS prohibits scraping) | Active, variable success | Evaluated; not finalist (duplicates Yelp Fusion's signal at worse ToS) |
| 7 | **Outscraper Google Maps API** | Scraper-wrapper API | ~$1–3/1k | Yes | Gray (inherits scraper ToS + redistribution issue) | Aggregator, opaque source-chain | **Eliminated pre-probe** — wraps the same scraped data as Apify without adding ToS protection or control |
| 8 | **Yelp Fusion Plus** | First-party API | ~$9.99/1k = 1¢/call; 30-day free trial; 500 calls/day cap; third-party reporting suggests a monthly base commitment on top of per-call rate | Yes (rating, review_count, 3 excerpts) | **Clean (first-party)** | Active; Jul-2024 pricing change controversy subsided | **Finalist — probe slot #5** (first-to-drop if budget tightens) |
| 9 | **BrightData Web Scraper IDE** (Yelp/Google) | Enterprise scraping | Custom + proxy usage | Yes (configurable) | Gray | Active but enterprise | **Eliminated pre-probe** — setup friction incompatible with pipx-CLI user |
| 10 | **SerpAPI Google Maps** | SERP wrapper | ~1.5¢/call effective | Yes | **Active Google DMCA lawsuit filed Dec-2025** (motion-to-dismiss hearing 2026-05-19) | Active but legally contested | **Eliminated pre-probe** — naming SerpAPI in a public OSS ADR during live Google litigation is a ship-and-regret risk. Reconsider post-ruling. |
| 11 | **DataForSEO Google Reviews API** | Aggregator API | ~$0.00075 / 10 reviews ≈ sub-0.1¢/site at typical SMB review counts (**requires 2026-pricing verification in Slice B**) | Yes (rating + review_count + review text) | Aggregator; no active litigation on file (distinct from SerpAPI); relies on scraped data but at one abstraction layer further than direct Apify | Active enterprise, pay-as-you-go | **Finalist — probe slot #4**. Claimed 10–60× cheaper than Legacy Google Places if pricing holds. |
| 12 | **Direct Yelp page scraping** | Homebrew | ~0¢ (proxy costs) | Yes | **Yelp ToS explicitly prohibits** | N/A | **Eliminated** — named for completeness only; would never ship |
| 13 | **WebSearch + LLM parsing** (agentic) | Agent-tool pattern (no dedicated provider) | ~$0.01–0.02/query (agent search-tool pricing) + agent parse tokens | Yes (rating + review_count reliably from SERP cards; snippets sometimes; categories inconsistently) | Clean — it's an agent using its own tool surface, not scraping Google directly | N/A (no provider module to maintain) | **Finalist — probe slot #3**. The most consequential candidate: if this wins, the outcome is "remove `reviews_google_places` entirely and document the agentic pattern" (ADR Outcome E). |

### Eliminations, reasoned

- **Google Places (New) Essentials / Pro.** Google's New API tier
  system puts `rating` and `userRatingCount` in the **Enterprise**
  Place Details SKU. Essentials returns address/location/types only;
  Pro adds display-name/phone but still not the rating. Our required
  fields force Enterprise. The "downgrade to Essentials" outcome the
  issue listed is architecturally impossible for our use case.
- **SerpAPI.** Google sued SerpAPI in Dec-2025 under the DMCA alleging
  SearchGuard bypass; motion-to-dismiss hearing set for 2026-05-19.
  For a public OSS project to name SerpAPI as an `accepted` reviews
  provider during active litigation is a reputational and
  legal-exposure risk disproportionate to the ~0.8¢/call potential
  savings. Revisit post-ruling; not during this ADR cycle.
- **Outscraper.** Wraps scraped Google Maps data. Inherits the same
  Feb-2026 limited-view fragility as Apify actors and the same
  Google-ToS redistribution gray zone, without giving us either lower
  cost than Apify direct or ToS clarity over Apify direct. Adds a
  candidate to the probe without buying any axis we don't already
  have covered. Also introduces async/webhook integration friction
  (1–3 minute task completion) that would force a non-trivial
  refactor of linear synchronous pipelines. Eliminated.
- **BrightData.** Enterprise Web Scraper IDE requires BrightData
  account setup, proxy-unit management, and custom scraper
  development. Setup friction for a `pipx install companyctx` user is
  too high for a default-path provider. If we ever need it, it slots
  into the `SmartProxyProvider` Attempt-2 layer, not the reviews slot.

### Finalists — probe slot justification

Five slots × 10 sites = 50 cells. Pre-flight spend estimate: ~$1.50
total (well inside the $5–15 envelope), making room for all five
without forcing triage.

**Slot #1: Google Places API (New) Enterprise.** First-party,
authoritative rating, migration target for the legacy integration
(Google no longer lets new projects enable Places Legacy, since
2025-03-01). Even if we decide to switch the default, the Enterprise
SKU becomes the ToS-clean escape hatch. Field mask is locked to
`id,displayName,rating,userRatingCount,websiteUri` to stay off the
pricier Atmosphere tier. Must be measured.

**Slot #2: Apify `compass/crawler-google-places`.** The scraper-actor
category the issue specifically asks about. Highest usage in the Apify
Google Maps namespace (`compass/` is Apify's most-maintained
third-party namespace; tens of thousands of monthly active users;
4.7/5 rating across 1,200+ reviews per the public actor page).
Headline price ~$2.10/1k looks like a 20× savings over Google
Enterprise, but the probe must measure **effective cost with
residential proxies** (the Feb-2026 limited-view rollout broke most
legacy scrapers and survivors need residential-proxy rotation). If
effective cost lands above ~2¢/call the advantage evaporates. Must be
measured.

**Slot #3: WebSearch + LLM parsing.** The agentic alternative. If a
single WebSearch turn on `"<business name> <city> reviews"` reliably
surfaces Google's structured SERP result card (which typically
contains rating + user_ratings_total inline) for 85%+ of a
representative test corpus, then `reviews_google_places` at 5.4¢/site
is paying for determinism the downstream pipeline may not need. This
is the **most consequential slot** — it's the one where "win" means
"remove the provider entirely, document the pattern, ship v0.5 with
one fewer dependency to maintain." Must be measured.

**Slot #4: DataForSEO Google Reviews API.** Aggregator-family;
claimed ~$0.00075/10 reviews ≈ sub-0.1¢/site. Sits between first-party
(Google, Yelp) and scraper-direct (Apify) on both cost and ToS axes.
Slice B's first task on this slot is to verify the pricing claim
against DataForSEO's current pricing page before burning probe cells
on a stale number. Must be measured.

**Slot #5: Yelp Fusion Plus.** First-party, US-only, 500 calls/day
cap; 30-day trial is effectively free for a ten-site probe. First-to-
drop if Slice B budget or wall-clock tightens, because multi-source
fallback patterns (Yelp as a backup to Google) are already common in
downstream pipelines and the question "does Yelp cover where Google
doesn't?" is partially answered by operational record already.

(Apify also has cheaper newer actors — e.g.
`kaix/google-maps-places-scraper` at ~$0.10/1k nominal — but they have
far lower monthly-user counts than the compass actor. Using the
higher-usage `compass/` actor gives the probe a signal about
actor-stability, which is the load-bearing question for the whole
scraper-actor category. If `compass/` fails, no other actor is likely
to succeed under the same Google-side pressure.)

## Probe methodology (for Slice B)

### Probe-set design

**10 slugs**, sanitized, distributed across categories that stress
different edges of the providers' resolution behavior:

| Slot | Category | Rationale |
|---|---|---|
| 1-4 | Small local business with clear physical address (medical/aesthetic class) | Highest Google Places coverage expected — baseline |
| 5-7 | Service-Area Businesses without public storefronts (home-services class) | Lower Google Places coverage; stresses coverage axis |
| 8-9 | Social-only businesses (Facebook / Instagram, no dedicated TLD) | Edge case — tests ZERO_RESULTS handling |
| 10 | Deliberately obscure low-visibility entity | Coverage-gap stress test |

Slugs sampled deterministically from a historical test corpus of the
tool's target-class domains. The slug → real-URL mapping lives in
`research/.slug-map-cox64.local.csv` (gitignored under
`research/*.local.*`); the committed probe artifacts reference slugs
only.

### Measurement harness

A Python CLI, `scripts/probe_reviews.py` (committed under this PR),
takes the slug list and a provider set, runs one call per (slug,
provider) cell, and appends a row to
`research/2026-04-23-reviews-probe-raw.jsonl` per cell. Row shape:

```json
{
  "slug": "med-aesth-01",
  "provider": "google_places_new_enterprise | apify_compass_crawler | websearch_llm_parse | dataforseo_reviews | yelp_fusion_plus",
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

Provider credentials live in the operator's local env
(`GOOGLE_PLACES_NEW_API_KEY`, `YELP_FUSION_API_KEY`, `APIFY_TOKEN`,
`DATAFORSEO_LOGIN` + `DATAFORSEO_PASSWORD`) and are never committed.
The harness is provider-agnostic: adding a new provider is one adapter
class.

### WebSearch + LLM parsing: agentic-probe protocol

Slot #3 is structurally different from the other four — it is an
agent-tool pattern, not a billable third-party API. The probe harness
cannot "just call" WebSearch+parse the way it calls a REST endpoint;
the call surface is an agent's own tool use, driven by a prompt.

The operator runs the agentic probe out-of-band, producing JSONL rows
that match the shared schema above. Protocol:

1. For each slug, open a fresh agent session (or programmatic API
   call to the model with a web-search tool enabled) and run a
   pre-registered prompt template of the shape:

   ```
   Find the Google rating and review count for "<business name> <city>".
   Use WebSearch. Return exactly a JSON object with keys rating (float
   or null), review_count (int or null), source (string identifying
   where the number came from: SERP-card | yelp-SERP | facebook-SERP |
   other | not-found). Do not invent numbers.
   ```

2. Record the session's `input_tokens`, `output_tokens`,
   `tool_use.web_search.queries`, and the returned JSON. Billed cost
   is computed from token counts × model price plus the WebSearch
   tool's per-query cost.
3. Latency is the wall-clock time from prompt-submit to final
   assistant turn (the session, not any single tool call).
4. The JSON is appended to the probe-raw JSONL with
   `provider: "websearch_llm_parse"`.

Determinism caveat: the agentic slot runs once per slug, not N-repeats.
LLM outputs vary; the probe captures a single trial, not a
distribution. If the WebSearch+parse slot is the eventual winner, the
Slice B ADR must document this sampling caveat and an implementation
ticket must specify how downstream agentic consumers handle variance
(temperature pin, few-shot examples, retry-on-nonconforming-JSON —
all downstream concerns, out of scope for the measurement).

### Site mix: why 10 and not 100

Per the measurement culture already in the repo (see the 20-site TLS
spike that sized #21), **10 sites is a cost-and-fit sanity check, not
a coverage benchmark**. At n=10, a single ZERO_RESULTS swings coverage
by 10 percentage points. We cannot tell 85% from 95% at this n. What
we **can** tell:

- Which providers return `rating+count` at all vs. ZERO_RESULTS on a
  representative slice.
- The **effective billed cost per successful call** (nominal + proxy
  + actor-start overheads).
- Whether ratings **agree within ±0.3 stars** across providers for
  the same business (divergence = data-quality signal).
- Which providers return results for the social-only edge cases.

If two providers disagree hard at n=10, we expand to n=30 or drop the
divergent one; that's a Slice B branch, not a Slice A commitment.

### Decision rule (pre-committed)

The recommendation after the probe follows this rule, pre-registered
before measurement to avoid motivated interpretation. Order matters —
the first matching branch wins, which prioritizes the provider-removal
outcome when it is supportable over keeping an expensive dedicated
provider:

```
effective_cost_per_successful_call(p) =
    (nominal_cost_cents(p) + proxy_cost_cents(p) + actor_start_cents(p)
     + agent_token_cents(p))
    / coverage_rate(p)

Recommend REMOVE provider entirely (agentic pattern) if:
    coverage(websearch_llm_parse) ≥ 0.85
    AND effective_cost(websearch_llm_parse) ≤ 1.5¢/site
    AND data consistency vs Google baseline within ±0.3 stars on
        co-present businesses
    AND the JSON-format compliance rate across the 10 slugs is 10/10
        (no hallucinated numbers, no malformed outputs)

Recommend SWITCH to cheapest aggregator if:
    coverage(dataforseo_reviews) ≥ 0.85
    AND effective_cost(dataforseo_reviews) ≤ 0.5 × effective_cost(google_new_enterprise)
    AND 2026-pricing verification confirms the sub-0.1¢/site claim
    AND data consistency vs Google baseline within ±0.3 stars

Recommend SWITCH to cheapest viable first-party/gold-tier alternative if:
    effective_cost(cheapest) < 0.5 × effective_cost(google_new_enterprise)
    AND coverage(cheapest) ≥ coverage(google_new_enterprise) - 0.05
    AND ToS posture is first-party or Gold-tier Apify actor

Recommend COMPOSITE (Google New Enterprise → Yelp Fusion fallback) if:
    coverage(google_new_enterprise) < 0.8
    AND coverage(google OR yelp) ≥ 0.9
    AND effective_cost(composite_expected) ≤ 1.2 × effective_cost(google_only)

Recommend KEEP Google Places (migrate Legacy → New Enterprise) if:
    effective_cost(google_new_enterprise) ≤ 1.5 × effective_cost(cheapest_other)
    AND coverage(google_new_enterprise) ≥ 0.8

Else: KEEP Legacy temporarily, reopen probe with different shortlist.
```

All five branches land in the ADR (Outcomes A–E); the probe numbers
pick which. Ordering reflects "prefer less surface area when the
numbers support it" — removing the reviews provider entirely is the
single highest-leverage outcome available to this spike, so it is
first in the rule.

## Decision matrix (pre-probe, weights only)

Weights ratify the issue spec, with one change flagged below:

| Axis | Weight | Notes |
|---|---|---|
| Effective cost per successful call | 3× | Merges "cost" + "coverage" into one axis since they combine multiplicatively |
| ToS / redistribution posture | **3×** | **Raised from issue's 2×.** Scraped-Google-Maps data embedded in downstream outputs that get redistributed externally is the most plausible real-world blow-up. First-party > Gold-Apify > Outscraper/BrightData > direct scraping. |
| Data consistency vs baseline | 2× | Ratings diverging >0.3 between providers = data-quality signal |
| Setup friction for operators | 1× | How many env vars + how much account setup |
| Data richness | 1× | Default downstream shape consumes rating+count only — lowest weight |

Coverage rate was folded into "effective cost" because a provider
that covers 80% of sites at 1¢/call is cheaper per **successful**
call (1.25¢) than one that covers 100% at 2¢ (2¢). Separating the
two axes double-counts the signal.

## Out of scope

- **Live probe execution, cost capture, ADR promotion to `accepted`.**
  Requires operator to provision Google Places (New) Enterprise key,
  Yelp Fusion Plus key, Apify token + residential-proxy allocation,
  and DataForSEO credentials. Total probe budget $5–15 per
  [issue #116 acceptance](https://github.com/dmthepm/companyctx/issues/116).
  Tracked as Slice B — see the follow-up issue linked from the PR
  description.
- **Implementation of the chosen provider(s).** A switch from Legacy
  Google Places to New Enterprise, or to a composite, is a provider
  change — a `reviews_google_places_new.py` file, new provider
  modules, updated tests, updated fixtures, updated `PROVIDERS.md`, a
  `CHANGELOG.md` entry under an unreleased v0.5 section. Out of scope
  for a research/ADR ticket; tracked as the implementation follow-up
  issue.
- **Extending beyond 10 sites.** Covered in methodology above. If the
  probe reveals ambiguity (two providers tied within 10%), we go to
  30 sites before promoting the ADR, and that's a Slice B branch.
- **Non-review providers** (social signals, categories, hours). Out
  of scope per the issue.

## Reproducibility

- **Harness:** `scripts/probe_reviews.py` — committed under this PR.
- **Slug mapping:** `research/.slug-map-cox64.local.csv` — gitignored
  under `research/*.local.*`. The sampling procedure (deterministic
  alphabetical-first-N from the tool's historical test corpus,
  filtered by category label) is reproducible without the slug file.
- **Raw evidence (Slice B):** `research/2026-04-23-reviews-probe-raw.jsonl`
  — appended by the harness; sanitized (slugs only, no hostnames).
- **Credentials:** operator-provided env vars, never committed.

## Cross-cutting: caching strategy

Independent of the provider winner, the v0.3 Vertical Memory SQLite
cache (`docs/ARCHITECTURE.md`) is already provider-agnostic. Reviews
change slowly enough that a 30-day TTL on `reviews_*` entries would
let a steady-state request mix hit cache on most repeat sites and pay
the provider cost only on net-new queries. Cache-enabled effective
cost at 3k/mo new-query volume with ~20% repeat rate is roughly 80%
of the provider's nominal cost.

A note on the 30-day TTL: Google Maps Platform's Service Specific
Terms permit temporary local caching of Places data for up to 30
consecutive calendar days before the data must be purged. The
proposed 30-day TTL lands exactly on that ToS boundary. Any longer
cache window for Google-derived data would violate those terms; if
the cache is extended for non-Google providers, it must be scoped
per-provider, not global.

The caching strategy applies regardless of which finalist wins the
Slice B probe. Tracked as a separate optimization, not as a Slice B
acceptance criterion — caching under-counts the measured per-call
cost we need to compare providers on, so the Slice B probe runs with
caching disabled. The cache becomes an additional value layer on top
of whichever provider ships.

## Foursquare — deferred alternative

| Method | Cost/call (est.) | Fields | ToS | Notes |
|---|---|---|---|---|
| **Foursquare Places API** (Pro tier) | ~1.5¢; 10k/mo free | `rating` (0–10 scale), `tips` count, categories | First-party; clean | Different reviewer pool than Google — ratings do not compare 1:1. Useful as a diversity source or review-coverage backfill, not as a cost-replacement for a Google-agreement comparison. Skipped from Slice B probe to preserve the $15 envelope. Reopen if Slice B lands in Outcome D and we widen the shortlist. |

## References

- Issue: [#116](https://github.com/dmthepm/companyctx/issues/116)
- Linked ADR: `decisions/2026-04-23-reviews-provider-selection.md` (status: **proposed**)
- Pattern precedent: `research/2026-04-21-tls-impersonation-spike.md`
- Architecture context for caching and Vertical Memory:
  `docs/ARCHITECTURE.md`
