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

Across thirteen candidate methods surveyed desktop-only (no live probe yet), the **five finalists that go forward into the Slice B live probe** are **Google Places API (New) Enterprise SKU** (first-party baseline), **Apify `compass/crawler-google-places`** (scraper-actor category, probe measures effective cost including residential-proxy surcharge), **WebSearch + LLM parsing** (the agentic alternative — the outcome if this wins is "remove `reviews_google_places` entirely and document the pattern in `examples/`"), **DataForSEO Google Reviews API** (aggregator-family, claimed ~$0.00075/10 reviews pending 2026-pricing verification), and **Yelp Fusion Plus** (first-party US-only backup, free during 30-day trial, first-to-drop if Slice B budget tightens); SerpAPI is eliminated pre-probe on active Google DMCA litigation (Dec 2025), Google Places Essentials/Pro are eliminated because the fields we need (`rating`, `userRatingCount`) are in the Enterprise tier, Outscraper is eliminated as it wraps the same scraped-Google data as Apify without adding control, BrightData is eliminated on setup friction, and direct Yelp scraping is eliminated on ToS posture.

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

Thirteen method categories, scored on the axes named in the issue (cost,
coverage, data shape, ToS, maintenance). The original eight categories
in the issue body have been expanded twice during thread review: the
**WebSearch + LLM parsing** agentic alternative was added per Devon's
2026-04-23 comment ("is Claude somehow finding reviews and counts just
with web..."), and **DataForSEO Google Reviews API** was added per the
cross-issue prompt from the COX-63 parallel audit. Both are load-bearing
additions — one reframes the decision ("do we need a provider at all?"),
the other adds a materially cheaper aggregator candidate that slots
cleanly between scraper-family and first-party. Scores are desktop-only
signals; probe numbers replace them in Slice B.

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
| 11 | **DataForSEO Google Reviews API** | Aggregator API | ~$0.00075 / 10 reviews ≈ sub-0.1¢/site at typical SMB review counts (claim from cross-issue Grok audit; **requires 2026-pricing verification in Slice B**) | Yes (rating + review_count + review text) | Aggregator; no active litigation on file (distinct from SerpAPI); relies on scraped data but at one abstraction layer further than direct Apify | Active enterprise, pay-as-you-go | **Finalist — probe slot #5**. Surfaced from the COX-63 parallel audit comment; claimed 10–60× cheaper than Legacy Google Places if pricing holds. |
| 12 | **Direct Yelp page scraping** | Homebrew | ~0¢ (proxy costs) | Yes | **Yelp ToS explicitly prohibits** | N/A | **Eliminated** — named for completeness only; would never ship |
| 13 | **WebSearch + LLM parsing** (agentic) | Agent-tool pattern (no dedicated provider) | ~$0.01–0.02/query (Claude/Anthropic search-tool pricing) + agent parse tokens | Yes (rating + review_count reliably from SERP cards; snippets sometimes; categories inconsistently) | Clean — it's an agent using its own tool surface, not scraping Google directly | N/A (no provider module to maintain) | **Finalist — probe slot #4**. The most consequential candidate: if this wins on the partner corpus, the outcome is "remove `reviews_google_places` entirely and document the agentic pattern" (ADR Outcome E). |

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

Five slots × 10 sites = 50 cells. Budget estimate: ~$1.50 total (well
inside the $5–15 envelope), making room for all five without forcing a
triage.

**Slot #1: Google Places API (New) Enterprise.** First-party,
authoritative rating, migration target for our legacy integration (which
Google has flagged as non-enablable for new projects since 2025-03-01).
Even if we decide to switch the default, the Enterprise SKU becomes the
ToS-clean escape hatch. Must be measured.

**Slot #2: Apify `compass/crawler-google-places`.** The scraper-actor
category the issue specifically asks about. Most-used Google Maps actor
on Apify (`compass/` prefix is Apify's most-maintained third-party
namespace). Headline price ~$2.10/1k looks like a 20× savings over
Google Enterprise, but the probe must measure **effective cost with
residential proxies** (the Feb-2026 limited-view rollout broke most
legacy scrapers and survivors need residential-proxy rotation). If the
effective cost lands above ~2¢/call the advantage evaporates. Must be
measured.

**Slot #3: WebSearch + LLM parsing.** The agentic alternative surfaced
by Devon's 2026-04-23 skeptical push: *"is Claude somehow finding
reviews and counts just with web..."* The partner's pipeline already
drives Claude through research passes; if a single WebSearch turn on
`"<business name> <city> reviews"` reliably surfaces Google's structured
SERP result card (which typically contains rating + user_ratings_total
inline) for 85%+ of the partner corpus, then `reviews_google_places` at
5.4¢/site is paying for determinism the downstream pipeline may not
need. This is the **most consequential slot** — it's the one where
"win" means "remove the provider entirely, document the pattern, ship
v0.5 with one fewer dependency to maintain." Must be measured.

**Slot #4: DataForSEO Google Reviews API.** The aggregator-family
candidate added per the COX-63 audit comment. Claimed ~$0.00075/10
reviews — if the April-2026 pricing still holds, effective cost on a
typical SMB (10–50 reviews per business) is sub-0.1¢/site, which would
make it the cheapest non-agentic option by an order of magnitude. Sits
between first-party (Google, Yelp) and scraper-direct (Apify) on both
the cost axis and the ToS axis: aggregation at one abstraction layer
further from Google's terms-of-service frontline than Apify, with no
active-litigation signal on file. Slice B's first task on this slot is
to **verify the pricing claim** against DataForSEO's current pricing
page before burning any probe cells on it. Must be measured.

**Slot #5: Yelp Fusion Plus.** First-party, US-only (matches partner
corpus — medical-aesthetic and home-services are US-heavy), 500
calls/day cap is above the partner's 100/day volume so the 30-day trial
is effectively free, $9.99/1k thereafter is cheaper than Google New
Enterprise. Honest coverage gap: businesses not listed on Yelp at all
(more common in home-services than aesthetic). **First-to-drop if Slice
B budget or wall-clock tightens** — the partner's own pipeline already
runs Yelp as an out-of-band fallback, so the question "does Yelp cover
where Google doesn't?" is partially answered by new-signal-studio's
operational record already. Must be measured if budget allows.

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

