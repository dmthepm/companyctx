# OSS-HYGIENE.md — public-OSS health checklist

`companyctx` is a public MIT package. Automated CI (ruff, mypy, pytest,
coverage) catches the mechanical regressions. This file catches the
ecosystem-rot signals they don't: API stability, doc drift, contribution
surface, telemetry, supply chain, reproducibility, license, and package
metadata.

Reviewers cross-check every PR against these eight sections. Each section
has a concrete pass/fail criterion a human can verify in a minute by
reading the diff and one or two files on `main`.

This is a living checklist — when a new failure mode surfaces in review,
add a ninth section rather than stretching an existing one.

## 1. Public API stability

*Downstream agent pipelines pin a version and expect `from companyctx
import X` to keep working.*

- **Pass.** Every new public function or class is added to the nearest
  `__all__` (`companyctx/__init__.py` for top-level surface,
  `companyctx/<module>.py` for module-level surface). Renames and removals
  ship a `DeprecationWarning` and stay importable for at least one
  minor release. Breaking changes bump the major version and land with a
  `BREAKING CHANGE:` footer on the commit.
- **Fail.** A name used in `SKILL.md`, `README.md`, `docs/SCHEMA.md`, or
  an `examples/` snippet is removed or renamed in a patch/minor release
  with no deprecation path. A new public class is defined but not listed
  in `__all__`, so `from companyctx import X` breaks for downstream users
  even though the class exists.

## 2. User-facing doc freshness

*Agents consume `SKILL.md`. Humans consume `README.md`. PyPI consumes
`long_description`. All three must tell the same story.*

- **Pass.** A CLI surface change (new flag, new command, new exit code,
  new output field) updates, in the same PR: `README.md`, `SKILL.md`,
  `docs/SPEC.md`, the relevant `docs/*.md` that names the flag, and the
  Typer `help=` string shown by `companyctx <cmd> --help`. If the change
  invalidates a status line (e.g. "CLI is stubs — every command exits
  2"), that line is fixed or removed in the same PR.
- **Fail.** PR adds `--bypass-cache` to Typer but `SKILL.md`'s command
  table still lists only the old flags. Or: CLI is wired to return real
  data but `README.md` still says "CLI itself is still stubs." Status
  lines like this are the most common drift and the easiest to miss
  because they look like prose, not code.

## 3. Contribution surface

*`companyctx` is a public repo. External contributors land here first
via `CONTRIBUTING.md`, the PR template, and the issue templates.*

- **Pass.** `CONTRIBUTING.md` still describes the real setup path
  (`pip install -e ".[dev,extract,reviews,youtube]"`), the real pre-push
  gates (`ruff check`, `ruff format --check`, `mypy`, `pytest`), and the
  real branch/PR conventions. PR / issue templates in `.github/` match
  today's labels and checklist shape. `CODE_OF_CONDUCT.md` is present
  and linked from `CONTRIBUTING.md`.
- **Fail.** `CONTRIBUTING.md` names a gate that's been removed, skips a
  gate that's been added, or refers to a branch naming scheme that's
  since changed. PR template asks for a checkbox the reviewer no longer
  cares about. `CODE_OF_CONDUCT.md` is missing or orphaned.

## 4. Telemetry / privacy

*Zero-key is not just a default, it's a posture. No silent network
behavior anywhere on the default path.*

- **Pass.** `import companyctx`, `companyctx --help`, `companyctx
  --version`, and `companyctx providers list` make zero outbound network
  requests. The only code paths that touch the network are the provider
  `run(...)` methods themselves, invoked from `companyctx fetch`. Any
  opt-in network behavior (remote cache sync, update check, telemetry)
  ships default-off behind an explicit flag, is documented in
  `README.md` and `SKILL.md`, and its TOML/env knobs are listed in
  `docs/SPEC.md`.
- **Fail.** A new dependency adds an import-time HTTP call (version
  check, crash reporter init, analytics client). A provider imports
  another provider's side-effectful module at module scope. `--help`
  opens a socket.

## 5. Supply chain

*Every third-party dependency is a risk bet. We document the bet so
future reviewers can re-check it.*

- **Pass.** A PR adding a net-new dependency answers three things in the
  PR description (not just the commit message): (a) **Why this package
  specifically?** — what it does that stdlib doesn't, and what
  alternatives were rejected; (b) **What's the swap path?** — the named
  fallback if the upstream project goes unmaintained or hostile;
  (c) **Governance signal** — multi-maintainer with an active release
  cadence, or single-maintainer / solo repo (and if solo, why the risk
  is acceptable). Existing deps in `pyproject.toml` with a known
  bus-factor-one maintainer are called out in the file they're first
  imported from, so the risk is visible at the point of use.
- **Fail.** A single-line import pulls in a transitive tree of 40
  packages for convenience. A direct dep is added with no rationale
  beyond "it works." A vendor named in a PR description has never been
  measured against the fixtures corpus — see the vendor-naming rule in
  the Code Review preferences. (PR #31 is the current exemplar for this
  section: `curl_cffi` picked over `rnet` on license grounds and over
  `primp` on a determinism-hazard (silent fingerprint fallback). That's
  the shape every new-dep PR should take.)

## 6. Reproducibility

*"Works on my machine" is unacceptable for a tool whose contract is
byte-identical `--mock` output across runs.*

- **Pass.** `.github/workflows/ci.yml` tests against a matrix of
  `["3.10", "3.11", "3.12"]` — exact minors, not `>=3.10`. Runtime deps
  in `pyproject.toml` use lower bounds (`pydantic>=2.6`) because that's
  the library contract. Dev-tool bounds (`ruff`, `mypy`, `pytest`) are
  tight enough that a float-bound minor release can't silently break
  linting on `main` — either pinned to a specific version or bounded
  with a compatible-release operator (`~=`). Fixtures are deterministic
  and re-generating them produces byte-identical output modulo
  `fetched_at`.
- **Fail.** CI uses `python-version: 3.x` (floats). `ruff>=0.4` in dev
  deps lets a major-bump release of ruff silently change lint rules on
  the next install. A fixture regenerator is non-deterministic (random
  iteration order, unstable dict keys).

## 7. License discipline

*The repo is MIT. Every byte shipped has to be compatible.*

- **Pass.** No source file carries a license header that conflicts with
  the top-level `LICENSE`. Any vendored third-party code lives in a
  clearly-named directory with its original `LICENSE` file alongside,
  and is noted in a top-level `NOTICE` if attribution is required. New
  dependencies in `pyproject.toml` are MIT / BSD / Apache-2.0 /
  ISC / PSF / MPL-2.0 — or have been affirmatively analyzed for
  compatibility in an ADR. GPL / AGPL / SSPL dependencies are rejected;
  LGPL is case-by-case and gets an ADR.
- **Fail.** A snippet copied from Stack Overflow or a GPL project lands
  in `companyctx/` without attribution or license review. A dependency
  is added whose license hasn't been checked. (Precedent: PR #31's
  spike rejected `rnet` specifically because it's GPL-3.0 — the
  contamination path was real, not theoretical. That level of scrutiny
  is the bar.)

