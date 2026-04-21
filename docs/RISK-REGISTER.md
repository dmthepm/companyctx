# Risk Register — D100-grounded failure modes

This document catalogs the Phase 1 web-fetch / content-extraction failure
modes observed in the D100 cold-outreach pipeline's session transcripts and
maps each one to the `companyctx` envelope surfaces that must describe it.

It exists so that `expected.json` fixtures, provider implementations, and
downstream pipelines stop writing against *assumed* failures and start
writing against *observed* ones.

## Scope

- **Evidence base.** 37 session transcripts committed to
  `joel-req/new-signal-studio` at `logs/` and `logs/backfill/`, spanning
  **2026-04-12 → 2026-04-21**. 13 contained substantive Phase 1 activity
  (web fetch + HTML extraction); 24 were orchestration shells, MCP ping
  diagnostics, or out-of-scope Apollo / Google Docs / Instantly work.
  Niches covered: gutter installation, real-estate staging, home
  inspection, IV-therapy wellness, chiropractic, dermatology-aesthetic,
  window replacement, waste management. ~180+ per-prospect sub-agent runs
  sampled.
- **Only Phase 1 is in scope.** Apollo, Google Docs, Instantly, and
  launchd/auth failures belong to other systems and are excluded.
- **Transcripts are evidence, not source code.** They live in
  `new-signal-studio`; they are not committed here. Quoted snippets are
  sanitized (business names → `<site>`, owners → `<owner>`, cities and
  real domains redacted).

## How to read the register

Each failure mode gets:

- **Signature** — what it looks like in a transcript.
- **Frequency** — how often it fires across the 13 heavy transcripts.
- **Evidence** — one or two filename:line citations.
- **Waterfall layer** that should cover it (Attempt 1 zero-key stealth,
  Attempt 2 smart-proxy provider, Attempt 3 direct-API provider, or
  a cross-cutting concern).
- **Envelope mapping** — proposed `ProviderRunMetadata.status`, top-level
  envelope `status`, `error` template, `suggestion` template.
- **Agent recovery observed** — what the D100 agent did, and whether it
  was the right thing for `companyctx` to do.

Envelope enums, for reference (see `docs/SPEC.md`):

- `ProviderRunMetadata.status` ∈ `{ok, degraded, failed, not_configured}`
- Top-level envelope `status` ∈ `{ok, partial, degraded}`

## Summary

| ID | Mode | Freq (transcripts) | Layer | Envelope shape |
|---|---|---|---|---|
| FM-1 | Homepage 403 / hard block by CDN anti-bot | 2 | Attempt 2 | per-provider `failed` → top `partial` if Attempt 2 rescues, else `degraded` |
| FM-2 | Yelp 403 on server-rendered fetch | 4 | Attempt 3 (Yelp Fusion) | per-provider `failed` → top `partial` |
| FM-3 | IG / FB follower-count scrape blocked | 4 | gap (no API without commercial key) | per-provider `degraded` → top `partial` |
| FM-4 | Google review count unreachable (GBP is JS-rendered) | 3 | Attempt 3 (Google Places) | `not_configured` or `failed` → top `partial` |
| FM-5 | "Under construction" / redirect to parent brand | 1 | Attempt 1 (needs richer envelope metadata) | per-provider `degraded` + `warning` |
| FM-6 | Services/about content present but unstructured | 13/13 | extraction heuristic (Attempt 1 output) | per-provider `degraded` when sub-fields empty |
| FM-7 | One-page template / brochureware site | 2+ | Attempt 1 (honest low-confidence) | `ok` per-provider, top `partial` + `quality.confidence = low` |
| FM-8 | Upstream vertical tag disagrees with homepage-inferred vertical | 1 | Attempt 1 (envelope warning) | top `ok` + `quality.warnings` |
| FM-9 | Franchise / multi-location ambiguity | 2 | Attempt 3 (per-location GBP place-id) | per-provider `degraded` → top `partial` |
| FM-10 | Secondary-source cascade without provenance | 5+ | cross-cutting (schema) | per-field `source_url` required |
| FM-11 | About-page URL not auto-discovered | 3+ | Attempt 1 (owned heuristic, not OSS) | per-provider `degraded` on `site_about` |
| FM-12 | Press / awards discovery needs search, not site fetch | 10+ | separate provider (search-API) | `mentions_*: not_configured` until keyed |
| FM-13 | Site-fetch timeouts / transient failures | 0 observed | Attempt 1 (defensive default only) | `failed` — do not over-invest |
| FM-14 | Homepage fetched but social handles not found | 3+ | Attempt 1 (footer anchor heuristic) | `social.<platform>.handle: degraded` |

