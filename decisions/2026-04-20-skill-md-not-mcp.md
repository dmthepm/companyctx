---
type: decision
date: 2026-04-20
topic: agent discovery via SKILL.md, not MCP — Noontide-wide posture
status: accepted
linked_decisions:
  - decisions/2026-04-20-name-change-to-companyctx.md
  - decisions/2026-04-20-zero-key-stealth-strategy.md
linked_research:
  - research/2026-04-20-markdown-is-the-new-api-deep-research-gemini.md
---

# SKILL.md, not MCP — the agent-discovery surface for every Noontide OSS primitive

## Status

**Accepted.** `SKILL.md` ships in `companyctx` v0.1 (M1). MCP is **off the
roadmap** for this project — not a v0.2 sibling, not a v0.3 candidate,
not "we'll see." This is a Noontide-wide posture, not a
companyctx-specific call: every OSS primitive we ship adopts CLI + SKILL.md,
not MCP.

The canonical decision lives upstream in the design workspace. This file
is the public-repo artifact so external readers see the reasoning surface.

## Context

An earlier draft of the companyctx scope-and-brand-lock parked both
`SKILL.md` and an MCP server as v0.2 siblings. A follow-up research turn
("Markdown is the New API" — Gemini deep research) stress-tested that
parking and returned three concrete reasons to ship SKILL.md and drop
MCP entirely. Devon locked the reversal.

The tension the research resolved: agent-facing tools can either expose
themselves as a protocol server (MCP) or as a CLI discovered via a
~150-token markdown file (`SKILL.md`). `companyctx` is a muscle in the
brains-and-muscles pattern. The right shape of "how an agent finds us"
has to match that pattern, not work against it.

## Decision

### 1. `SKILL.md` ships in v0.1 M1

A ~150-token `SKILL.md` at the repo root is the canonical agent-discovery
surface. Content:

- **Purpose** — one sentence on what the tool is for.
- **Commands** — the three or four invocations that matter.
- **Rules for agents** — invariants the CLI enforces (e.g. "never extract
  people data", "branch on `status`, not try/except", "pipe stdout, don't
  parse logs").
- **Example** — one bash line that shows the canonical pipe.

Nothing else. README is for humans; `SKILL.md` is for agents.

### 2. MCP is off the roadmap

No MCP server ships in v0.1, v0.2, or any currently planned release.
Revisit only if an enterprise-governance customer (OAuth, audit,
multi-tenant access control) ever materializes — which is not our ICP.

### 3. This is Noontide-wide

Every OSS primitive we ship adopts the same posture: CLI + `SKILL.md`, no
MCP. Consistent agent-discovery surface across the portfolio makes the
pattern repeatable and the portfolio legible.

## Rationale

The three arguments the research surfaced, in rough order of weight:

- **Token economics (the load-bearing one).** MCP servers inject their
  full JSON-RPC schema into context before any work happens — up to ~50k
  tokens for reference servers. A `SKILL.md` is ~150 tokens. That's
  roughly a 275× difference. A muscle built specifically to *save* tokens
  (the whole reason `companyctx` replaces "LLM reads the HTML") cannot
  coherently ship wrapped in a layer that burns 50k tokens on
  self-introduction.
- **LLMs already speak Unix.** Frontier models are trained on fifty years
  of bash, pipes, `jq`, man pages, shell one-liners. `companyctx
  example.com | jq '.data.pages'` is native vocabulary. MCP is a novel
  dialect the agent has to learn per-server. Betting against the
  training distribution is expensive and the payoff is a worse UX.
- **Intelligence boundary.** MCP runs as a separate process with
  structured tool-call semantics. The agent hands off state, the server
  does its thing, the agent reads a result — the brain cannot apply its
  own reasoning to intermediate state. CLI + stdout keeps the agent in
  the loop end-to-end. That's the brains-and-muscles pattern in its
  purest form; MCP breaks it.

## Alternatives considered

| Option | Why rejected |
|---|---|
| Ship an MCP server in v0.1 | Contradicts the token-economics case `companyctx` itself makes. A muscle built to save tokens can't wrap itself in a layer that burns 50k. |
| Park MCP as a v0.2 sibling, ship SKILL.md now | Half-measure. If MCP is the wrong shape, shipping it later is still the wrong shape. Better to name the stance clearly: no MCP, unless an enterprise-governance customer appears. |
| Skip SKILL.md, rely on README for agent discovery | README is optimized for humans — long, narrative, multi-section. Agents want a dense, rules-forward, ~150-token surface. Different audiences, different files. Both are cheap to maintain. |
| Ship a `.cursorrules` sibling to SKILL.md | Considered for v0.2 once SKILL.md shows adoption signal. Cursor-specific and redundant on day one. |
| Ship a thin Claude Code skill adapter at launch | Also considered for v0.2. Keeps the core tiny while we measure SKILL.md reception first. |

## Risks

- **MCP ecosystem becomes the default before SKILL.md adoption matures.**
  Mitigation: SKILL.md is one markdown file; adopting MCP later remains
  possible without breaking the CLI contract. The posture is a ship
  decision, not an architectural lock-in.
- **SKILL.md template drifts across the Noontide OSS portfolio.**
  Mitigation: pin the template shape in a Noontide-wide decision doc and
  cross-reference from each project's SKILL.md header.
- **Agents ignore SKILL.md and inject random shell commands.**
  Mitigation: the CLI is the contract; SKILL.md is a hint. Hardening
  against bad invocations is the CLI's job (sensible defaults, clear
  error messages, `companyctx --help`) regardless of discovery surface.

## Further reading

- `research/2026-04-20-markdown-is-the-new-api-deep-research-gemini.md`
  (upstream design workspace) — the deep-research turn that produced the
  token-economics / Unix-fluency / intelligence-boundary argument.
- `decisions/2026-04-20-name-change-to-companyctx.md` — the rename ADR
  that lands alongside this one in M1.
- `decisions/2026-04-20-zero-key-stealth-strategy.md` — the other
  load-bearing M1 decision.
