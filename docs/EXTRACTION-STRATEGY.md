# Extraction Strategy

Which content extractors handle which site shapes, and where deterministic
extraction is **not** feasible — so the envelope flags `partial` honestly
instead of pretending the fetch succeeded.

Companion to `docs/RISK-REGISTER.md` (failure modes × envelope surfaces)
and `docs/ZERO-KEY.md` (zero-key coverage matrix). Read them together.

## Mental model

The Deterministic Waterfall (`docs/ARCHITECTURE.md`) has three attempts.
Each attempt operates on a *class of site shapes* — not on individual
domains. The rules below bind site shapes to layers so an implementer can
answer "which provider should handle this?" without case-by-case
reasoning.

- **Attempt 1 — Zero-Key Stealth.** TLS-impersonation HTTP fetcher
  (`curl_cffi`, pinned `chrome146`) + `trafilatura` primary / `readability-lxml`
  fallback + `extruct` metadata + `BeautifulSoup`-based heuristics. No
  keys, no cost. Handles the majority case plus the long tail of thin /
  brochureware sites *honestly* (i.e. emits low-confidence envelopes
  rather than pretending).
- **Attempt 2 — Smart-Proxy Provider.** User-keyed residential-proxy /
  headless-browser provider behind the `SmartProxyProvider` interface.
  Vendor-agnostic; `companyctx` ships the contract, not a specific
  vendor. Engages when Attempt 1 hits a CDN anti-bot block or a site
  requires rendered HTML.
- **Attempt 3 — Direct-API Provider.** ToS-safe review / social-counts
  APIs (`reviews_google_places`, `reviews_yelp_fusion`,
  `social_counts_youtube`). Fills review counts, ratings, and follower
  counts where no fetch-based approach is deterministic.

Every attempt emits the same envelope shape. The top-level `status`
aggregates provider-level outcomes.

## Site-shape map

Six shapes appear in the partner-pipeline transcripts mined for this
doc (evidence catalog in `docs/RISK-REGISTER.md`). Each row binds a
shape to the
Waterfall layer that should handle it and names the honest deterministic
gap.

| Site shape | How to recognize it | Primary approach | Waterfall layer | Honest deterministic gap |
|---|---|---|---|---|
| **Server-rendered static HTML** — the majority case: WordPress / Squarespace / Wix / Webflow / small-agency custom | `GET /` returns 200, HTML body ≥ 2 KB of meaningful text, no JS required for content | TLS-impersonation fetch → `trafilatura` (primary) / `readability-lxml` (fallback) → `extruct` for JSON-LD / OG / `sameAs` → `BeautifulSoup` footer scan for social anchors | Attempt 1 | **Services-list extraction remains heuristic.** No OSS cleanly produces `services: list[str]` from clean body text (FM-6). **About-page auto-discovery is owned companyctx code** (FM-11), not OSS. Both flag `ProviderRunMetadata.status = "degraded"` on the affected sub-provider so the envelope signals "raw text captured; structured sub-fields empty." |
| **CDN-anti-bot-fronted** — returns 403 / challenge page on `GET /` | 403 on plain fetch; WAF challenge pages; Cloudflare / DataDome / Akamai / PerimeterX markers in response headers or body | Attempt 1 fails fast; escalate to Attempt 2 (smart-proxy with residential egress) | Attempt 2 | **Without a user-supplied smart-proxy key, this prospect is permanently degraded on homepage-sourced fields** (FM-1). Correct envelope: Attempt 1 → `failed`; Attempt 2 → `not_configured` unless keyed; top-level → `partial` with `error.code = "blocked_by_antibot"` and `error.suggestion = "configure a smart-proxy provider key"`. |
| **JS-rendered / SPA surfaces** — Google Business Profile map panel, some franchise-directory inner pages, certain Squarespace-JS variants | `GET /` returns a minimal shell; body < 2 KB meaningful text; visible text on the rendered page is absent from the fetched HTML | Detect low-text-density on the Attempt-1 response → bail early rather than emit half-junk. For *review* fields on JS surfaces with a direct API (Google Places, YouTube Data), prefer Attempt 3. For SPAs without a direct API, emit `degraded` honestly — a headless-browser renderer is **not in the v0.1 scope** per the zero-key ADR | Attempt 3 where a direct API exists; gap otherwise | **Genuine gap for SPA sites without an API.** Transcripts show these are rare in the partner's niches (~5–10% estimate, dominant case is Google Maps panels which *do* have an API); deferring a headless-browser renderer is defensible for v0.1. Revisit if fixtures-corpus measurement shows > 20% of ICP prospects on SPA shapes. |
| **Review / directory aggregator** — Yelp, Google Business, Houzz, Angi, HomeAdvisor, Birdeye, BBB | Fetch against these domains returns 403 or a thin shell (FM-2, FM-4) | Prefer the **direct API** for Yelp (Yelp Fusion) and Google (Google Places). For the long tail (Birdeye, HomeAdvisor, Angi, BBB), only Attempt 2 helps — none publish a public API. | Attempt 3 for Yelp + Google; Attempt 2 for the long tail | **Long-tail aggregators have no API** — we're permanently at smart-proxy quality there. When Attempt 2 is `not_configured`, envelope emits `status = "partial"` with `data.reviews` left `None` (or populated from a surface that did succeed) and `error.suggestion` naming the first aggregator that's configurable. |
| **Social-platform profile** — Instagram, Facebook, LinkedIn, TikTok, YouTube | Fetching the platform directly either 403s or returns a login-wall shell; follower counts render client-side | **Handle discovery is Attempt 1** (footer anchors + `extruct sameAs`) — companyctx owns that heuristic. **Counts are Attempt 3 for YouTube** (YouTube Data API); **a hard gap for IG / FB / TikTok** without commercial authenticated-graph access (FM-3). | Attempt 1 for handles; Attempt 3 for YouTube counts; gap for IG / FB / TikTok counts | **IG / FB / TikTok follower counts are a permanent `degraded` path.** Document it, don't hide it. Envelope reports: handle present in `social.handles` (Attempt-1 provider `ok`), count absent from `social.follower_counts` (counts provider `degraded`), top-level `partial`, `error.suggestion = "IG/FB/TikTok follower counts require authenticated social-graph access"`. |
| **Brochureware / one-page template / under-construction / parked / Facebook-only** | `GET /` returns 200, HTML parses cleanly, but meaningful text is < 2 KB; no services page; no team page; sometimes a 301 to a parent brand (FM-5); sometimes no domain at all (Facebook-only business) | Attempt 1 handles it; the honest behavior is to **emit the thin data and let synthesis handle it upstream** — optional envelope fields are nullable (SPEC §126) | Attempt 1 | No gap on the fetch itself. Correct envelope is driven entirely by per-provider status: fetchers that succeeded at their extractor job return `ok` (empty outputs are valid); a heuristic provider that expected to find e.g. a services list or `team_size_claim` and couldn't can legitimately return `degraded`, which then maps to top-level `partial` per SPEC §73. The distinction between "site blocked us" (FM-1) and "site had nothing" (FM-7) lives in the per-provider `ProviderRunMetadata.status` values; **do not collapse them**. See RISK-REGISTER FM-7 for the full mapping. |

