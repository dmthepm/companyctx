---
type: decision
date: 2026-04-20
topic: rename dmthepm/research-pack → dmthepm/companyctx
status: accepted
supersedes_name: research-pack
---

# Rename `research-pack` → `companyctx`

## Status

**Accepted.** GitHub repo renamed (URL forwarding active). PyPI name
`companyctx` verified available. Package directory, CLI entry point,
import path, env-var prefix, cache-db filename, and all metadata updated
in a single M1 PR.

The canonical decision lives in the upstream design workspace:
`noontide-projects/boston-v1/decisions/2026-04-20-research-pack-scope-and-brand-lock.md`.
This file is the public-repo artifact so external readers can see the
reasoning surface — the walks-the-walk posture for the OSS audience.

## Context

The original name `research-pack` was chosen early, when the project was
framed as a "research pack collector for outreach pipelines." Four internal
research passes plus three deep-research returns (Gemini scope, GPT scope,
Grok scope×2 / audience×3 / repo-structure) stress-tested the name. The
convergent signal:

- Hyphenated `-pack` / `-toolkit` names read as enterprise bundles and pull
  SDR / sales-enablement traffic — the wrong top-of-funnel audience for a
  narrow deterministic CLI.
- "research" is overloaded in 2026 — academic LLM evaluation tools vs. SDR
  lead-gen tools both claim the word. Mixed audience, muddy positioning.
- The target durable shape — Simon Willison's `llm`, `datasette`,
  `sqlite-utils`; `trafilatura`, `extruct`, `litestream`, `uv`,
  `aider`, `browser-use` — is **single-token, technical, primitive-flavored.**
  `companyctx` reads that way; `research-pack` does not.

Gemini's scope pass flagged the old name as a **fatal compromise** for the
intended OSS audience. Grok's final pass validated `companyctx` with zero
identified conflicts. GPT was neutral on rename but did not oppose.

## Decision

Rename to `companyctx`. "Company Context" as a primitive — the thing an
agent brain pipes through to get schema-locked context about a company at
a given site.

Concretely:

- GitHub repo: `dmthepm/research-pack` → `dmthepm/companyctx` (rename done,
  URL forwarding active).
- PyPI package: `companyctx` (verified available).
- Import path: `companyctx` (was `research_pack`).
- CLI command: `companyctx` (was `research-pack`).
- Env-var prefix: `COMPANYCTX_` (was `RESEARCH_PACK_`).
- Entry-point group: `companyctx.providers` (was `research_pack.providers`).
- Schema envelope class: `CompanyContext` (was `ResearchPack`).

## Rationale

- **Audience alignment.** Single-token technical name reads as a primitive —
  the right shape for the Claude Code / Cursor / Aider / Willison-sphere
  corner where this tool lives.
- **Scope clarity.** `companyctx` tells you what it does in one token:
  context about a company. `research-pack` implied synthesis, analysis,
  opinion — which this tool explicitly does not do.
- **Cheap to change pre-tag.** No shipped users, no PyPI presence, no
  dependent ecosystem. The cost of changing later (renaming a tagged
  package, breaking imports, migrating users) compounds fast.
- **Aligns with the brains-and-muscles framing.** `companyctx` names a
  narrow muscle. `research-pack` named a bundle.

## Alternatives considered

| Option | Why rejected |
|---|---|
| Keep `research-pack` | Convergent deep-research signal flagged it as fatal for audience fit. Hyphenated `-pack` pulls SDR traffic. |
| `dossier` | Collides with existing generic tooling. |
| `siggraph` | Collides with the graphics conference. |
| `brief-forge` | Overclaims into synthesis territory — we explicitly don't synthesize. |
| `context-collector` | Two tokens, hyphenated, reads as a bundle again. |
| `ctx` alone | Too short; collides with every library's request-context variable. |

`companyctx` was the cleanest single-token option that both described the
scope (company-only, no people data) and read as a primitive.

## Migration

No user migration required. The project is pre-tag, pre-PyPI, pre-public
release. The rename lands in the same M1 PR as the rest of the scaffold —
external readers only ever see the new name.

Internal references:

- Joel's skill files (the downstream consumer's private workspace) will
  update as part of the D100 integration handoff, not before. The
  integration hasn't happened yet — the integration-ready artifact uses
  the new name from day one.
- The upstream design workspace has been amended (PR #80 on
  `noontide-co/projects`).

## Risks

- **Issue #1 body on the renamed repo still says `research-pack`.**
  Mitigation: edit the issue body in the M1 PR that lands this rename.
  Layered comments already point readers to the new name.
- **Draft PR #2 references the old name throughout.** Mitigation: this
  decision is part of the rebrand commits in that PR; title + description
  get rewritten as the rebrand lands.
- **Old URL indexed with the old name.** Mitigation: GitHub's rename
  forwarding is active and permanent. Not a meaningful risk.

## Further reading

- Upstream canonical decision (with deep-research reconciliation):
  `noontide-projects/boston-v1/decisions/2026-04-20-research-pack-scope-and-brand-lock.md`
- `decisions/2026-04-20-zero-key-stealth-strategy.md` — the other load-bearing
  decision landing alongside this rename in M1.