## FM-1 — Homepage returns 403 / hard block on root domain

- **Signature.** Sub-agent narrative contains `"<site> blocked WebFetch
  (403)"` or `"Website blocked 403 — data sourced from BBB, Yelp, search
  results"`. No retry; no header variation.
- **Frequency.** 2 transcripts, 2 distinct prospects (window-replacement
  vendor, roofing/gutter contractor). Low absolute count, 100%
  unrecoverable in-transcript.
- **Evidence.**
  - `backfill-2026-04-18-command-message-d100-command-m-05ed4365.md:3775`
  - `backfill-2026-04-16-command-message-d100-command-m-167f63bc.md:1605`
- **Agent recovery.** Pivoted to BBB / Birdeye / search-snippet sources
  in-LLM with no structured record of the swap. Homepage-sourced fields
  (services, team, founder bio) absent from the brief.
- **Waterfall layer.** Attempt 1 can't win — the site is behind a CDN
  anti-bot layer that rejects the TLS-impersonation fingerprint. Attempt
  2 (smart-proxy provider with residential egress) is the designed fix.
  Attempt 3 doesn't help: there is no API for "give me this homepage."
- **Envelope mapping.**
  - Attempt 1: `ProviderRunMetadata.status = "failed"`,
    `error = "CDN anti-bot 403 on homepage"`,
    `suggestion = "retry via smart-proxy provider with residential egress"`.
  - If Attempt 2 rescues: top-level `status = "ok"` (or `partial` if
    other providers degraded).
  - If Attempt 2 is `not_configured` or also fails: top-level
    `status = "partial"` with `fields_missing` populated and
    `suggestion = "configure a smart-proxy provider key"`.

## FM-2 — Yelp returns 403 on server-rendered fetch

- **Signature.** `"Yelp 403 blocked"`; `"Yelp blocked, Google not
  confirmable"`. Single most common Phase 1 data-loss pattern in the
  corpus.
- **Frequency.** 4 transcripts, 5+ distinct prospects.
- **Evidence.**
  - `backfill-2026-04-17-command-message-d100-command-m-77656e04.md:2840`
  - `backfill-2026-04-17-command-message-d100-command-m-1ff83f41.md:3126`
- **Agent recovery.** Substituted Birdeye / HomeAdvisor / Angi / BBB /
  Houzz aggregates where available; otherwise `INSUFFICIENT DATA`.
- **Waterfall layer.** Attempt 1 fails reliably. Attempt 2 (smart-proxy)
  may or may not beat Yelp's detection. **Attempt 3 is the designed
  fix** — the Yelp Fusion API exists for exactly this. This is the
  single strongest transcript-grounded argument for Attempt 3 existing.
- **Envelope mapping.**
  - Scraped-Yelp provider: `ProviderRunMetadata.status = "failed"`.
  - `reviews_yelp_fusion` if no key: `status = "not_configured"`.
  - Top-level `status = "partial"`,
    `fields_missing = ["reviews.yelp.count", "reviews.yelp.rating"]`,
    `suggestion = "configure Yelp Fusion direct-API key to bypass
    scraping"`.

## FM-3 — Instagram / Facebook follower-count scrape blocked

- **Signature.** `"IG profile scrapes were blocked"`, `"Facebook
  follower counts could not be extracted from public previews"`.
- **Frequency.** 4 transcripts, 5+ distinct prospects. Failure is
  asymmetric: FB likes succeed ~70% of the time, IG follower count
  succeeds <30%.
- **Evidence.**
  - `d100-run-waste-management-services-2026-04-21-e1155059-3079-4046-b663-18f8258a314f.md:2115`
  - `backfill-2026-04-17-command-message-d100-command-m-9bc12c4e.md:4107`
- **Agent recovery.** Marked the count `INSUFFICIENT DATA`. Often
  captured the platform's *presence* (handle is active) but not the
  *numeric count*.
- **Waterfall layer.** Attempt 1 confirms the handle via site-linked-out
  detection. Attempt 2 proxy helps only marginally. Attempt 3 is a
  genuine **Waterfall gap**: IG / FB / TikTok follower counts have no
  deterministic public API without a commercial authenticated-graph
  agreement.