## Attempt-by-attempt responsibilities

### Attempt 1 — Zero-Key Stealth

**Owns every site shape on first contact.** Its job isn't to succeed
everywhere; it's to succeed on the majority case (server-rendered
static HTML) and **fail diagnostically** on the rest so later attempts
can recover with a meaningful signal.

Day-one providers for Attempt 1:

- `site_text_trafilatura` — primary body-text extractor.
- `site_text_readability` — bus-factor fallback. Wired day one per
  `docs/SPEC.md` so single-extractor regressions don't silently cost
  the envelope.
- `site_meta_extruct` — JSON-LD / OpenGraph / Twitter cards / `sameAs`
  social handle discovery.
- `social_discovery_site` — `BeautifulSoup` footer scan for
  `a[href*="instagram.com"]` etc., cross-checked against
  `extruct sameAs`. Owns the FM-14 fix.
- `signals_site_heuristic` — copyright year, last-blog-post, team-size
  claim regex, tech-stack fingerprint.

Known gaps Attempt 1 cannot close deterministically:

- **Services-list extraction** (FM-6). The envelope carries
  `pages.services: list[str]`; when the heuristic doesn't hit, emit an
  empty list with `ProviderRunMetadata.status = "degraded"` and
  `error = "services list needs LLM synthesis from raw text"` (the per-
  provider `ProviderRunMetadata.error`; the envelope-level
  `EnvelopeError` is aggregated separately).
  Do **not** attempt a half-heuristic that produces a noisy list —
  downstream synthesis is better served by honest emptiness.
- **About-page URL auto-discovery** (FM-11). Attempt 1 owns an
  anchor-text heuristic (`about`, `about-us`, `our-story`, `team`,
  `meet-the-`). When it doesn't find a match, emit `degraded` on the
  about sub-provider, not a silent null.