Provider credentials live in the operator's local env (`GOOGLE_PLACES_NEW_API_KEY`,
`YELP_FUSION_API_KEY`, `APIFY_TOKEN`, `DATAFORSEO_LOGIN` + `DATAFORSEO_PASSWORD`)
and are never committed. The harness is provider-agnostic: adding a new
provider is one adapter class.

### WebSearch + LLM parsing: agentic-probe protocol

Slot #3 is structurally different from the other four slots — it is an
agent-tool pattern, not a billable third-party API. The probe harness
cannot "just call" WebSearch+parse the way it calls a REST endpoint;
the call surface is Claude's own tool use, driven by a prompt.

The operator runs the agentic probe out-of-band, producing JSONL rows
that match the shared schema above. Protocol:

1. For each slug, the operator opens a fresh Claude Code session (or
   programmatic API call to `claude-opus-4-7` with WebSearch tool
   enabled) and runs a pre-registered prompt template of the shape:
   ```
   Find the Google rating and review count for "<business name> <city>".
   Use WebSearch. Return exactly a JSON object with keys rating (float
   or null), review_count (int or null), source (string identifying
   where the number came from: SERP-card | yelp-SERP | facebook-SERP |
   other | not-found). Do not invent numbers.
   ```
2. The operator records the session's `input_tokens`, `output_tokens`,
   `tool_use.web_search.queries`, and the returned JSON. Billed cost is
   computed from the token counts × the model's price plus the
   WebSearch tool's per-query cost.
3. Latency is the wall-clock time from prompt-submit to final
   assistant turn (the session, not any single tool call).
4. The JSON is appended to the probe-raw JSONL with
   `provider: "websearch_llm_parse"`.

Determinism caveat: the agentic slot runs once per slug, not N-repeats.
LLM outputs vary; the probe captures a single trial, not a distribution.
If the WebSearch+parse slot is the eventual winner, the Slice B ADR
must document this sampling caveat and an implementation ticket must
specify how downstream agentic consumers handle variance (temperature
pin, few-shot examples, retry-on-nonconforming-JSON — all downstream
concerns, out of scope for the measurement).

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

