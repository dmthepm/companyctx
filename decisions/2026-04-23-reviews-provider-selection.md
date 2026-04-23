---
type: decision
date: 2026-04-23
topic: reviews-provider selection — measurement-driven successor to v0.3's Google Places Legacy choice
status: proposed
accepted_on: null
linked_decisions:
  - decisions/2026-04-20-zero-key-stealth-strategy.md
linked_docs:
  - docs/PROVIDERS.md
  - docs/ARCHITECTURE.md
linked_research:
  - research/2026-04-23-reviews-extraction-method-survey.md
linked_issues:
  - https://github.com/dmthepm/companyctx/issues/116
---

# Reviews-provider selection

## Status

**Proposed 2026-04-23. Pending spike.**

Following the precedent set by
`decisions/2026-04-20-zero-key-stealth-strategy.md` — proposed first,
accepted only after a same-corpus measurement spike landed the numbers
— this ADR does not name a chosen vendor in its `accepted` state until
the Slice B live probe runs. The desktop survey in
`research/2026-04-23-reviews-extraction-method-survey.md` produced a
shortlist of five finalists; the 10-site probe (Slice B of issue
[#116](https://github.com/dmthepm/companyctx/issues/116)) is what flips
this ADR to `accepted` and names a specific provider or composition.

Until the probe runs, the default in `companyctx` remains
`reviews_google_places` (Legacy Place Details), exactly as shipped in
v0.3/v0.4. **This ADR does not authorize any code change.**

## Context

### The process gap this closes

`v0.3` shipped `reviews_google_places` (Legacy Google Places) as the
sole reviews provider at ~5.4¢/call. That choice was informed by an
earlier informal desktop landscape review but was **not backed by a
same-corpus head-to-head measurement against alternatives.** The
TLS-impersonation library spike (#21 /
`decisions/2026-04-20-zero-key-stealth-strategy.md`) is the pattern
the reviews slot should have followed from the start: candidates
enumerated, candidates measured on the same corpus, decision cited
back to the numbers. Issue [#116](https://github.com/dmthepm/companyctx/issues/116)
retrofits that pattern.

### Four facts that force the decision regardless of probe outcome

1. **Google Places Legacy is no longer enablable for new projects
   (since 2025-03-01).** Existing keys continue to work, but any new
   `companyctx` user trying to follow the Quickstart with a fresh GCP
   project gets stuck at "cannot enable the Places API (Legacy)."
   Migration to Places API (New) is required on time-horizon grounds
   even if the probe confirms Google is the right source.
2. **The fields we need (`rating`, `userRatingCount`) are in the
   Enterprise SKU of the New API.** Essentials and Pro tiers do not
   return them. The "downgrade to Essentials" outcome listed in the
   issue is architecturally impossible. A further refinement: `rating`
   + `userRatingCount` + `websiteUri` are in the **Enterprise** tier,
   whereas full `reviews` text and `reviewSummary` fields trigger the
   pricier **Enterprise + Atmosphere** tier. Our downstream consumers
   use rating + count only, so the correct field mask stays on
   Enterprise and avoids Atmosphere — a concrete ~$5 / 1000 request
   saving we should lock into the implementation.
3. **SerpAPI is in active Google DMCA litigation (Dec-2025; hearing
   2026-05-19).** Any ADR naming SerpAPI as `accepted` during active
   litigation is a ship-and-regret risk. SerpAPI is dropped from the
   shortlist pre-probe.
4. **The agentic alternative is on the table.** A scope-expansion
   comment on the issue thread introduced a fifth candidate (WebSearch
   + LLM parsing) that does not fit the "structured third-party
   provider" frame. If this wins on the probe, the outcome is the
   removal of `reviews_google_places` from the waterfall entirely, not
   the replacement of one provider with another. Outcome E below
   carries that branch, and it is pre-registered as the first-matching
   branch in the decision rule.

## Decision (proposed)

### Finalist shortlist for the Slice B probe

Five candidates, measured head-to-head on the same 10-site corpus. Two
slots were added after the initial three were finalized: **WebSearch +
LLM parsing** (the agentic alternative) and **DataForSEO Google
Reviews API** (aggregator-family, cross-issue candidate from the
COX-63 parallel audit).

1. **Google Places API (New) — Enterprise SKU** (strict field mask
   excluding Atmosphere). First-party; `rating` + `userRatingCount` +
   `websiteUri` in the Enterprise tier; migration target for the
   Legacy-based current implementation.
2. **Apify `compass/crawler-google-places`.** Scraper-actor category;
   highest usage in the Apify Google Maps namespace; nominal ~$2.10/1k.
   Probe measures **effective cost including residential-proxy
   surcharge** (post-Feb-2026 limited-view lockdown).
3. **WebSearch + LLM parsing.** The agentic alternative. No dedicated
   provider module; an agent does a single WebSearch turn and parses
   the SERP card for rating + count. Triggers Outcome E below if it
   wins.
4. **DataForSEO Google Reviews API.** Aggregator-family; claim of
   ~$0.00075/10 reviews pending 2026-pricing verification as the
   first step of Slice B. ToS posture one layer removed from direct
   scraping with no active-litigation signal on file.
5. **Yelp Fusion Plus** ($9.99/1k; 500 calls/day cap; US-only).
   First-party; free during 30-day trial at the probe's volume.
   First-to-drop if Slice B budget or wall-clock tightens.

See `research/2026-04-23-reviews-extraction-method-survey.md` for the
eliminations (Essentials/Pro, SerpAPI, Outscraper, BrightData, direct
scraping) and their rationale.

### Five-branch outcome structure

After Slice B measurement, this ADR's `Decision` section will be
rewritten to one of **exactly these five outcomes** (the branch is
picked by the pre-registered decision rule in the research doc):

#### Outcome A — Migrate-in-place to Google Places API (New) Enterprise

**Trigger:** Google New Enterprise clears coverage ≥ 0.8 AND
effective-cost(Google New Enterprise) ≤ 1.5 × effective-cost(cheapest
alternative).

**Action:** Replace `companyctx/providers/reviews_google_places.py`
with a New-API implementation using **Text Search (New) + Place
Details (New) with an explicit Enterprise-tier field mask that
deliberately excludes Atmosphere-tier fields**. The exact field mask
is `id,displayName,rating,userRatingCount,websiteUri` — nothing else.
Default downstream consumers use rating + count only; requesting full
`reviews` or `reviewSummary` would trigger the Atmosphere SKU at
$25/1k instead of $20/1k Enterprise and produce data we do not use.

- Text Search (New) Enterprise: $35/1k, 1k/mo free.
- Place Details (New) Enterprise: $20/1k, 1k/mo free.
- **Combined post-free Google bill at 3k/mo volume: ~$110/mo**, vs.
  the ~$175/mo Legacy Pro figure implied by the v0.3 cost model.
  Outcome A is the migration path AND a ~37% cost reduction on the
  Google leg, independent of any switch to a different provider.

Same provider slug, same envelope shape, updated cost constants.
Breaking change is internal only — no operator-facing env-var rename;
the new provider reads the same `GOOGLE_PLACES_API_KEY` env var. A
test must lock the field mask against regression — if a future edit
widens it into the Atmosphere tier, pytest should fail. CHANGELOG
entry under v0.5 unreleased documents the Legacy → New migration, the
cost reduction, and the unchanged envelope shape.

#### Outcome B — Switch default to Yelp Fusion Plus

**Trigger:** Yelp coverage ≥ 0.9 on a US-heavy test corpus AND
effective-cost(Yelp) < 0.5 × effective-cost(Google New Enterprise)
AND data consistency vs. Google baseline within ±0.3 stars on
co-present businesses.

**Action:** Introduce `companyctx/providers/reviews_yelp_fusion.py`
as the new default. The commented-out stub entry point at
`pyproject.toml:61` becomes live. Google New Enterprise becomes the
**Attempt-3-escape** for Yelp's US-only gap. New env var
`YELP_FUSION_API_KEY`; CHANGELOG marks as **breaking** (v0.5 minor
bump with a migration note in the release notes, since the old
`GOOGLE_PLACES_API_KEY` is still honored but no longer the primary).

#### Outcome C — Composite (Google New Enterprise → Yelp Fusion fallback)

**Trigger:** Neither provider clears coverage ≥ 0.9 alone, but the
**union** clears ≥ 0.95 AND a fallback shape is warranted by the
coverage gaps surfaced in the probe.

**Action:** A new `reviews_composite.py` provider class that
implements the composite attempt order internally, emits a **single**
cost-cents number (actual billed, summing partial-attempt costs), and
populates `ReviewsSignals` with a `source` field reflecting which
provider actually produced the data. Operator must provision both
`GOOGLE_PLACES_API_KEY` and `YELP_FUSION_API_KEY`; ADR documents that
both are required under this outcome, a setup-friction tradeoff
accepted in exchange for the coverage gain. CHANGELOG v0.5 marks
this as the feature release.

#### Outcome D — Keep Legacy Google Places, reopen probe

**Trigger:** Probe results inconclusive (coverage < 0.8 across all
five finalists, or data consistency divergence > 0.3 stars making
rankings unstable, or Apify effective-cost-including-proxy puts it at
parity with Google New Enterprise), OR the probe runs up against
key-provisioning or actor-breakage issues that invalidate the
measurement.

**Action:** No code change. Ticket re-opens with a wider or different
shortlist (Foursquare, post-ruling SerpAPI). Accept that the v0.3
status quo was defensible and the cost-saving hypothesis did not
survive contact with evidence. This outcome is listed explicitly to
prevent a "we spent the budget, we must switch" motivated-reasoning
error.

#### Outcome E — Remove the reviews provider entirely

**Trigger:** WebSearch + LLM parsing clears coverage ≥ 0.85 on the
test corpus AND effective cost (including agent tokens + WebSearch
tool cost) ≤ 1.5¢/site AND JSON-format compliance rate is 10/10 on
the probe slugs AND data consistency vs. Google baseline is within
±0.3 stars on co-present businesses.

**Action:** The highest-leverage outcome available to this spike.

1. Delete `companyctx/providers/reviews_google_places.py` and its
   tests / fixtures / entry-point registration in `pyproject.toml:60`.
2. Remove the `reviews` provider-category references from
   `docs/PROVIDERS.md`; the category stays in the schema (for any
   downstream who wires their own) but the default waterfall emits
   `data.reviews: null` and documents **the agentic pattern** as the
   recommended downstream integration:

   > For reviews, do not wire a dedicated provider. Instead, at the
   > synthesis layer of your agent pipeline, issue a
   > `WebSearch("<name> <city> reviews")` turn and parse the SERP
   > card. Example: see `examples/reviews_via_websearch.py`.

3. Add `examples/reviews_via_websearch.py` showing the prompt
   template, the JSON-return contract, and a validator that rejects
   hallucinated numbers.
4. Remove `GOOGLE_PLACES_API_KEY` from the setup documentation; it
   remains honored for any user who has not yet migrated their
   pipeline to the agentic pattern, but the zero-key path no longer
   gates on it.
5. CHANGELOG v0.5 marks this as a **BREAKING CHANGE** with a
   migration note: users whose pipelines explicitly consume
   `data.reviews` must either (a) add the WebSearch+parse step
   upstream of the companyctx call, or (b) wire their own reviews
   provider via entry point before the v0.5 upgrade. Migration path
   is documented with both options so downstream users can pick.
6. Update the zero-key README hero to reflect that reviews are
   **outside** the companyctx schema-locked output in v0.5 and that
   this is an intentional narrowing based on measurement.

This outcome is listed first in the decision rule not because it is
most likely but because it is most **consequential** — collapsing a
whole provider surface into an agent-tool pattern is the largest
scope-narrowing move the spike can produce, and narrowing scope to
the deterministic-CLI wedge is the repo's stated preference when
evidence supports it. See ADR
`decisions/2026-04-20-zero-key-stealth-strategy.md` for the "every
attempt maps to the same envelope shape; providers are replaceable;
the envelope is not" posture that Outcome E operationalizes.

### Explicitly rejected outcomes

- **Pluggable reviews provider** (the issue's outcome #4). Ship one
  default that works; don't make the user pick. Pluggability for its
  own sake is user-facing choice overload and internal-facing
  multi-fixture / multi-CI-cell maintenance debt. The `ProviderBase`
  abstraction already lets a user **replace** the default via entry
  point; no TOML/env toggle needed. If the probe surfaces a segment
  that needs a different provider, the fix is a **segment-specific
  default** documented in a follow-up ADR, not a generic
  pluggable-config surface.
- **Google Places Essentials downgrade.** Impossible — the required
  fields are not in that SKU (see Context #2).
- **SerpAPI.** Eliminated on active litigation (see Context #3).

## Rationale

1. **Measurement-before-naming is the established pattern.** The TLS
   spike precedent (ADR accepted after
   `research/2026-04-21-tls-impersonation-spike.md` landed the
   numbers) is the one this ADR follows. Proposed today, accepted
   after Slice B.
2. **Pre-registering the decision rule removes motivated-reasoning
   risk.** The research doc's `Decision rule (pre-committed)` section
   maps probe numbers to outcome branches before we see the numbers.
   If Google New Enterprise wins on the rule, we keep it even if the
   mood on the day of the probe is "we want to switch."
3. **Outcome E is the highest-leverage branch.** If WebSearch + LLM
   parsing clears the decision rule's thresholds, the right move is
   not to replace one provider with a cheaper one but to collapse the
   provider surface to zero and document the agentic pattern.
   Narrowing scope to the deterministic-CLI wedge is the repo's
   stated preference when evidence supports it.
4. **Single-provider > pluggable.** `companyctx`'s adoption wedge is
   "one command, deterministic output, no config knobs." A pluggable
   `COMPANYCTX_REVIEWS_PROVIDER=...` toggle contradicts that wedge.

## Alternatives considered (at the ADR layer)

| Option | Why deferred or rejected |
|---|---|
| "Stick with Legacy Google Places indefinitely" | Legacy is non-enablable for new GCP projects since 2025-03-01. Even if the probe favors Google, migration to New Enterprise is required on time-horizon grounds. |
| "Ship pluggable provider config" | Contradicts the deterministic-CLI wedge; adds maintenance across N providers that we don't have evidence we need. Rejected per Rationale #4. |
| "Just switch to Apify, cheaper and done" | Pre-probe evidence says "cheaper" is partial — residential-proxy cost after Feb-2026 lockdown is the open question the probe answers. Motivated-reasoning-avoidance: let the numbers pick. |
| "Broader shortlist — include SerpAPI / Outscraper" | SerpAPI eliminated on litigation. Outscraper eliminated as it wraps the same scraped Google data as Apify with zero ToS improvement. **DataForSEO is in the shortlist.** |
| "Skip WebSearch + LLM parsing — it's not a third-party API" | The question framing itself was skeptical ("is Claude somehow finding reviews just with web"). Excluding it because it doesn't fit the "structured third-party provider" mental model would reproduce the v0.3 error of shipping a provider without measuring the alternatives. Outcome E is the branch that takes the agentic answer seriously. |
| "Expand probe to 100 sites for statistical significance" | The measurement question at stake is cost-and-coverage-fit at expected volume, not 3-decimal-place statistics. n=10 is enough to separate providers that differ by >20%; if the numbers come in tighter than that, the ADR branches to Outcome D (reopen) rather than picking between near-ties. |

## Risks

- **Probe runs land in Outcome D (inconclusive).** Mitigation: the
  decision rule names this outcome explicitly so we don't force a
  switch under ambiguous numbers. Reopen with a different shortlist
  (Foursquare comes in from the bench; post-ruling SerpAPI if the
  case resolves favorably).
- **Apify `compass/crawler-google-places` is broken on probe day.**
  Possible — the Feb-2026 limited-view event broke several scrapers.
  Mitigation: that *is* the measurement. If the actor returns zero on
  the probe set at any proxy configuration, that's dispositive
  against the scraper-actor category in general, and Outcome A/B/C
  take it.
- **Yelp Fusion free-trial misattribution.** A 30-day trial at
  500 calls/day could mask the $9.99/1k reality. Mitigation: probe
  records **billed cost at post-trial rates** in the
  `cost_incurred_cents` field (even if the actual invoice is $0
  during the trial), making the numbers comparable to Google's
  billed-from-day-one pricing.
- **v0.5 breaking-change release notes are harsher than downstream
  users tolerate.** Mitigation: Outcome A (migrate-in-place) is
  specifically structured to be *non-breaking* (same env var, same
  envelope shape, cost constants change under the hood). Outcomes
  B/C/E require an env-var or setup change and get a `BREAKING
  CHANGE:` footer honestly.

## Open questions (resolved in Slice B)

1. What is the **effective** cost per successful call for each
   finalist, including proxy and actor-start overheads?
2. What is the coverage rate on the social-only edge-case slugs,
   where Google Places has historically returned ZERO_RESULTS?
3. Do ratings agree within ±0.3 stars across providers for the
   same-address small-business slugs (high-overlap businesses)?
4. Does the Apify actor's success rate survive a same-day re-run 2
   hours later? (Flakiness heuristic — if not, Outcome A/B is
   strengthened vs. Outcome C that relies on fallback working.)

## Downstream changes (deferred — do NOT ship under Slice A)

When this ADR flips to `accepted`:

1. Status frontmatter: `proposed` → `accepted`, add `accepted_on`.
2. `docs/PROVIDERS.md` reviews section updated to name the chosen
   provider and link this ADR.
3. One of Outcomes A / B / C / E implemented in a follow-up PR
   against the implementation issue.
4. `CHANGELOG.md` v0.5-unreleased entry under `### Changed`
   (Outcome A) or `### BREAKING` (Outcomes B/C/E).
5. Fixtures updated for the new provider (new response-shape JSON
   under `fixtures/<slug>/`).
6. Pre-push gates (`ruff`, `mypy`, `pytest --cov-fail-under=70`)
   remain green. Provider tests mirror the structure of
   `tests/test_reviews_google_places.py`.

Nothing above ships in the same PR as this ADR. This PR is research
+ ADR only.