- **Effective-vs-requested URL** (FM-5). When a redirect crosses a
  brand boundary (SLD mismatch), emit `ProviderRunMetadata.status =
  "degraded"` and name the mismatch in the `error` string. The v0.1
  envelope has no field for requested-vs-effective URL; surfacing that
  pair is a schema evolution (see
  [RISK-REGISTER §1](RISK-REGISTER.md#1-identity-preservation-on-redirect)).
  Until that lands, the degraded status + error string is the only
  signal the envelope can carry.

Heuristic for escalating to Attempt 2: **text density.** If
`len(extracted_text) < 2000` on a 200 response, or the response status
is 403/451/challenge-page-detected, hand off. Do not enter retry loops
(FM-13 evidence: site-fetch timeouts are essentially absent from the
corpus; aggressive retry is not the load-bearing investment).

### Attempt 2 — Smart-Proxy Provider

**Owns the CDN-anti-bot shape.** Vendor-agnostic interface; user
supplies credentials (residential-proxy, headless-browser, or hybrid).
The specific vendor is not named in public docs until a fixtures-corpus
spike measures candidates (naming rule in `CLAUDE.md` / workspace
preferences).

Behavior contract:

- `not_configured` status when no key is set — envelope still emits,
  top-level `status = "partial"` with `error.code =
  "misconfigured_provider"`; `error.suggestion` names the configuration
  step.
- `ok` when it rescues a fetch that Attempt 1 failed; the envelope
  payload and extractors are identical to Attempt 1's shape.
- `failed` when configured but blocked (residential IP rotated to a
  flagged pool, challenge page not cleared). Envelope escalates to
  Attempt 3 if one applies, or settles on `partial` / `degraded`.

Attempt 2 does **not** attempt JS rendering beyond what the user's
configured provider exposes. If a prospect needs a headless browser and
the user's `SmartProxyProvider` doesn't do one, the envelope emits
`degraded` on JS-dependent fields with `suggestion` naming the gap.

### Attempt 3 — Direct-API Provider

**Owns review counts, ratings, and authenticated-graph follower counts
where a public API exists.** User-keyed; env-gated; missing-key
provider statuses are `not_configured`, not `failed`.

Day-one providers for Attempt 3:

- `reviews_google_places` — solves FM-4 and the specific-location
  subcase of FM-9 (requires the location's GBP place-id, not the brand
  name).
- `reviews_yelp_fusion` — solves FM-2. The single strongest
  transcript-grounded argument for Attempt 3 existing at all.
- `social_counts_youtube` — YouTube Data API `channels.list` (ToS-safe);
  the one social-platform with a deterministic follower-count path.

Attempt 3 does **not** try to cover IG / FB / TikTok. The envelope
documents the gap (FM-3) and emits `degraded` on the per-platform
counts provider rather than hiding it.

## Cross-cutting rules

- **Provenance today is per-provider, not per-field** (FM-10). The
  v0.1 envelope carries `provenance: dict[slug, ProviderRunMetadata]`
  (SPEC §61–64); there is no per-field provenance. Field-level
  provenance is a deferred schema evolution
  ([RISK-REGISTER §4](RISK-REGISTER.md#4-per-field-provenance));
  until it lands, each provider is responsible for internal fallback
  transparency via its `error` string and for not silently mixing
  primary-domain facts with third-party aggregator facts.
- **Vertical observation is a deferred schema change** (FM-8). The
  v0.1 envelope has no field for it; the synthesis layer has to
  infer. See
  [RISK-REGISTER §2](RISK-REGISTER.md#2-vertical-observation-and-firmographics-mismatch-warning).
- **Press / awards is a separate pipeline** (FM-12). The
  site-extraction layer doesn't own it. `mentions_brave_stub` ships as
  plumbing; coverage requires a keyed search provider. Most briefs
  depend on press-discovery content, so the pipeline can't be
  deferred indefinitely — but it doesn't belong to Attempts 1–3.
- **No `partial` from half-heuristics.** When a structured sub-field
  can't be extracted cleanly, emit empty + `degraded`, not a noisy
  value. Downstream synthesis is a better consumer of honest absence
  than of confident garbage.
- **No vendor names.** Public docs (this one, `PROVIDERS.md`, accepted
  ADRs) name a vendor for a new layer only after a fixtures-corpus
  spike measures it. Research files and proposed ADRs can list
  candidates with a "pending spike" banner. Current accepted vendor
  picks: `curl_cffi` for TLS impersonation
  (`decisions/2026-04-20-zero-key-stealth-strategy.md`); `trafilatura`
  + `readability-lxml` + `extruct` as Attempt-1 extractors
  (`docs/SPEC.md`); Google Places / Yelp Fusion / YouTube Data API as
  Attempt-3 providers (`docs/SPEC.md`). Everything else in this doc is
  a category, not a pick.

## Site-shape frequencies in the partner corpus

Rough distribution across the 13 heavy transcripts mined — not an SLA
forecast, a sizing hint for the v0.1 fixtures corpus:

| Shape | Rough share of prospects |
|---|---|
| Server-rendered static HTML | ~70% |
| Review / directory aggregator (for the reviews provider) | universal — every prospect hits ≥ 1 |
| Social-platform profile (for social handles) | ~90% have ≥ 1 discoverable handle |
| CDN-anti-bot-fronted | 1–3% — low count, 100% unrecoverable without Attempt 2 |
| JS-rendered / SPA (excluding Google Maps panels) | ~5–10% |
| Brochureware / one-page / parked | ~10–15% |

Fixtures-corpus implication: a 5-fixture baseline (sized to
`expected.json` validation in issue #15) should cover
server-rendered + aggregator-dependent + social-discoverable +
CDN-blocked + brochureware. The five cases map one-to-one to the top
five rows above.

## References

- `docs/SPEC.md` — envelope contract and provider-plugin interface.
- `docs/ARCHITECTURE.md` — the Deterministic Waterfall diagram.
- `docs/ZERO-KEY.md` — honest Attempt-1 coverage matrix.
- `docs/RISK-REGISTER.md` — failure modes × envelope mapping, cited per
  mode to the partner transcripts that evidenced each one.
- `docs/PROVIDERS.md` — day-one provider list with cost hints.