## Cross-reference: external LLM research passes

Devon ran the same COX-64 prompt through two external LLMs in parallel
with this Claude pass: **Grok** (two passes, Pass 2 supersedes Pass 1)
and **Gemini** (single long-form pass with Works Cited). All three
external drafts are preserved verbatim in the private research archive
outside this repo. This section reconciles them against the decisions
above. Keeping this reconciliation in the research doc rather than in a
scratch note is deliberate: three LLMs landed on meaningfully different
recommendations for the same prompt, and the diff is itself evidence
about the reliability of single-pass LLM research — directly relevant
to the kind of confidence the downstream partner should place in any
one of them.

### Convergences (all three external lines agree with this doc)

- **The cost delta is real.** Grok puts it at ~10–20× between
  first-party (Google Enterprise) and scraper-family (Apify /
  Outscraper); Gemini puts it at ~28× specifically for Google Enterprise
  → Apify compass. This doc's math (~20× at partner volume after the
  Google SKU free caps are factored in) agrees with the order of
  magnitude.
- **Apify `compass/crawler-google-places` is a legitimate scraper-
  family finalist.** All three external passes name it explicitly.
  Gemini independently cites its stats — **24,000+ monthly active
  users, 4.7/5 rating across 1,200+ reviews, 1.6-day average issue
  response time** — which is a stronger maintenance signal than this
  doc previously captured from the Apify MCP search (which returned a
  different `compass/` actor). Stats taken; the `compass/crawler-
  google-places` slot is reinforced, not replaced.
- **ProviderBase pluggability is architecturally free.** All three
  agree that adding or swapping a reviews provider is a provider entry-
  point change, not a schema or core-loop change. The disagreement is
  **whether** to use pluggability, not **whether we could**.
- **Outscraper introduces async/webhook integration friction.** Gemini
  documents this most concretely — the 1-to-3-minute async task model
  requires either polling or webhook refactoring, both of which are
  non-trivial engineering against a linear pipeline. This reinforces
  this doc's elimination of Outscraper pre-probe; it's not just that it
  wraps scraped Google data, it's also that adopting it requires a
  pipeline-shape change the partner has not asked for.
- **Yelp Fusion is pricing-hostile.** Gemini cites a **$229/month base
  minimum** in addition to the per-1k rate — significantly harsher than
  this doc's first draft, which treated Yelp Fusion Plus as "free
  during trial then $9.99/1k." Taken; Yelp Fusion's post-trial economics
  are worse than this doc stated.
- **Gemini independently confirms the Enterprise-SKU-for-rating
  mapping.** Gemini Works-Cited [15] quotes Google's docs directly:
  *"requesting the rating or userRatingCount fields automatically
  triggers the Place Details Enterprise SKU."* This validates this
  doc's finding that Grok's "Essentials + field mask" plan does not
  return the fields we need. Two of three external passes now converge
  on the correct SKU mapping.

### Where this doc holds its line against all external passes

1. **Google SKU field-tier mapping.** Both Grok passes collapsed the
   Essentials / Pro / Enterprise distinction and proposed "Essentials +
   field mask" as the cost-optimized Google path. Gemini gets this
   right. This doc's Enterprise-tier probe slot is correct; Grok's
   "Essentials-stays-free" framing is not. Worth flagging that
   single-pass desktop research can collapse authoritative-doc
   distinctions in ways that make the downstream recommendation
   silently wrong — this is why the probe is load-bearing.
