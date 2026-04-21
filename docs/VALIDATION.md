# SNAPSHOT — canonical at `noontide-projects/boston-v1/decisions/2026-04-20-companyctx-validation-protocol.md`; do not maintain here

> This file is a frozen snapshot taken at scaffolding time (Milestone 1).
> Future protocol edits land in the canonical workspace and flow back via a
> new handoff cycle, not via PRs against this file.

---

# companyctx — validation protocol

## Two-phase gate

Before `companyctx` replaces the LLM-reads-HTML step in a downstream
production pipeline, both phases must pass.

### Phase A — blind-eval (fast signal)

- **N:** 10 prospects.
- **Source:** picked from a recent successful overnight batch on the
  downstream pipeline. Niches should span 2–3 categories to avoid overfitting.
- **Input:** for each prospect, run `companyctx fetch <domain>` → JSON.
  A synthesis call reads the JSON and writes the 6-section brief
  (Differentiator / Audience / Content & Social / Credentials & Proof / Gap /
  5 Script Angles).
- **Comparison:** side-by-side with the existing Opus-reads-HTML brief for
  the same prospect.
- **Reviewers:** the project owner + the downstream pipeline owner, blind
  (each scores without seeing the other's scores first).
- **Scoring:** per-prospect, pick one of `(+)` companyctx better,
  `(=)` same, `(−)` Opus better. Record disagreements explicitly.
- **Pass:** ≥8/10 prospects have at least one reviewer saying `(+)` or `(=)`,
  AND no prospect has both reviewers saying `(−)`.
- **Turnaround:** 48 hours from v0.1 ready.
- **Outcome:** pass → proceed to Phase B; fail → kill or iterate.

### Phase B — 2-week live A/B on booked calls (real validation)

- **Setup:** half of the campaigns run companyctx briefs, half run the
  Opus briefs. Same niches, same day, same downstream synthesis model.
- **Duration:** 2 weeks (matches reply-rate decay curve).
- **Metric:** booked calls (the revenue signal — not just reply rates).
- **Pass:** reply rate within ±10% of the Opus baseline AND no catastrophic
  silent-failure pattern (e.g., a whole category of signals consistently
  missing).
- **Fail:** reply rate drops >10%, OR a downstream reviewer surfaces a
  pattern of "the brief missed something Opus would have caught."
- **Outcome:** pass → production switch; fail → kill (the tool stays
  available for adjacent pipelines). Easy rollback because the provider is
  pluggable — toggle back to Opus-reads-HTML in one config change.

## Why two phases

Phase 1 research quality **doesn't fail loudly**. A weaker brief → weaker
creative → ~15% reply-rate sag shows up 2–3 weeks downstream as fewer booked
calls, not as a pipeline error. Blind-eval catches *obvious* drops; it cannot
catch "briefs are 85% as good." A/B is more expensive but cheaper than a
month of undiagnosed quality loss at scale.

## Gating summary

| Phase | Gate | Pass | Fail |
|---|---|---|---|
| A | Blind-eval on 10 prospects | Proceed to B | Kill or iterate |
| B | 2-week live A/B on booked calls | Production switch | Kill; tool stays available for adjacent pipelines |
| — | Post-switch | Ongoing monitoring via downstream review + weekly-cost logs | Easy rollback (provider is pluggable) |

## Mapping to the three concerns the spec is built around

- **Inference preservation.** A/B catches this directly. If the
  `signals: CrossReferenceSignals` bucket misses what the Opus
  cross-reference inference caught, reply rates sag in Phase B. Phase A
  can only hint at it.
- **Silent-failure shape.** The whole reason Phase B exists. Blind-eval
  alone would accept "85% as good" and lose 15% reply rate silently at
  10× scale.
- **Maintenance surface.** Not validated by this protocol. Handled in the
  spec via fallback providers + pluggable interface.

## Risks

- **Blind-eval passes but A/B fails.** By design — A/B is the real gate.
- **A/B underpowered at low daily volume.** ~1000 prospects split 500/500
  over 2 weeks is marginal for 5–10% deltas. Mitigation: extend by 1 week
  if the signal is inconclusive at 2 weeks.
- **A/B blocked by downstream capacity.** Mitigation: downgrade to
  blind-eval + 1-week A/B only with explicit agreement from the downstream
  owner.
- **Production switch made on thin data because stakes escalate.**
  Mitigation: Phase B pass criterion is explicit (±10% reply rate). No
  feel-based switch.
