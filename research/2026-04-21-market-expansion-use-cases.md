---
type: research
date: 2026-04-21
topic: market-expansion use cases for companyctx beyond the D100 cold-email wedge
category: go-to-market
status: living document
linked_issues:
  - https://github.com/dmthepm/companyctx/issues/36
linked_decisions:
  - decisions/2026-04-20-name-change-to-companyctx.md
  - decisions/2026-04-20-skill-md-not-mcp.md
---

# Market-expansion use cases

## One-sentence summary

`companyctx` is a primitive, not a product, and the same deterministic
envelope that powers the D100 cold-email wedge also plugs cleanly into
inbound CRM enrichment, private-equity rollup sourcing, automated
competitor tracking, and agentic customer support — each of which is
worth codifying as proof that the primitive generalizes without
widening the v0.1 scope.

## Framing

The main `README.md` stays locked to the D100 cold-outreach wedge. That
is the first paid pipeline (`joel-req/new-signal-studio`) and therefore
the product message the repo leads with. Adjacent use cases belong here,
in `research/`, and get proven in `examples/` when the time comes, so
the wedge does not dilute and the broader map does not get lost in chat.

Two load-bearing ideas sit above the use-case list:

1. **The primitive is not the product.** The CLI is a muscle. The value
   to an end buyer lives in the playbooks, orchestration, prompts, and
   implementation expertise layered on top — which is deliberately not
   what this repo ships. See the companion strategy note,
   `research/2026-04-21-funnel-and-monetization-strategy.md`.
2. **Build in public is part of the channel.** Founders and developer-
   operators respond to watching market reasoning and use-case
   exploration happen in the open. The repo is where this thinking
   lives permanently; social / community channels are where it gets
   distributed as hooks, examples, and narratives. Codifying here
   preserves the evidence trail the distribution surface points back to.

## Guardrail

The repo should show the chessboard without losing the wedge. In
practice:

- `README.md` stays tightly focused on the D100 cold-email wedge and
  the deterministic-envelope contract.
- `research/` holds the market-expansion reasoning and positioning
  exploration.
- `examples/` proves the use cases with small scripts, because code is
  the marketing. Examples are proof-of-concept, not long-form copy.
- No adjacent use case gets into the README until it has at least one
  working example and an operator willing to say it works.

## Use cases

Each entry lists the target user, the pain, the deterministic flow, and
why the use case matters to `companyctx`'s position in the market. The
flows are illustrative — they describe the shape of the integration,
not shipped code.

### 1. Inbound lead enrichment

- **User.** RevOps managers and growth marketers running lifecycle on
  inbound B2B leads.
- **Pain.** A lead submits only an email. The sales or lifecycle team
  needs company context — services, size, stack, review footprint —
  immediately, and the standing options are paid legacy enrichment
  vendors whose pricing, latency, and data model were built for the
  pre-agent era.
- **Flow.**
  1. Form-fill webhook fires on lead submission.
  2. Extract the domain from the submitted email.
  3. Run `companyctx fetch <domain> --json`.
  4. Map the schema-locked JSON into the CRM company record; branch on
     `status` to decide whether to enqueue a re-fetch or to route the
     lead to a manual-review queue.
- **Why it matters.** This positions `companyctx` as a local-first
  alternative to legacy enrichment vendors (Clearbit-class, ZoomInfo-
  class) in the agent era. Deterministic JSON, no per-call billing on
  the zero-key path, and a schema built to be *inputs for synthesis* —
  which is exactly the wedge the incumbents were not built for.

### 2. Private equity / SMB rollup sourcing

- **User.** Micro-PE firms, search funds, and M&A analysts screening
  local-service businesses for acquisition.
- **Pain.** The most interesting rollup targets tend to be businesses
  with strong local reputation but weak tech and marketing. Manually
  screening those — pulling review counts, checking copyright years,
  looking for stale blogs, sniffing for a dated stack — is slow and
  labor-intensive, and does not scale past a hundred domains.
- **Flow.**
  1. Seed a list of candidate domains (scrape a category page, buy a
     list, pull from a county registry, etc.).
  2. Run `companyctx fetch <domain> --json` across the list; cache hits
     accumulate in Vertical Memory as a byproduct.
  3. Filter the resulting JSON on deterministic acquisition signals:
     review count and rating (e.g. `reviews.count >= 100` AND
     `reviews.rating >= 4.5`), stale copyright year, tech-stack
     markers (WordPress / Elementor / legacy CMSes), absence of recent
     blog posts, small team-size claims.
  4. Rank, shortlist, and hand off to a human analyst for diligence.
