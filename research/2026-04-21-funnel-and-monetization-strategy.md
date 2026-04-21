---
type: research
date: 2026-04-21
topic: three-funnel monetization framing for companyctx as a Noontide top-of-funnel primitive
category: go-to-market
status: living document
linked_issues:
  - https://github.com/dmthepm/companyctx/issues/36
  - https://github.com/dmthepm/companyctx/issues/35
linked_research:
  - research/2026-04-21-market-expansion-use-cases.md
linked_decisions:
  - decisions/2026-04-20-name-change-to-companyctx.md
---

# Funnel and monetization strategy

## One-sentence summary

`companyctx` is explicitly not monetized as a primitive; it is top-of-
funnel for the paid Noontide umbrella, which today is Main Branch
playbooks + the Noontide consulting practice, and tomorrow may include
a hosted / unified-API fallback for operators who want convenience over
local control.

## Framing

The wrong move is to try to monetize the primitive directly — pricing
tiers, gated providers, credit systems, "pro" features hidden behind a
paywall. The primitive's whole job is to be a trustworthy muscle for
agent pipelines; charging for the muscle immediately compromises the
trust that makes it useful in the first place.

The right move is to treat the primitive as distribution. `companyctx`
earns its place in operator workflows as free, schema-locked,
deterministic infrastructure. The paid surface is everything Noontide
layers on top.

This note codifies that split so the reasoning does not get lost in
chat history or slide decks.

## The three funnels

### 1. Main Branch playbooks (today)

- **Free.** The muscle — `companyctx` itself. Pipx install, zero-key
  stealth on the default path, local SQLite cache.
- **Paid.** The brain and nervous system: prompts, orchestration, glue
  code, opinionated playbooks, live implementation support, and the
  D100-class outbound workflows that Main Branch members actually run
  in production.
- **What we sell.** A revenue outcome (booked meetings, landed deals,
  pipeline), not a data-extraction primitive. Operators pay for the
  motion, not the muscle.
- **Why this works.** The operator who clones the repo already gets
  real value. The ones who convert are the ones who decide the
  playbook wrapped around the primitive is worth more than building
  it themselves. That is a self-qualifying funnel.

### 2. Noontide agency consulting (today)

- **Free.** The repo itself — code as proof of competence. The
  `examples/` directory demonstrates we can wire the primitive into a
  real pipeline. The `decisions/` directory demonstrates we think
  clearly about architecture. The `research/` directory demonstrates
  we anchor decisions in measurement. Together, they do the job a
  case study does, without the aftertaste of a case study.
- **Paid.** Enterprise and mid-market buyers who want the D100-class
  pipeline but do not want to implement it themselves become
  consulting leads for the Noontide agency practice. The sales motion
  is "we built this, here is the code, here is the playbook, here is
  what it costs to have us run it for you."
- **What we sell.** Implementation, integration, and ongoing operation
  of the full pipeline inside a customer's environment. The repo is
  the credential; the consulting engagement is the product.
- **README posture.** The README should provide a tasteful path to
  agency engagement without turning the repo into a brochure. One
  link in a footer-like "Support" or "Commercial support" section is
  enough. The README stays a technical README first; the commercial
  surface is a signpost, not a pitch. The specific section wording is
  tracked separately in #35.

### 3. Future hosted / unified API fallback (later)

- **Status.** Exploratory. Not on the v0.1 or v0.2 roadmap. Codified
  here so the option stays alive without cluttering near-term
  milestones.
- **The shape.** Longer term, convenience can become the paid SaaS
  layer. Operators run locally for free with their own provider keys,
  or — when they would rather not manage keys, quotas, smart-proxy
  contracts, and fallback routing themselves — point at a hosted
  Noontide endpoint that returns the same envelope shape with
  Noontide's pooled infrastructure behind it.
- **What we would sell.** Unified billing, fallback routing across
  multiple smart-proxy and direct-API providers, and the operational
  burden of fingerprint-freshness maintenance that the zero-key path
  depends on.
- **What we would *not* sell.** A different envelope, a gated schema,
  or anything that makes the hosted path a data moat relative to the
  local path. The contract is the product; the hosted surface is a
  convenience layer on top of the same contract.
- **Trigger conditions.** At least one of: (a) Main Branch operators
  repeatedly asking for pooled keys; (b) an enterprise buyer
  explicitly refusing to run the CLI locally; (c) fingerprint-
  freshness upkeep becoming load-bearing enough that hosting it
  centrally is cheaper for everyone than each operator doing it.

## Why the split works

The three funnels reinforce each other:

- The free primitive sells the Main Branch playbook. Operators see the
  muscle works, then subscribe to the brain.
- The free primitive + public `examples/` and `decisions/` sell the
  consulting engagement. Buyers see the output and hire for the
  operation.
- Both paid surfaces, once running at scale, produce the demand signal
  that justifies (or kills) the hosted path.

If the order inverts — primitive behind a paywall, playbooks bundled
inside a SaaS — the muscle loses its trust surface and the rest of the
funnel collapses with it.

## Guardrails

- **Do not paywall the primitive.** Ever. If a feature feels like it
  "should be paid," it belongs in the playbook or the hosted fallback,
  not in the CLI.
- **Do not bundle the playbook into the primitive.** Opinionated
  prompts, D100-specific flows, and orchestration logic stay upstream
  in Main Branch content. The repo ships muscle, not motion.
- **Do not let the README drift into a sales surface.** The README's
  job is to get an agent pipeline integrated in the first read. The
  commercial path is a signpost at the bottom, not a banner at the
  top. #35 is the issue that governs that posture; this note is the
  reasoning behind why the answer there is "tasteful, one section."
- **Do not name vendors in public docs before measurement.** This
  applies to the hosted fallback too: when it ships, any specific
  smart-proxy or direct-API provider we pool through it has to clear
  the same measurement bar the local path does. The rule does not
  relax inside a hosted surface.

## What this document does not do

- It does **not** commit Noontide to launching the hosted fallback.
  That is explicitly a trigger-gated option, not a roadmap item.
- It does **not** prescribe pricing or packaging for Main Branch or
  the agency. Those are commercial decisions that live in upstream
  Noontide planning, not in the `companyctx` repo.
- It does **not** bind future `companyctx` architecture to any
  particular funnel stage. The primitive remains designed to the
  invariants in `docs/ARCHITECTURE.md`; the funnels are layered on
  top, not baked in.