- **Envelope mapping.**
  - Per-handle `ProviderRunMetadata.status = "degraded"` — handle
    confirmed, count missing. This is the cleanest transcript-backed
    argument for keeping the three-state provider enum instead of
    collapsing to binary ok/fail.
  - `error = "social-platform login-wall on counts"`,
    `suggestion = "handle confirmed; follower count requires
    authenticated social-graph API"`.
  - YouTube is the exception: `social_counts_youtube` (YouTube Data API)
    covers it cleanly under Attempt 3 when keyed.

## FM-4 — Google review count simply never surfaces

- **Signature.** `"Google rating and review count not surfaced"`;
  `"Google-specific not surfaced"`. Distinct from FM-2: no explicit 403;
  the number isn't visible via fetch + search-snippet approaches.
- **Frequency.** 3+ transcripts, high per-transcript occurrence count.
  The home-inspection vertical alone showed 6+ prospects with this flag.
- **Evidence.**
  - `backfill-2026-04-17-command-message-d100-command-m-9bc12c4e.md:3989`
  - `backfill-2026-04-17-command-message-d100-command-m-57f83f37.md:1820`
- **Agent recovery.** Captured whatever aggregates were visible
  (Birdeye, HomeAdvisor, Houzz, Angi, franchise-rollup pages) and
  flagged Google-specific numbers as `INSUFFICIENT DATA`.
- **Why it happens.** The Google Business Profile map panel is
  JS-rendered inside a SPA surface. This is not a captcha; it is
  structural. A stealth HTTP fetch will never parse it.
- **Waterfall layer.** Attempts 1 and 2 cannot solve this. **Attempt 3
  (`reviews_google_places`, Google Places API) is the only deterministic
  path.** Second-strongest transcript argument for Attempt 3.
- **Envelope mapping.**
  - `reviews_google_places` with no key: `status = "not_configured"`,
    `suggestion = "enable Google Places API via GOOGLE_PLACES_API_KEY"`.
  - With key but API rejects: `status = "failed"`.
  - Top-level `status = "partial"` with
    `fields_missing = ["reviews.google.count", "reviews.google.rating"]`.

## FM-5 — "Under construction" or redirect to parent brand

- **Signature.** `"<site> is explicitly 'under construction'"`;
  `"<site> redirects to <parent-brand-site>"`.
- **Frequency.** 1 transcript, 1 direct occurrence + 1 adjacent note.
  Low count but a clean, named shape.
- **Evidence.**
  - `backfill-2026-04-18-command-message-d100-command-m-05ed4365.md:3776`
- **Agent recovery.** Followed the redirect manually, pulled data from
  the parent-brand site, preserved the original business name in the
  brief. Caveat: the redirect target is a *different* business entity
  (franchise parent), so some imported facts don't describe the
  prospect's specific location.
- **Waterfall layer.** Attempt 1 — the need is richer envelope
  metadata, not a new layer.
- **Envelope mapping.**
  - Preserve both `requested_url` and `effective_url` in the envelope
    (or on `pages`).
  - Attempt-1 `ProviderRunMetadata.status = "degraded"` when
    `effective_url` differs from `requested_url` across a brand boundary
    (heuristic: SLD mismatch).
  - `suggestion = "site redirected to parent domain; extracted data may
    describe the parent brand, not this prospect"`.

## FM-6 — Services / about content present but unstructured

- **Signature.** Briefs inline services, credentials, team names, and
  founding-year into prose — there is no structured `services[]` or
  `credentials[]` payload passed between sub-agents. Every downstream
  consumer re-reads HTML to get at 2 KB of facts.
- **Frequency.** Effectively **every** high-activity transcript
  (13/13). This is the **dominant token-cost failure** across the
  corpus, not a fetch failure.
- **Evidence.**
  - `d100-run-waste-management-services-2026-04-21-e1155059-3079-4046-b663-18f8258a314f.md:2085`
  - `backfill-2026-04-18-command-message-d100-command-m-9aea3234.md:827`
- **Why it matters.** This *is* the companyctx wedge: emit structured
  fields, so synthesis never re-fetches. Confirms the OSS-extraction
  gap that services-list extraction has no clean OSS (see
  `docs/EXTRACTION-STRATEGY.md`).
- **Waterfall layer.** Extraction-layer concern; orthogonal to the
  Waterfall. Applies to Attempt-1 output shape.