## 8. Package metadata health

*The PyPI listing, the type-stub story, and the install path all come
from `pyproject.toml` and a few sibling files. They rot quickly.*

- **Pass.** `[project]` classifiers list only the Python versions the
  CI matrix actually tests. `readme = "README.md"` and the rendered
  `long_description` is the README, so the PyPI page matches GitHub.
  `[project.urls]` has working `Homepage`, `Repository`, `Issues`, and
  `Changelog` entries. `companyctx/py.typed` exists (empty marker file)
  so downstream users who run `mypy` against code that imports
  `companyctx` get our Pydantic type hints rather than `Any`. Keywords
  are accurate to what the tool does today.
- **Fail.** `Programming Language :: Python :: 3.9` classifier in a
  package whose CI doesn't test 3.9. `readme` points to a file that
  doesn't exist or renders badly on PyPI. `Changelog` URL 404s. The
  `py.typed` marker is missing so downstream type-checking degrades to
  `Any`.

---

## Automated gates

Four automated gates run on every PR to catch OSS health drift that
human review misses at scale. Human review (the eight sections above)
stays authoritative — the gates are a safety net, not a substitute.

### What runs

| Gate         | Where                           | Trigger                           | Blocks CI? |
|--------------|---------------------------------|-----------------------------------|------------|
| `pip-audit`  | `.github/workflows/ci.yml`      | push to `main`, PR                | Yes        |
| `pyroma`     | `.github/workflows/ci.yml`      | push to `main`, PR                | Yes        |
| CodeQL       | `.github/workflows/codeql.yml`  | push to `main`, PR, weekly cron   | No\*       |
| Dependabot   | `.github/dependabot.yml`        | weekly sweep                      | No\*\*     |

\* CodeQL findings surface as Security alerts on the repo. They don't
fail CI today; branch protection can promote them to blocking in a
separate repo-settings change (not code).

\*\* Dependabot opens PRs; the same ruff / mypy / pytest / pip-audit /
pyroma gates then gate those PRs just like any human PR.

### `pip-audit` — CVE scan on direct + transitive deps

Runs in the `supply-chain` job alongside ruff / mypy / pytest. Uses the
`--strict` flag so any advisory against any installed package fails the
build. Allowlist is `.pip-audit.toml` at repo root.

To dismiss a false positive:

1. Reproduce locally: `pip-audit $(python scripts/pip_audit_ignores.py)`.
2. Confirm the vulnerable code path is not reachable from any provider
   or CLI entry point. If it is reachable, the answer is "upgrade the
   dep" or "vendor around it", not allowlist.
3. Add an entry to `.pip-audit.toml`:

   ```toml
   [[ignore]]
   id = "GHSA-xxxx-xxxx-xxxx"
   reason = "vuln in <package>.<symbol>; companyctx calls <other_symbol> only."
   ```

4. Cite the advisory ID in your PR description. Reviewers verify the
   unreachable claim before approving.

