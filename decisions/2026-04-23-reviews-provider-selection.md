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

Per the repo rule in `CLAUDE.md` ("Never name a vendor in public docs
before measurement"), this ADR is not `accepted` and does not commit
`companyctx` to a chosen provider. The desktop survey in
`research/2026-04-23-reviews-extraction-method-survey.md` produced a
shortlist of three finalists; the live 10-site probe (Slice B of issue
[#116](https://github.com/dmthepm/companyctx/issues/116)) is what flips
this ADR to `accepted` and names a specific provider or composition.

Until the probe runs, the default in `companyctx` remains
`reviews_google_places` (Legacy Place Details), exactly as shipped in
v0.3/v0.4. **This ADR does not authorize any code change.**

## Context

### The process gap this closes

`v0.3` shipped `reviews_google_places` (Legacy Google Places) as the
sole reviews provider at ~5.4¢/call. That choice was informed by a v0.1
desktop survey
(`noontide-projects/research/2026-04-20-research-pack-reviews-business-claude-code.md`)
but was **not backed by a same-corpus head-to-head measurement against
alternatives.** The TLS-impersonation library spike (#21 /
`decisions/2026-04-20-zero-key-stealth-strategy.md`) is the pattern the
reviews slot should have followed from the start: candidates enumerated,
candidates measured on the same corpus, decision cited back to the
numbers. Issue [#116](https://github.com/dmthepm/companyctx/issues/116)
retrofits that pattern.

### Three facts that force the decision regardless of probe outcome

1. **Google Places Legacy is no longer enablable for new projects
   (since 2025-03-01).** Existing keys continue to work, but any new
   `companyctx` user trying to follow the Quickstart with a fresh GCP
   project gets stuck at "cannot enable the Places API (Legacy)."
   Migration to Places API (New) is required on time-horizon grounds
   even if the probe confirms Google is the right source.
2. **The fields we need (`rating`, `userRatingCount`) are in the
   Enterprise SKU of the New API.** Essentials and Pro tiers do not
   return them. The "downgrade to Essentials" outcome listed in the
   issue is architecturally impossible.
3. **SerpAPI is in active Google DMCA litigation (Dec-2025; hearing
   2026-05-19).** Any ADR naming SerpAPI as `accepted` during active
   litigation is a ship-and-regret risk. SerpAPI is dropped from the
   shortlist pre-probe.

### Partner-shaped reality check

The partner's `new-signal-studio` pipeline already runs a
**multi-source fallback** (Google → Yelp → HomeAdvisor → Angi → BBB →
Trustindex), treating any "INSUFFICIENT DATA" event as a
pipeline-continues-with-missing-field rather than a stall. The partner
does not need the "one true review provider"; the partner needs
"rating + count shows up from somewhere reliable." That shape
pushes the ADR toward **composite fallback** over either
single-provider or user-pluggable.

## Decision (proposed)

### Finalist shortlist for the Slice B probe

Three providers, measured head-to-head on the same 10-site corpus:

1. **Google Places API (New) — Enterprise SKU.** First-party;
   `rating` + `userRatingCount` in the Enterprise tier; migration target
   for our Legacy-based current implementation.
2. **Yelp Fusion Plus** ($9.99/1k; 500 calls/day cap; US-only). First-party;
   free during 30-day trial at partner's volume.
3. **Apify `compass/crawler-google-places`.** Represents the
   scraper-actor category the issue specifically asked about; highest
   usage in the Apify Google Maps namespace; nominal ~$2.10/1k.
   Probe measures **effective cost including residential-proxy surcharge**
   (post-Feb-2026 limited-view lockdown).

See `research/2026-04-23-reviews-extraction-method-survey.md` for the
eliminations (Essentials/Pro, SerpAPI, Outscraper, BrightData, direct
scraping) and their rationale.

### Four-branch outcome structure

After Slice B measurement, this ADR's `Decision` section will be
rewritten to one of **exactly these four outcomes** (the branch is
picked by the pre-registered decision rule in the research doc):

#### Outcome A — Migrate-in-place to Google Places API (New) Enterprise

**Trigger:** Google New Enterprise clears coverage ≥ 0.8 AND
effective-cost(Google New Enterprise) ≤ 1.5 × effective-cost(cheapest
alternative).

**Action:** Replace `companyctx/providers/reviews_google_places.py`
with a New-API implementation (Text Search (New) + Place Details (New)
with an explicit Enterprise-tier field mask). Same provider slug,
same envelope shape, updated cost constants. Breaking change is
internal only — no partner-facing env-var rename; the new provider
reads the same `GOOGLE_PLACES_API_KEY` env var. CHANGELOG entry
under v0.5 unreleased documents the Legacy → New migration and the
unchanged envelope shape.

#### Outcome B — Switch default to Yelp Fusion Plus

**Trigger:** Yelp coverage ≥ 0.9 on the US-heavy partner corpus AND
effective-cost(Yelp) < 0.5 × effective-cost(Google New Enterprise) AND
data consistency vs. Google baseline within ±0.3 stars on co-present
businesses.

**Action:** Introduce `companyctx/providers/reviews_yelp_fusion.py` as
the new default. The commented-out stub entry point at
`pyproject.toml:61` becomes live. Google New Enterprise becomes the
**Attempt-3-escape** for Yelp's US-only gap. New env var
`YELP_FUSION_API_KEY`; CHANGELOG marks as **breaking** (v0.5 minor
bump with a migration note in the release notes, since the old
`GOOGLE_PLACES_API_KEY` is still honored but no longer the primary).

#### Outcome C — Composite (Google New Enterprise → Yelp Fusion fallback)

**Trigger:** Neither provider clears coverage ≥ 0.9 alone, but the
**union** clears ≥ 0.95 AND the partner's session logs already show the
composite shape is the operational posture.

**Action:** A new `reviews_composite.py` provider class that implements
the composite attempt order internally, emits a **single** cost-cents
number (actual billed, summing partial-attempt costs), and populates
`ReviewsSignals` with a `source` field reflecting which provider
actually produced the data. Partner must provision both
`GOOGLE_PLACES_API_KEY` and `YELP_FUSION_API_KEY`; ADR documents
that both are required under this outcome, which is a setup-friction
tradeoff accepted in exchange for the coverage gain. CHANGELOG v0.5
marks this as the feature release.

#### Outcome D — Keep Legacy Google Places, reopen probe

**Trigger:** Probe results inconclusive (coverage < 0.8 across all
three finalists, or data consistency divergence > 0.3 stars making
rankings unstable, or Apify effective-cost-including-proxy puts it at
parity with Google New Enterprise), OR the probe runs up against
key-provisioning or actor-breakage issues that invalidate the
measurement.

**Action:** No code change. Ticket re-opens with a wider or different
shortlist. Accept that the v0.3 status quo was defensible and the
cost-saving hypothesis did not survive contact with evidence. This
outcome is listed explicitly to prevent a "we spent the budget, we
must switch" motivated-reasoning error.

### Explicitly rejected outcomes

- **Pluggable reviews provider** (the issue's outcome #4). Ship one
  default that works; don't make the user pick. Pluggability for its
  own sake is partner-facing choice overload and internal-facing
  multi-fixture / multi-CI-cell maintenance debt. The `ProviderBase`
  abstraction already lets a user **replace** the default via entry
  point; no TOML/env toggle needed. If the probe surfaces a segment
  (e.g., non-US partners) that needs a different provider, the fix is
  a **segment-specific default** documented in a follow-up ADR, not a
  generic pluggable-config surface.
- **Google Places Essentials downgrade.** Impossible — the required
  fields are not in that SKU (see Context #2).
- **SerpAPI.** Eliminated on active litigation (see Context #3).

## Rationale

1. **Measurement-before-naming is the repo rule.** The TLS spike
   precedent (ADR accepted after `research/2026-04-21-...-spike.md`
   landed the numbers) is the one this ADR follows. Proposed today,
   accepted after Slice B.
2. **Pre-registering the decision rule removes motivated-reasoning
   risk.** The research doc's `Decision rule (pre-committed)` section
   maps probe numbers to outcome branches before we see the numbers.
   If Google New Enterprise wins on the rule, we keep it even if the
   partner mood on the day of the probe is "we want to switch."
3. **Honoring the partner's own fallback posture as the probable
   outcome shape.** Outcome C (composite) is the one that best matches
   `new-signal-studio`'s observed behavior of running Yelp / Angi / BBB
   / Trustindex when Google returns nothing. Outcome A (stay, just
   migrate) is defensible if coverage is high. Outcomes B and D are
   listed because they are real branches the probe could land on, not
   because we expect them.
4. **Single-provider > pluggable.** `companyctx`'s adoption wedge is "one
   command, deterministic output, no config knobs." A pluggable
   `COMPANYCTX_REVIEWS_PROVIDER=...` toggle contradicts that wedge.

## Alternatives considered (at the ADR layer)

| Option | Why deferred or rejected |
|---|---|
| "Stick with Legacy Google Places indefinitely" | Legacy is non-enablable for new GCP projects since 2025-03-01. Even if the probe favors Google, migration to New Enterprise is required on time-horizon grounds. |
| "Ship pluggable provider config" | Contradicts the deterministic-CLI wedge; adds maintenance across N providers that we don't have evidence we need. Rejected per Rationale #4. |
| "Just switch to Apify, cheaper and done" | Pre-probe evidence says "cheaper" is partial — residential-proxy cost after Feb-2026 lockdown is the open question the probe answers. Motivated-reasoning-avoidance: let the numbers pick. |
| "Broader shortlist — include SerpAPI / DataForSEO / Outscraper" | SerpAPI eliminated on litigation. Outscraper eliminated as it wraps the same scraped Google data as Apify with zero ToS improvement. DataForSEO evaluated but pricing transparency is insufficient for a same-day 10-site probe inside $15 budget; reopen if outcomes A-D all fail. |
| "Expand probe to 100 sites for statistical significance" | The measurement question at stake is cost-and-coverage-fit at partner-scale, not 3-decimal-place statistics. n=10 is enough to separate providers that differ by >20%; if the numbers come in tighter than that, the ADR branches to Outcome D (reopen) rather than picking between near-ties. |

## Risks

- **Probe runs land in Outcome D (inconclusive).** Mitigation: the
  decision rule names this outcome explicitly so we don't force a
  switch under ambiguous numbers. Reopen with a different shortlist
  (DataForSEO comes in from the bench; post-ruling SerpAPI if the
  case resolves favorably).
- **Apify `compass/crawler-google-places` is broken on probe day.**
  Possible — the Feb-2026 limited-view event broke several scrapers.
  Mitigation: that *is* the measurement. If the actor returns zero on
  our probe set at any proxy configuration, that's dispositive against
  the scraper-actor category in general, and Outcome A/B/C take it.
- **Yelp Fusion free-trial misattribution.** A 30-day trial at
  500 calls/day could mask the $9.99/1k reality. Mitigation: probe
  records **billed cost at post-trial rates** in the cost_incurred_cents
  field (even if the actual invoice is $0 during the trial), making the
  numbers comparable to Google's billed-from-day-one pricing.
- **v0.5 breaking-change release notes are harsher than partner
  tolerates.** Mitigation: Outcome A (migrate-in-place) is specifically
  structured to be *non-breaking* (same env var, same envelope shape,
  cost constants change under the hood). Outcomes B/C require an
  env-var or setup change and get a `BREAKING CHANGE:` footer honestly.
- **The partner cares less about this than the issue author does.**
  Real possibility per the partner-shaped reality check above. Mitigation:
  if the probe lands on Outcome A (migrate-in-place, near-invisible
  change), ship it and move on. Don't force a multi-provider refactor
  for a cost delta the downstream consumer isn't asking for.

## Open questions (resolved in Slice B)

1. What is the **effective** cost per successful call for each finalist,
   including proxy and actor-start overheads?
2. What is the coverage rate on the 2 no-website-just-Facebook slugs,
   where Google Places has historically returned INSUFFICIENT DATA per
   the partner's session logs?
3. Do ratings agree within ±0.3 stars across providers for the 4
   medical/aesthetic slugs (high-overlap businesses)?
4. Does the Apify actor's success rate survive a same-day re-run 2
   hours later? (Flakiness heuristic — if not, Outcome A/B is
   strengthened vs. Outcome C that relies on fallback working.)

## Downstream changes (deferred — do NOT ship under Slice A)

When this ADR flips to `accepted`:

1. Status frontmatter: `proposed` → `accepted`, add `accepted_on`.
2. `docs/PROVIDERS.md` reviews section updated to name the chosen
   provider and link this ADR.
3. One of Outcomes A / B / C implemented in a follow-up PR against the
   implementation issue.
4. `CHANGELOG.md` v0.5-unreleased entry under `### Changed` (Outcome A)
   or `### BREAKING` (Outcomes B/C).
5. Fixtures updated for the new provider (new response-shape JSON under
   `fixtures/<slug>/`).
6. Pre-push gates (`ruff`, `mypy`, `pytest --cov-fail-under=70`) remain
   green. Provider tests mirror the structure of
   `tests/test_reviews_google_places.py`.

Nothing above ships in the same PR as this ADR. This PR is research + ADR only.