- **Envelope mapping.**
  - `signals_site_heuristic` and related providers emit
    `status = "ok"` when structured fields (`services`, `team`,
    `credentials`, `founded_year`) populate.
  - `status = "degraded"` when raw `pages.homepage_text` was captured
    but structured sub-fields are empty because heuristics didn't hit.
  - `suggestion = "services list needs LLM synthesis from raw text"`
    when structured extraction fails but raw text is present.

## FM-7 — One-page / brochureware / relationship-driven B2B site

- **Signature.** Brief flags `"extremely low digital footprint"` or
  `"no dedicated social surfaced"`, or runs short on differentiators
  despite a successful fetch.
- **Frequency.** 2 transcripts, 3+ prospects.
- **Evidence.**
  - `backfill-2026-04-16-command-message-d100-command-m-167f63bc.md:1473`
  - `backfill-2026-04-18-command-message-d100-command-m-05ed4365.md:3669`
- **Agent recovery.** Accepted thin data, pivoted script angles to lean
  on Apollo firmographics. This is the right pattern to mirror.
- **Waterfall layer.** Attempt 1 succeeds fetch-wise; no later layer
  helps. The fetch worked; the site just has nothing to extract.
- **Envelope mapping.**
  - Attempt-1 `ProviderRunMetadata.status = "ok"`.
  - Top-level `status = "partial"` with `quality.confidence = "low"`
    and `fields_missing` populated.
  - `suggestion = "site is brochureware; downstream synthesis should
    lean on firmographic data"`.
  - **Do not map to `degraded` or `failed`** — the fetch succeeded. The
    distinction between "site blocked us" and "site had nothing" is
    load-bearing for downstream decisions.

## FM-8 — Upstream vertical tag disagrees with homepage-inferred vertical

- **Signature.** `"Apollo's 'real estate' classification confirmed
  wrong — they're portable sanitation + site services."`
- **Frequency.** 1 transcript (waste-management 2026-04-21), 2
  prospects in a single batch.
- **Evidence.**
  - `d100-run-waste-management-services-2026-04-21-e1155059-3079-4046-b663-18f8258a314f.md:2059`
  - `d100-run-waste-management-services-2026-04-21-e1155059-3079-4046-b663-18f8258a314f.md:2139`
- **Agent recovery.** Corrected the classification from homepage text
  mid-research. The correction lives in prose, not in a structured
  field.
- **Waterfall layer.** Attempt 1 resolves.
- **Envelope mapping.** This is the canonical "companyctx is a router"
  signal. Emit a heuristic `vertical_detected` field on
  `signals_site_heuristic` output and surface a mismatch when upstream
  firmographics disagree:
  - Top-level `status = "ok"` with
    `quality.warnings = ["upstream vertical tag disagrees with
    homepage-inferred vertical"]`.
  - The envelope never asserts the "true" vertical — that's a synthesis
    judgment. It reports the observation.

## FM-9 — Franchise / multi-location ambiguity

- **Signature.** `"franchise aggregate 4.9/747"`; `"franchise page
  reports 37 reviews / 5.0; Google-specific not surfaced"`.
- **Frequency.** 2 transcripts (home-inspection, real-estate-staging),
  6+ prospects.
- **Evidence.**
  - `backfill-2026-04-17-command-message-d100-command-m-9bc12c4e.md:4141`
  - `backfill-2026-04-17-command-message-d100-command-m-9bc12c4e.md:4146`
- **Agent recovery.** Kept both numbers, prefixed one "franchise
  aggregate." No structure.
- **Waterfall layer.** Attempt 3 (Google Places) is the real fix, same
  family as FM-4 but with a subtlety: callers must pass the *location-
  specific* GBP place-id, not just the brand name.
- **Envelope mapping.**
  - `reviews.google` carries `scope: "location" | "parent_brand" |
    "aggregate"` (or equivalent) so downstream callers can distinguish.
  - When only aggregate is available: `ProviderRunMetadata.status =
    "degraded"`, top-level `partial`.
  - `suggestion = "parent-brand aggregate captured; location-level
    numbers require Google Places API on the specific GBP listing"`.

## FM-10 — Secondary-source cascade without provenance

- **Signature.** When primary sources (FM-1, FM-2, FM-4) block, the
  agent silently pulls from BBB, Birdeye, HomeAdvisor, Houzz,
  RocketReach, press-release wires, chamber sites. No structured record
  of which fact came from where.
- **Frequency.** Co-occurs with every FM-1/FM-2/FM-4 firing: 5+
  transcripts, 10+ prospects.