- **Why it matters.** This is a materially larger use case than
  outbound enrichment and demonstrates that the same envelope drives
  acquisition research, not just sales motion. It also exercises
  Vertical Memory as a compound asset — the same cache that speeds
  D100 outreach doubles as a queryable SMB dataset for deal flow.

### 3. Automated competitor tracking

- **User.** Founders and product marketers tracking a handful of
  competitors.
- **Pain.** Competitive tracking today is either manual (somebody
  re-reads five sites every Monday) or done via bloated tooling that
  treats this as an enterprise problem. Freeform LLM summarization of
  raw HTML is brittle and produces false positives — the "competitor
  relaunched their homepage" alert that turns out to be a CSS class
  rename.
- **Flow.**
  1. On a daily schedule, run `companyctx fetch <competitor-domain>
     --refresh --json` for each tracked domain.
  2. Diff the new JSON against the prior run stored in Vertical Memory
     (keyed on `data.site` + `data.fetched_at`).
  3. Filter the diff to business-meaningful fields — new services,
     review-count step changes, tech-stack additions, copyright-year
     updates, new social handles — rather than arbitrary HTML churn.
  4. Route the distilled change set to a synthesis step (LLM, Slack
     webhook, internal digest) and emit an alert.
- **Why it matters.** Deterministic JSON with an `extra="forbid"`
  schema means the diff is stable by construction. Fewer false
  positives than HTML-scraping approaches and far fewer than
  "ask the model to summarize what changed."

### 4. Dynamic agentic customer support

- **User.** Customer success teams and AI support builders operating
  B2B support bots or assisted-live agents.
- **Pain.** Support agents (human or AI) answer generically when they
  lack business and stack context about the customer on the other end
  of the ticket. Pulling that context is either a manual lookup
  (expensive, slow) or a brittle integration with a legacy enrichment
  vendor (expensive, rate-limited, not agent-shaped).
- **Flow.**
  1. Infer the customer's company domain from the support ticket
     metadata (auth'd user email, billing account, etc.).
  2. Run `companyctx fetch <domain> --from-cache --json`; fall back to
     a live fetch if the cache misses and freshness matters.
  3. Inject the structured context (services, stack, rough size, review
     posture) into the support agent's prompt.
  4. The agent now answers with business-aware specificity instead of
     boilerplate.
- **Why it matters.** This upgrades a generic support bot into
  something closer to a solutions engineer. It also cleanly matches
  the brains-and-muscles pattern: the support agent is the brain,
  `companyctx` is the muscle that fetches deterministic context, and
  the envelope is the contract between them.

## Follow-on examples (future milestone)

The issue explicitly defers implementation. These filenames are
reserved for when we prove the use cases with code:

- `examples/pe-rollup-screener.sh` — pipes a domain list through
  `companyctx` and `jq` to filter on rollup signals. Exercises use
  case 2.
- `examples/competitor-tracker.sh` — daily refresh + JSON diff, with
  a hand-off to whatever synthesis step the operator prefers.
  Exercises use case 3.
- `examples/hubspot-enrichment.py` — webhook → domain → envelope →
  CRM company-record update. Exercises use case 1. The HubSpot
  choice is illustrative; the pattern generalizes across CRMs.
- Customer-support example is deferred until at least one operator is
  actively integrating `companyctx` into a support-agent prompt. The
  shape of the example depends on their agent framework, which the
  repo should not prescribe.

Each example, when it lands, should stay small enough to read in a
sitting and should show only the integration shape, not a production
harness.

## Distribution notes

Preserved here because distribution hooks frequently point back to this
document for the underlying reasoning:

- **The "pivot" narrative** — built for outbound, realized the same
  primitive replaces a paid legacy enrichment vendor on inbound.
- **The "enemy" narrative** — paying legacy enrichment vendors in the
  agent era is increasingly hard to justify, because the incumbents'
  data model was built for human dashboards, not for JSON-in / JSON-
  out agent pipelines.

Social distribution surfaces these as hooks; the repo is the receipt.

## What this document does not do

- It does **not** commit `companyctx` to shipping features for any of
  the four use cases in v0.1. The v0.1 scope stays on the D100 wedge.
- It does **not** name any provider vendor the tool would integrate
  with. The rule that public docs do not name vendors before
  measurement applies here. Legacy enrichment vendors named above
  (Clearbit, ZoomInfo) are positioned as incumbents we displace, not
  as providers we call — the rule does not apply to competitive
  framing.
- It does **not** promise a monetization path for the primitive
  itself. The funnel lives in the companion strategy note.
