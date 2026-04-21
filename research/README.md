# `research/` — evidence-bearing research only

This folder holds **measurement-anchored research** that informs
`companyctx` design decisions. It is not a catch-all for planning
docs, GTM strategy, brain-dumps, or notes-to-self.

## What qualifies

A file belongs here only if it has at least one of:

- **Raw evidence** committed alongside it — a probe set, a JSONL of
  measurements, a fixtures corpus, an API response dump. The TLS
  impersonation spike is the canonical example: it ships
  `2026-04-21-tls-impersonation-spike.md` + the raw
  `2026-04-21-tls-impersonation-spike-raw.jsonl` it was produced
  from.
- **A reproducible methodology** the reader could re-run on new
  inputs to verify or refute the conclusion.
- **A claim that resolves an open question parked in `decisions/`** —
  i.e. it unblocks or contradicts an ADR.

If a proposed addition has none of the above, it belongs somewhere
else. Common cases and their correct homes:

| Content | Lives in |
|---|---|
| GTM strategy, funnel thinking, pricing, positioning | GitHub Discussions (public) or Noontide internal workspace (private) |
| Architectural decisions | `decisions/` (ADRs) |
| Technical measurement + evidence | **here** |
| User-facing product documentation | `docs/` |
| Runnable recipes proving use cases | `examples/` (code is the marketing) |

## Transitional artifacts

A file may live here temporarily if it has a **clear migration target**
declared in its front matter — e.g. a use-case catalog waiting for
`examples/` scripts to absorb it, or a positioning draft staged for
migration to Discussions. Transitional files declare
`status: transitional` and name the destination in a top-of-file
banner. If neither migration target exists, the file doesn't qualify
and belongs in Discussions or the Noontide internal workspace from
the start.

## Why the charter

Without this rule the folder drifts into a founder's diary, which is
exactly the wrong signal for an OSS primitive trying to be a
razor-sharp UNIX tool. The folder's credibility comes from every file
in it being defensible against the question "what did you measure?"

## Naming

`YYYY-MM-DD-<kebab-topic>.md` for the write-up, plus
`YYYY-MM-DD-<kebab-topic>-raw.jsonl` (or similar) for the evidence
file when present. Dates reflect when the research was performed, not
when the file was last touched.

## Front matter

Every research file begins with the YAML block used by existing
entries — `type: research`, `date`, `topic`, `category`, `status`,
and links to related `decisions/` ADRs, GitHub issues, and the raw
evidence file. See `2026-04-21-tls-impersonation-spike.md` as the
reference shape.
