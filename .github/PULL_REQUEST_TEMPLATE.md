<!--
  Thanks for contributing to companyctx!

  Keep PRs ~400 lines of code where possible. One PR per milestone or
  per provider. See CONTRIBUTING.md.
-->

## What this changes

<!-- One paragraph: the user-visible behavior change. -->

## Why

<!-- Link to the issue or decision doc. -->

Closes #

## How to verify locally

```bash
pip install -e ".[dev,extract,reviews,youtube]"
ruff check .
ruff format --check .
mypy companyctx
pytest -v --cov=companyctx
```

## Checklist

- [ ] Conventional commit prefix (`feat:`, `fix:`, `docs:`, `chore:`, `test:`).
- [ ] Tests added or updated for behavior changes.
- [ ] No secrets in code, tests, or fixtures.
- [ ] If a new provider: declares `slug`, `category`, `cost_hint`, never raises uncaught.
- [ ] If a CLI flag changed: updated `docs/SPEC.md` snapshot note (canonical lives upstream).
- [ ] CI is green (ruff + mypy strict + pytest ≥70% cov).