When the upstream package ships a fix, delete the allowlist entry. Do
not leave stale entries.

### `pyroma` — package metadata health

Runs with `-n 9` so any score below 9/10 fails CI. Current baseline is
10/10. A drop usually means a missing classifier, a broken
`project.urls` entry, or a `long_description` that stopped rendering.
The fix is always in `pyproject.toml`, not in an allowlist — there is
no allowlist for pyroma by design.

### CodeQL — static analysis

GitHub's default CodeQL, two languages:

- `python` — catches the library code itself (injection, unsafe
  deserialization, etc.).
- `actions` — catches workflow files (expression injection, script
  injection via untrusted input).

Findings appear on the Security tab. Triage weekly; file an issue for
anything we can't fix same-day.

### Dependabot — weekly dep sweep

Weekly on Monday 09:00 America/Los_Angeles. Two ecosystems: `pip` and
`github-actions`. Minor and patch updates group into one PR per
ecosystem; major updates open individually so a human can judge breakage
risk. All Dependabot PRs target `main` and pass through the full CI
gate stack before merge.

### Philosophy

Gates catch drift, not design. Prefer fixing the underlying issue
(upgrade the dep, fix the metadata, rewrite the vulnerable code path)
over allowlisting. Allowlist entries cost review attention every time
someone audits this file — that cost is the point, and it should bias
us toward real fixes.

---

## Test case — how PR #19 would have scored

PR [dmthepm/companyctx#19](https://github.com/dmthepm/companyctx/pull/19)
(`feat(m2): envelope + waterfall orchestrator + first zero-key
provider`) wired the real `fetch` / `providers list` / `validate` CLI,
added `companyctx/core.py`, shipped the first provider
(`site_text_trafilatura`), and expanded the schema. Scoring against
this checklist as of merge commit `eda1734`:

1. **Public API stability — PARTIAL.** `companyctx/core.py` and
   `companyctx/schema.py` both added a module-level `__all__` (good). But
   `companyctx/__init__.py` still only re-exports `__version__`. A
   downstream consumer writing `from companyctx import Envelope,
   CompanyContext, ProviderRunMetadata` — the natural shape for a
   schema-is-the-product library — gets `ImportError`. For a v0.1.0 on
   PyPI this is still fixable without a deprecation cycle, but past
   v0.1.0 it would be a MEDIUM API-stability miss. **Fix:** re-export
   the envelope types from `companyctx/__init__.py` before the v0.1.0
   tag.
2. **User-facing doc freshness — FAIL (MEDIUM).** PR #19 flipped
   `companyctx fetch --mock --json` from "every command exits `2`" to a
   working envelope emitter, but `README.md`'s Status block still reads
   "**The CLI itself is still stubs**: every command exits `2`." The
   prose drift is exactly the failure mode Section 2 catches. **Fix:**
   either bundle the README status update into the same PR, or open a
   follow-up `docs:` PR before v0.1.0 ships.
3. **Contribution surface — PASS.** `CONTRIBUTING.md`,
   `CODE_OF_CONDUCT.md`, and `.github/PULL_REQUEST_TEMPLATE.md` all
   still match the real flow.
4. **Telemetry / privacy — PASS.** `core.py` and the new provider only
   touch the network from inside `run(...)`. No import-time HTTP.
5. **Supply chain — PASS.** Zero net-new dependencies (entry-point
   registration only in `pyproject.toml`). `trafilatura` /
   `beautifulsoup4` / `lxml` were already vetted in the scaffold.
6. **Reproducibility — PARTIAL (LOW).** CI pins the Python matrix at
   exact minors (good). Dev-tool bounds in `pyproject.toml` are
   loose lower bounds: `ruff>=0.4`, `mypy>=1.10`, `pytest>=8.0`. Any
   breaking minor release of any of those tools could silently break
   `main`. **Fix:** tighten to `~=` compatible-release operators before
   v0.1.0.
7. **License discipline — PASS.** No vendored code, no conflicting
   headers, all deps MIT/BSD/Apache-2.0.
8. **Package metadata health — FAIL (LOW).** `companyctx/py.typed` does
   not exist. The package ships no typing marker, so downstream `mypy`
   users who import `companyctx` get `Any` instead of our Pydantic
   types — specifically defeating one of the library's selling points.
   Classifiers, `long_description`, and URLs are all correct. **Fix:**
   add the empty marker file in the same PR as the `__init__.py`
   re-exports from item 1.

**Reviewer verdict against this checklist:** REQUEST CHANGES — two
MEDIUM misses (item 1 API surface, item 2 README status drift) and two
LOW misses (item 6 dev-dep pinning, item 8 `py.typed`). None block
merging the M2 slice on its own terms; all block a clean v0.1.0 tag.
Tracked as follow-up issues rather than held against the M2 PR.

The scoring above is the proof the checklist is load-bearing: each
failure here is a real, verifiable drift on `main` at commit `eda1734`
that the existing ten Code Review preferences (scope, contract,
determinism, secrets, etc.) would not have flagged.