- **Evidence.**
  - `backfill-2026-04-16-command-message-d100-command-m-167f63bc.md:1605`
  - `backfill-2026-04-18-command-message-d100-command-m-05ed4365.md:3775`
- **Waterfall layer.** Cross-cutting — this is a schema concern, not a
  single-attempt concern.
- **Envelope mapping.** Schema guidance:
  - Each extracted value that can come from multiple surfaces should be
    a struct carrying `source_url` + originating `provider_slug`, not a
    bare scalar. The v0.1 envelope already models per-provider
    provenance via `ProviderRunMetadata`; reviews / mentions / signals
    that can spill across surfaces should extend this down to the
    field level over time.
  - When a field's value was sourced from a fallback surface rather
    than the prospect's own domain, top-level `status = "partial"` and
    `suggestion` should name the swap.
- **Rationale.** companyctx is MIT and permanent-public. "Deterministic
  router" loses meaning if provenance is implicit.

## FM-11 — About-page URL not auto-discovered

- **Signature.** Brief references founder name from LinkedIn / Apollo
  but not from the site's about page; founder story is cited from a
  local magazine interview, not the vendor's own About surface.
- **Frequency.** 3+ transcripts, recurring pattern.
- **Evidence.**
  - `d100-run-waste-management-services-2026-04-21-e1155059-3079-4046-b663-18f8258a314f.md:2055`
- **Why it happens.** OSS extractors clean body text but do not
  *discover* which URL on a site is the About page. Small businesses
  hide it under "Our Story", "Meet the Team", or a nav dropdown.
- **Waterfall layer.** Attempt 1 — requires owned anchor-text heuristic
  code (not OSS).
- **Envelope mapping.**
  - When the `/` fetch succeeds but the about-page URL isn't found:
    per-provider `status = "degraded"` on a `site_about` sub-provider.
  - `suggestion = "about-page URL not auto-detected — pass
    --about-url=<path> or enable the footer anchor-text scan"`.

## FM-12 — Press / awards discovery needs search, not site fetch