2. **SerpAPI.** Grok Pass 2 lists SerpApi Google Maps as viable without
   mention of Google's Dec-2025 DMCA suit. Gemini does not discuss
   SerpAPI at all (narrower shortlist, didn't include it). This doc
   eliminates SerpAPI pre-probe on the active-litigation risk. The miss
   in Grok's pass is an example of why adversarial critique is a
   distinct step from desktop survey.
3. **ToS weighting.** Grok Pass 2 frames scraper-ToS risk as
   "overblown"; Gemini's framing is more careful — cites the
   hiQ-Labs-v-LinkedIn / CFAA jurisprudence correctly, notes that
   *contract-breach claims persist even when CFAA does not apply*, and
   specifically documents Google Maps Platform's **30-day caching
   restriction**. This doc's 3× ToS weighting stands; Gemini's detail
   sharpens rather than undercuts it.
4. **Recommendation shape.** Grok Pass 2 recommends pluggable-default-
   to-Outscraper; Gemini recommends a **Factory Pattern with
   `REVIEWS_PROVIDER` env toggle**. Two external passes, two votes for
   pluggable. This doc (and the linked ADR) holds its rejection of
   pluggable-as-default per the adversarial critique already on record:
   pluggability is maintenance debt dressed as flexibility (doubled
   fixture sets, doubled CI-matrix cells, doubled ToS surfaces), and it
   forces the partner to pick when the partner's actual need is "rating
   + count shows up." The 2-vs-1 external weight is noted but the
   adversarial critique's argument is about architecture cost, not about
   vote-counting — and the probe numbers + the pre-registered decision
   rule, not external-LLM consensus, pick the outcome.
5. **Grok Pass 2's "provider never implemented" claim.** Wrong — the
   provider ships in v0.3.0, 533 lines on `main`. Grok Pass 1 had it
   right; Pass 2 regressed. Flagged as a concrete example of narrative-
   research hallucination.
6. **Gemini's "Empirical Evaluation Framework and Probe Execution"
   section is fabricated.** This is the most important single finding
   from this synthesis. Gemini's document includes a section that
   presents itself as having *run the 10-site probe* and produces
   specific numbers in a measurement-like table:

   > | Metric | Google Places (Enterprise) | Apify (compass) | Outscraper API |
   > | Billed Cost (per 10 sites) | $0.58 | $0.021 | $0.03 |
   > | Coverage Rate | 100% (10/10) | 100% (10/10) | 100% (10/10) |
   > | Data Consistency | Baseline Control | 100% Match (Rating) | 100% Match (Rating) |

   Gemini did not run this probe. No API keys were provisioned, no
   slugs were tested, no billed costs were observed. The numbers are
   extrapolations from desktop pricing pages presented in a table shape
   that looks like measurement. This is the **exact failure mode the
   repo rule "never name a vendor in public docs before measurement"
   exists to prevent**. If we had accepted Gemini's recommendation
   ("switch to Apify compass as primary") on the strength of that
   table, we would have been shipping a vendor change backed by
   fabricated measurement. The header of this doc's methodology section
   reads "10 sites is a cost-and-fit sanity check, not a coverage
   benchmark" precisely to keep even our own future-selves honest about
   what n=10 measurement can and can't support — Gemini's pass presents
   n=10 *extrapolation* as if it were that benchmark, and it isn't.

   The Gemini pass is cited here *because* it got this wrong in an
   instructive way, not to dismiss it. The rest of Gemini's research
   (Enterprise-SKU mapping, Apify stats, Yelp base minimum, ToS detail)
   is genuinely useful. The fabricated-probe section is the single
   sharpest argument for why this ticket had to be split into Slice A
   (research + harness, deferred probe) and Slice B (actual probe with
   real keys + real billed cost): shipping one of those external
   passes as the ADR directly would have meant shipping a recommendation
   backed by a table of invented numbers.

### Additions taken from the external passes

- **Foursquare Places API** added to the matrix above as an evaluated
  alternative (deferred, not a Slice B finalist — Grok Pass 2 surfaced
  this).
- **30-day cache TTL** promoted to a cross-cutting optimization note,
  below. Grok surfaced the idea; **Gemini's Google Maps Platform ToS
  citation sharpens the constraint**: Google permits temporary caching
  of Places data for up to 30 consecutive calendar days; persistent
  local stores past that window violate the ToS. This happens to be
  exactly the TTL Grok proposed, which lands the cache proposal on the
  right side of the ToS line by coincidence. This doc's Vertical Memory
  cache (SQLite) can apply this TTL directly; Slice B keeps the cache
  disabled so per-call cost is measured honestly.
- **2026 SKU free-tier caps** (Essentials 10k/mo free, Pro 5k/mo free)
  — at partner 3k/mo volume, Text Search Pro stays inside the 5k/mo
  free cap so the effective Google cost is only the Enterprise Place
  Details leg.
- **Apify `compass/crawler-google-places` usage stats** — 24,000+ MAU,
  4.7/5 rating, 1.6-day average issue response (per Gemini citation [9]).
  Stronger maintenance signal than the first draft of this doc cited;
  reinforces the Slot #2 choice.
- **Yelp Fusion $229/month base minimum** — Gemini citation [27].
  Post-trial economics are worse than this doc initially stated;
  captured in the matrix note.
- **hiQ Labs v. LinkedIn + CFAA jurisprudence framing** — Gemini
  citations [38–40]. Not taken into the doc verbatim (legal-framework
  summaries age poorly and the doc doesn't need to relitigate Ninth
  Circuit caselaw), but captured in the archive for the implementation
  follow-up issue.

### What none of the external passes covered

- **WebSearch + LLM parsing as a candidate.** None of Grok-1, Grok-2,
  or Gemini surfaced the agentic alternative. That candidate came from
  Devon's skeptical question on the issue thread — not a desktop-
  research category any of the LLMs spontaneously considered. This is
  itself a signal: the alternatives external LLMs generate are the
  alternatives that *look like the incumbent* (more structured APIs).
  The most consequential candidate in this survey was surfaced by a
  human who stepped outside the "what replaces the API?" frame. Noted
  for the process record.
- **DataForSEO Google Reviews API.** Surfaced cross-issue from the
  COX-63 audit; none of the three external passes named this one
  independently.
- **Google Places Legacy's non-enablable-since-2025-03-01 status.**
  None of the three passes flagged this. It is the single largest
  migration-force acting on this decision independent of cost, and
  pure desktop survey missed it. This doc catches it in Context #1 of
  the ADR.

### Foursquare — deferred alternative

| Method | Cost/call (est.) | Fields | ToS | Notes |
|---|---|---|---|---|
| **Foursquare Places API** (Pro tier) | ~1.5¢; 10k/mo free | `rating` (0–10 scale), `tips` count, categories | First-party; clean | Different reviewer pool than Google — ratings do not compare 1:1. Useful as a diversity source or review-coverage backfill, not as a cost-replacement for a Google-agreement comparison. Skipped from Slice B probe to preserve the $15 envelope. Reopen if Slice B lands in Outcome D and we widen the shortlist. |

### Cross-cutting: caching strategy

Independent of the provider winner, the v0.3 Vertical Memory SQLite cache
(`docs/ARCHITECTURE.md`) is already provider-agnostic. Reviews change
slowly enough that a 30-day TTL on `reviews_*` entries would let the
partner's steady-state request mix hit cache on most repeat sites and pay
the provider cost only on net-new prospects. Cache-enabled effective
cost at 3k/mo new-prospect volume with ~20% repeat rate is roughly 80%
of the provider's nominal cost. Grok Pass 2 raised this as a major
cost-reduction lever and the point stands regardless of which finalist
wins the Slice B probe. Tracked as a separate optimization, not as a
Slice B acceptance criterion — caching under-counts the measured
per-call cost we need to compare providers on, so the Slice B probe
runs with caching disabled. The cache becomes an additional value layer
on top of whichever provider ships.

## References

- Issue: [#116](https://github.com/dmthepm/companyctx/issues/116)
- Linked ADR: `decisions/2026-04-23-reviews-provider-selection.md` (status: **proposed**)
- Prior art: `noontide-projects/research/2026-04-20-research-pack-reviews-business-claude-code.md` (private)
- External LLM parallel passes: Grok (passes 1 + 2) and Gemini (single long-form pass), all preserved verbatim in the private research archive outside this repo. Paths deliberately omitted to honor the "never create companyctx imports or paths to noontide-projects" rule. Cross-reference + critique in the "Cross-reference: external LLM research passes" section above.
- Partner posture: `new-signal-studio/logs/d100-run-*.md` (private)
- Pattern precedent: `research/2026-04-21-tls-impersonation-spike.md`
