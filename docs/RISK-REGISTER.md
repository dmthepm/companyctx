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

Envelope enums and semantics (see `docs/SPEC.md` §56–78, §110–118):

- `ProviderRunMetadata.status` ∈ `{ok, degraded, failed, not_configured}`.
- Top-level envelope `status` ∈ `{ok, partial, degraded}`.
- `ok` — every required provider succeeded.
- `partial` — **at least one provider** returned `degraded`, `failed`,
  or `not_configured`, but `data` is still schema-conformant.
- `degraded` — **no provider succeeded**.
- Only fields declared in `docs/SPEC.md` §82–108 are envelope-available
  today. This register sticks to those. Cases where the honest mapping
  needs a field that doesn't exist yet are deferred to the
  [Schema-evolution proposals](#schema-evolution-proposals-non-normative)
  appendix and are **not** consumable by `#15` without that schema
  work landing first.

## Summary

| ID | Mode | Freq (transcripts) | Layer | Envelope shape (today's schema) |
|---|---|---|---|---|
| FM-1 | Homepage 403 / hard block by CDN anti-bot | 2 | Attempt 2 | Attempt-1 provider `failed`; top-level `partial` if any other provider succeeded, else `degraded` |
| FM-2 | Yelp 403 on server-rendered fetch | 4 | Attempt 3 (Yelp Fusion) | scraped-Yelp provider `failed` or Fusion `not_configured` → top `partial` |
| FM-3 | IG / FB follower-count scrape blocked | 4 | gap (no API without commercial key) | counts provider `degraded` → top `partial` |
| FM-4 | Google review count unreachable (GBP is JS-rendered) | 3 | Attempt 3 (Google Places) | `reviews_google_places` `not_configured` or `failed` → top `partial` |
| FM-5 | "Under construction" / redirect to parent brand | 1 | Attempt 1 | Attempt-1 provider `degraded`, top `partial`; identity distinction deferred (see schema-evolution §1) |
| FM-6 | Services/about content present but unstructured | 13/13 | extraction heuristic (Attempt 1) | `signals_site_heuristic` / services extractor `degraded` when `pages.services == []` → top `partial` |
| FM-7 | One-page template / brochureware site | 2+ | Attempt 1 (honest thin data) | per-provider `ok` on successful fetches; top `ok` (nulls on empty optional fields) or `partial` if a heuristic provider reports `degraded` |
| FM-8 | Upstream vertical tag disagrees with homepage-inferred vertical | 1 | Attempt 1 | today's envelope has no field for this; see schema-evolution §2 |
| FM-9 | Franchise / multi-location ambiguity | 2 | Attempt 3 (per-location GBP place-id) | `reviews_google_places` `degraded` → top `partial`; location-vs-aggregate distinction deferred to schema-evolution §3 |
| FM-10 | Secondary-source cascade without provenance | 5+ | cross-cutting | today's envelope carries per-*provider* provenance only; per-*field* provenance deferred to schema-evolution §4 |
| FM-11 | About-page URL not auto-discovered | 3+ | Attempt 1 (owned heuristic, not OSS) | `site_about` provider `degraded` → top `partial` |
| FM-12 | Press / awards discovery needs search, not site fetch | 10+ | separate provider (search-API) | `mentions_*` provider `not_configured` until a search-API key is set → top `partial` per SPEC §73 |
| FM-13 | Site-fetch timeouts / transient failures | 0 observed | Attempt 1 (defensive default only) | provider `failed` — do not over-invest |
| FM-14 | Homepage fetched but social handles not found | 3+ | Attempt 1 (footer anchor heuristic) | `social_discovery_site` `degraded` → top `partial` |

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
  - Attempt-1 provider (e.g. `site_text_trafilatura`):
    `ProviderRunMetadata.status = "failed"`,
    `error = "CDN anti-bot 403 on homepage"`,
    `suggestion = "retry via smart-proxy provider with residential
    egress"`.
  - If Attempt 2 rescues the homepage and no other provider degrades:
    top-level `status = "ok"`.
  - If Attempt 2 is `not_configured` and some other providers succeed
    (e.g. review / social providers on non-homepage surfaces): top-level
    `status = "partial"`; homepage-sourced `CompanyContext` fields
    (`pages.homepage_text`, `pages.about_text`, heuristic sub-fields)
    remain `None`; `error` and `suggestion` come from the primary
    degraded provider, typically `"configure a smart-proxy provider
    key"`.
  - If no provider succeeded: top-level `status = "degraded"`.

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
    `error = "yelp scrape blocked and yelp_fusion not configured"`,
    `suggestion = "configure Yelp Fusion direct-API key to bypass
    scraping"`.
  - `data.reviews` remains `None` (or populated from another review
    source if one succeeded) — missing reviews are encoded as `None`
    per `docs/SPEC.md` §126; downstream consumers read per-provider
    entries in `provenance` to see *why*.

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
  - Top-level `status = "partial"`; `data.reviews` left `None` (or
    carrying a non-Google source if one succeeded). The provenance
    entry is where downstream reads *why* Google wasn't filled.

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
- **Waterfall layer.** Attempt 1 — the fetch itself doesn't need a new
  layer; the envelope needs a way to flag brand identity.
- **Envelope mapping (today's schema).**
  - Attempt-1 fetcher: `ProviderRunMetadata.status = "degraded"` when
    the effective URL differs from the requested URL across a
    second-level-domain boundary. Detection sits in the fetcher; the
    degraded status is the only signal today's envelope can emit.
  - Top-level `status = "partial"`,
    `error = "cross-brand redirect: extracted data may describe the
    parent brand, not this prospect"`,
    `suggestion = "pass the parent-brand domain explicitly if the
    parent is the intended prospect, or skip"`.
- **Schema gap.** Surfacing the requested-vs-effective URL pair is a
  schema evolution — see
  [§1 Identity preservation on redirect](#1-identity-preservation-on-redirect).
  Until that lands, downstream consumers only see the degraded status
  and the `error` string; they cannot tell *which* URL the extractor
  followed.

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
  - Providers that succeed at their extractor job return
    `ProviderRunMetadata.status = "ok"` — the fetch worked; the site
    just has nothing to extract. Empty-but-extracted is valid data.
  - Providers whose job is to *find* a specific sub-field that isn't
    present (e.g. `social_discovery_site` finds no handles;
    `signals_site_heuristic` finds no `team_size_claim`) can
    legitimately return `status = "degraded"` with an `error` explaining
    that the source content didn't contain the target.
  - Top-level `status`:
    - `"ok"` if every provider returned `ok` (empty outputs are valid).
    - `"partial"` if any heuristic provider reported `degraded` because
      the heuristic didn't hit — per SPEC §73, `partial` requires at
      least one provider to be degraded / failed / not_configured.
  - **Do not map the fetch itself to `degraded` or `failed`.** The
    distinction between "site blocked us" (FM-1) and "site had nothing"
    (FM-7) is load-bearing; it lives in the per-provider `status`
    values, not in a flattened quality score.

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
- **Waterfall layer.** Attempt 1 resolves the observation itself.
- **Envelope mapping (today's schema).** There is **no field today**
  that can carry a vertical observation or the mismatch signal.
  `HeuristicSignals.tech_vs_claim_mismatches` (SPEC §107) is the
  closest-shaped slot but it's narrowly scoped to *tech vs claim*, not
  vertical classification. The transcript shows a real failure; the
  v0.1 envelope can't surface it.
- **Schema gap.** See
  [§2 Vertical observation and firmographics-mismatch warning](#2-vertical-observation-and-firmographics-mismatch-warning).
  Until that lands, `companyctx` has no way to propagate this signal —
  the synthesis layer has to infer it from `pages.homepage_text`
  unaided.

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
- **Envelope mapping (today's schema).**
  - `reviews_google_places` with no per-location place-id:
    `ProviderRunMetadata.status = "degraded"`,
    `error = "only parent-brand aggregate reachable; location-level
    reviews require per-location GBP place-id"`,
    `suggestion = "pass the specific GBP place-id for this location"`.
  - Top-level `status = "partial"`.
- **Schema gap.** `ReviewSignals` (SPEC §91–94) has no way to mark a
  value as *location-specific* vs *parent-brand aggregate*; callers
  can't tell them apart. See
  [§3 Review-scope distinction (location vs parent-brand aggregate)](#3-review-scope-distinction-location-vs-parent-brand-aggregate).

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
- **Envelope mapping (today's schema).** The v0.1 envelope carries
  provenance at the *provider* level via `provenance: dict[slug,
  ProviderRunMetadata]` (SPEC §61–64, §110–118). A `ReviewSignals`
  value carries `source: str` naming the provider slug that produced
  it (SPEC §94). There is **no per-field provenance** that can
  describe "this `services` entry came from the homepage but this one
  came from a third-party aggregator." Today, if a provider fell back
  across surfaces internally, that fact is flattened.
- **Schema gap.** See
  [§4 Per-field provenance](#4-per-field-provenance). Until it lands,
  downstream consumers can only see *which provider* produced a
  value, not *which surface within that provider's reach*.
- **Rationale.** `companyctx` is MIT and permanent-public.
  "Deterministic router" carries real weight only when provenance is
  explicit enough for reviewers to audit. The transcript evidence
  makes a strong case for field-level provenance; the schema change is
  non-trivial and belongs in its own issue, not this PR.

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
    the about-page provider (the provider owning `pages.about_text`)
    returns `ProviderRunMetadata.status = "degraded"` with
    `error = "about-page URL not discoverable via anchor heuristics"`.
  - Top-level `status = "partial"`; `data.pages.about_text` left
    `None` (it's already declared nullable in SPEC §88).
  - `suggestion = "about-page URL not auto-detected; synthesis can
    rely on homepage_text alone or pass an explicit about-URL hint"` —
    a user-facing hint flag is a CLI evolution, not assumed here.

## FM-12 — Press / awards discovery needs search, not site fetch

- **Signature.** Briefs cite awards, media mentions, industry
  rankings, and external accreditation — sourced via web search rather
  than the prospect's own domain. The D100 skill's own Phase 1
  instructions explicitly separate this into a dedicated
  "web search" step for "media mentions, awards, community presence"
  distinct from the "website fetch" step.
- **Frequency.** Appears in most high-activity transcripts. The skill
  instruction itself ("Web search … for reviews (Google rating +
  count), media mentions, awards, community presence") is echoed
  verbatim across 5+ batch transcripts, and the briefs that result
  consistently include award / press content that did not come from
  the prospect's own domain.
- **Evidence.**
  - `backfill-2026-04-16-command-message-d100-command-m-167f63bc.md:1609`
    — brief summary for one prospect lists multiple press / award /
    accreditation signals (a national-magazine category ranking, a
    BBB rating, an industry list mention, and a national rank) all
    derived from web search, not the vendor's own site.
  - `backfill-2026-04-18-command-message-d100-command-m-9aea3234.md:794`
    — agent explicitly records that it "verified … via fresh web
    research" to fill award content for a brief.
  - `backfill-2026-04-18-command-message-d100-command-m-9aea3234.md:403`
    and siblings — the skill reference itself codifies a search-based
    step for awards / media mentions as distinct from site fetching.
- **Waterfall layer.** Distinct from the three site-fetch attempts;
  press discovery is its own pipeline (search-API backed). The day-one
  plumbing is `mentions_brave_stub`; real coverage requires a keyed
  search provider.
- **Envelope mapping.**
  - `provenance["mentions_<slug>"]: ProviderRunMetadata` carries the
    per-provider status for press discovery.
  - No key configured: `ProviderRunMetadata.status =
    "not_configured"`. Per SPEC §73, `not_configured` on any provider
    forces top-level `status = "partial"` — the envelope tells the
    caller "this run is missing press coverage because no search key
    is set." The summary row and this body now agree on that.
  - `error` names the missing capability
    (`"press/awards discovery requires a configured search provider"`),
    `suggestion = "configure a search provider API key to fill
    mentions"`.
  - `data.mentions` remains `None` (optional per SPEC §98).
  - **Design note.** This means a clean zero-key install is
    `partial`-by-default on every run until a search key is set. That
    is intentional: silent absence of press coverage is the exact
    failure the D100 transcripts show — the envelope should signal it
    loudly, not hide it.

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
  is JS-rendered + requires an API), not captcha. In today's envelope
  the distinction lives in the `error` string + `suggestion` on the
  degraded provider; recoveries (smart-proxy vs API-key configuration)
  differ, so the suggestion strings must not be collapsed.
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
- **Upstream-vertical-misclassification (FM-8) is net new.** The v0.1
  envelope cannot propagate this signal; see schema-evolution §2.
- **Provenance-per-field (FM-10) is net new.** Transcripts silently mix
  homepage, BBB, Birdeye, press-wire, and search-snippet sources. The
  v0.1 envelope carries provenance per-provider but not per-field; see
  schema-evolution §4.
- **Under-construction / redirect shape (FM-5) is net new.** Low
  frequency, clean case — captured so fixtures cover it.

## Consumer notes

- **For `docs/EXTRACTION-STRATEGY.md`.** This register maps *failures*;
  the strategy doc maps *site shapes* to extraction approaches, then
  calls out the honest deterministic gaps. Read them together.
- **For `expected.json` authors.** Each fixture should encode which
  failure mode applies (if any) so the expected envelope's `status`,
  `error`, and `suggestion` fields are grounded, not guessed. Use
  **only** fields declared in `docs/SPEC.md` §82–108. The
  schema-evolution proposals below are *not* envelope-available yet
  and cannot be consumed by fixtures until their own issues land.
- **For provider implementations.** `ProviderRunMetadata.status`
  transitions are load-bearing. The enum is four-valued on purpose;
  FM-3 and FM-14 argue against collapsing `degraded` into `failed`.

## Schema-evolution proposals (non-normative)

Four transcript-grounded modes cannot be honestly represented by the
v0.1 envelope. Each is captured here so that follow-up issues can
propose concrete schema changes. **Nothing in this section is usable by
`#15` or by fixtures until a separate PR ratifies the schema change.**

### §1 Identity preservation on redirect

**Problem.** FM-5 — when a fetch follows a cross-SLD redirect, the
extracted `CompanyContext` may describe a different legal entity
(franchise parent) than the one the caller asked about. The envelope
has no field that preserves the requested-vs-effective URL pair, so
downstream consumers cannot tell.

**Candidate shape.** Add something like `pages.requested_url` and
`pages.effective_url` (both `str`) to `SiteSignals`, or a top-level
`data.identity` struct. Emit a `ProviderRunMetadata` error when the
SLDs differ.

**Follow-up.** Worth its own issue.

### §2 Vertical observation and firmographics-mismatch warning

**Problem.** FM-8 — the homepage-inferred vertical (e.g. "portable
sanitation") can disagree with an upstream firmographics tag (e.g.
Apollo's "real estate"). The envelope has no field that carries an
inferred vertical or a mismatch flag. `tech_vs_claim_mismatches` in
`HeuristicSignals` has the right *shape* (a list of observation
strings) but is domain-restricted to tech / positioning.

**Candidate shape.** Either (a) broaden `tech_vs_claim_mismatches`
into a more generic `observations: list[str]` under
`HeuristicSignals`, or (b) add a dedicated
`HeuristicSignals.vertical_inferred: str | None` — keeping it an
observation, per the `docs/SPEC.md` §121–124 "raw observations only"
rule.

**Follow-up.** Worth its own issue.

### §3 Review-scope distinction (location vs parent-brand aggregate)

**Problem.** FM-9 — `ReviewSignals.count` and `.rating` are flat
numbers. A franchise child site exposes parent-brand aggregates on its
homepage; the location's own numbers live in a separate GBP place-id.
Today the envelope cannot distinguish them, so a synthesis consumer
can confidently write "5.0 rating, 747 reviews" about what is really
the parent brand.

**Candidate shape.** Add
`ReviewSignals.scope: "location" | "parent_brand_aggregate"` (or
equivalent), and treat aggregate-only runs as `partial`.

**Follow-up.** Worth its own issue.

### §4 Per-field provenance

**Problem.** FM-10 — today's envelope carries provenance at the
*provider* level. Within a single provider call, a fallback across
surfaces (homepage → BBB → Birdeye → press wire) collapses to one
`ProviderRunMetadata` entry. The "deterministic router" positioning
argues for making the per-field surface explicit.

**Candidate shape.** Either wrap values that can come from multiple
surfaces in a struct `{value, source_url, extracted_at}`, or extend
`provenance` with per-path keys. Schema change is non-trivial and
deserves a focused ADR; transcript evidence (FM-1, FM-2, FM-4 all
trigger FM-10) makes the case strong.

**Follow-up.** Worth its own issue.

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

## Candidate refinements — needs vertical-diverse replication

This section is non-normative. Entries here are observations from a
single measurement that do not yet meet the bar for editing the main
register body (typically: ≥ 5% rate AND an identified mechanism).
They stay here until a follow-up run on a different vertical either
confirms or refutes the observation.

### FM-13 — 3% observed, medical/aesthetic only, no mechanism

The 2026-04-21 100-site durability run
([`fixtures/durability-report-2026-04-21.md`](../fixtures/durability-report-2026-04-21.md))
measured 3 / 100 = **3%** FM-13 timeouts against Joel's medical /
aesthetic SMB cohort. The register body says "0 observed … do not
over-invest" based on the D100 log-mining corpus (gutter / roofing /
IV / waste-management). **Three caveats keep this out of the main
body:**

1. 3% is below the 5% refinement threshold.
2. No shared fingerprint (CDN / CMS / hosting) identified from three
   data points.
3. The sample is 100% medical / aesthetic; the register was mined from
   unrelated verticals. A gutter / roofing / waste-management rerun is
   needed to tell apart a vertical-specific artifact from baseline
   network weather.

If a vertical-diverse rerun confirms a ≥ 5% rate **and** identifies a
shared mechanism (e.g. a specific CMS fingerprint or hosting pattern),
the FM-13 main body should be re-weighted from "do not over-invest" to
a concrete "invest in N-second retry with backoff on timeout" rule.
Until then, Attempt-2 escalation remains the higher-leverage place to
spend engineering.