- **Signature.** Briefs cite awards ("2024 NWRA national award"), press
  ("Forbes Homes #1 Best Gutter Guard 2023"), and credentials ("GentleCure
  SRT", "Inc. 5000 alum") — almost none of these come from the prospect's
  own site.
- **Frequency.** Most high-activity transcripts (10+). Roughly 50% of
  briefs depend on press-discovery content.
- **Evidence.**
  - `backfill-2026-04-17-command-message-d100-command-m-57f83f37.md:2296`
  - `backfill-2026-04-18-command-message-d100-command-m-9aea3234.md:854`
- **Waterfall layer.** Distinct from the three site-fetch attempts;
  press discovery is its own pipeline (search-API backed). The day-one
  plumbing is `mentions_brave_stub`; real coverage requires a keyed
  search provider.
- **Envelope mapping.**
  - `providers.mentions_<slug>: ProviderRunMetadata`.
  - No key configured: `status = "not_configured"`; top-level can still
    be `ok` because mentions are non-critical.
  - `suggestion = "press-release discovery is search-API-backed;
    configure a search provider key to fill mentions"`.

## FM-13 — Site-fetch timeouts / transient failures

- **Signature.** Would look like `"request timed out"`, `"connection
  reset"`, `"retry-after"` in transcripts.
- **Frequency.** **0 occurrences** on site fetches across the corpus.
  The only "timeout" hits were Apollo MCP rate-limit errors (out of
  scope) and the agent's own `sleep` helper.
- **Waterfall layer.** Attempt 1 — defensive default.
- **Envelope mapping.** Still support it
  (`ProviderRunMetadata.status = "failed"`,
  `error = "fetch timeout after Ns"`,
  `suggestion = "retry with longer timeout or escalate to smart-proxy"`)
  — but do **not** over-invest. Dominant Phase 1 failure mode is
  *blocks*, not *flakes*. Transcript evidence says aggressive retry /
  backoff is at best a tertiary concern. Attempt-2 escalation is the
  higher-leverage place to spend engineering.

## FM-14 — Homepage fetched but social handles not found

- **Signature.** `"Instagram and Facebook URLs / follower counts not
  surfaced"`; `"no IG surfaced in searches"`.
- **Frequency.** 3+ transcripts, 5+ prospects.
- **Evidence.**
  - `backfill-2026-04-17-command-message-d100-command-m-9bc12c4e.md:4020`
  - `backfill-2026-04-17-command-message-d100-command-m-9bc12c4e.md:4071`
- **Why it happens.** This is the canonical deterministic companyctx
  job: walk the homepage DOM for `a[href*="instagram.com"]`, etc., and
  cross-check against `extruct` `sameAs` metadata. Transcripts show
  agents giving up rather than doing this pass.
- **Waterfall layer.** Attempt 1 (`social_discovery_site`) — owned
  extraction heuristic.
- **Envelope mapping.**
  - When homepage fetch succeeds but no handle link is found:
    `social.<platform>.handle` absent; provider
    `ProviderRunMetadata.status = "degraded"`.
  - `suggestion = "no homepage-footer link; downstream may try
    business-name search on the platform"`.
- **Refinement note.** Distinct from FM-3 (handle known, count blocked)
  and from "handle misattribution" (wrong handle). These are three
  separate failure shapes; keeping them distinct matters for
  `expected.json` design.

## Taxonomy diff vs. prior research

`companyctx`'s design has been informed by two prior research files in
`noontide-projects` (local-only; not committed here). This section
captures how the transcript evidence compares.

### Confirmed

- **Primary-domain blocks** and **review-surface captchas / blocks**
  (carveout §7) confirmed — FM-1, FM-2, FM-4.
- **Low-info one-page sites** (carveout §7) confirmed — FM-7.
- **Services-list extraction is an OSS gap** (extraction-OSS §Gaps)
  confirmed — FM-6, universal across the corpus.
- **About-page auto-discovery is an OSS gap** (extraction-OSS §Gaps)
  confirmed — FM-11.
- **Press-release discovery is out of content-extraction scope**
  (extraction-OSS §Gaps) confirmed — FM-12 fires on ~50% of briefs.

### Refined

- **Google-captcha vs. Google-SPA (FM-4).** Prior taxonomy bundled
  these. Evidence shows the dominant Google failure is structural (GBP
  is JS-rendered + requires an API), not captcha. Envelope must
  distinguish `captcha_challenge` from `requires_direct_api` — they
  suggest different recoveries.
- **Social handle modes (FM-3, FM-14).** Prior taxonomy framed this as
  "handle misattribution." Transcripts show two separate modes:
  (a) handle not discovered at all (FM-14); (b) handle known but count
  blocked (FM-3). These are different envelope states.
- **Franchise / parent-brand ambiguity (FM-9).** Not previously
  enumerated. A distinct subcategory requiring per-location GBP
  place-id resolution.

### Contradicted / new

- **Site-fetch timeouts (FM-13) are essentially absent.** Prior
  instinct was to build retry/backoff first. Corpus evidence argues
  against it. Invest in Attempt-2 escalation, not Attempt-1 retry
  loops.
- **Upstream-vertical-misclassification (FM-8) is net new.** Suggests
  the envelope should emit a `vertical_detected` observation;
  firmographics lie often enough to matter.
- **Provenance-per-field (FM-10) is net new.** Transcripts silently mix
  homepage, BBB, Birdeye, press-wire, and search-snippet sources. MIT
  companyctx must carry per-field provenance for the "deterministic
  router" claim to hold up in review.
- **Under-construction / redirect shape (FM-5) is net new.** Low
  frequency, clean case — captured so fixtures cover it.

## Consumer notes

- **For `docs/EXTRACTION-STRATEGY.md`.** This register maps *failures*;
  the strategy doc maps *site shapes* to extraction approaches, then
  calls out the honest deterministic gaps. Read them together.
- **For `expected.json` authors.** Each fixture should encode which
  failure mode applies (if any) so the expected envelope's `status`,
  `error`, and `suggestion` fields are grounded, not guessed. A
  fixture for a Yelp-blocked prospect should ship the partial envelope
  this register specifies for FM-2, verbatim.
- **For provider implementations.** `ProviderRunMetadata.status`
  transitions are load-bearing. The enum is four-valued on purpose;
  FM-3 and FM-14 argue against collapsing `degraded` into `failed`.

## What this register does not do

- It does not quantify failure probability outside the observed
  niches. Eight niches is enough to ground the *shapes* of failure;
  it is not enough to forecast v0.2 SLAs.
- It does not prescribe retry policy, timeout values, or per-host
  rate-limit budgets. Those belong to provider implementations.
- It does not name vendors for Attempt 2 (smart-proxy) or specific
  OSS picks for new heuristics. Those decisions await measurement on
  the fixtures corpus (see `docs/PROVIDERS.md` and the zero-key
  strategy ADR for the naming rule).
