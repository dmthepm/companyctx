# Contributing to research-pack

Thanks for your interest. `research-pack` is a focused deterministic-collector
CLI; contributions that keep it simple, predictable, and testable are welcome.

## Getting started

```bash
git clone https://github.com/dmthepm/research-pack.git
cd research-pack
pip install -e ".[dev,extract,reviews,youtube]"
ruff check .
mypy research_pack
pytest -v --cov=research_pack
```

## Development workflow

1. Fork and create a topic branch from `main` (e.g. `feat/m3-trafilatura-provider`).
2. Make your change. Keep PRs around 400 lines of code where possible.
3. Add or update tests when behavior changes.
4. Run the full local check suite (`ruff`, `mypy --strict`, `pytest`).
5. Open a pull request against `main`.

## Where to put work

- New deterministic call class → new provider under `research_pack/providers/`,
  registered via `pyproject.toml` entry points. Providers must never raise; map
  failure modes to `ProviderRunMetadata.status`.
- Schema change → start in [`docs/SPEC.md`](docs/SPEC.md) (the canonical spec lives
  in `noontide-projects/boston-v1`; this repo carries a snapshot). Open a
  Discussion before code-changing the schema.
- New CLI flag → discuss first; CLI is a public contract.

## Commit messages

Conventional commits:

- `feat: add yelp fusion provider`
- `fix: respect robots.txt User-agent fallthrough`
- `docs: clarify --mock fixture layout`
- `chore: bump trafilatura pin`
- `test: cover cache TTL boundary`

## Provider rules (non-negotiable)

- **Never raise.** All failures map to `ProviderRunMetadata.status in {"degraded", "failed"}`.
- **Cost-hint required.** Each provider declares `cost_hint: "free" | "per-call" | "per-1k"`
  so `research-pack providers list` can surface it.
- **Env-only secrets.** No keys in code, tests, or fixtures.
- **robots.txt respected by default.** `--ignore-robots` is an explicit CLI flag
  and is not settable from TOML.
- **No cross-provider imports.** Providers are isolated; lint enforces this.

## Tests

- `tests/` is pytest with hypothesis available.
- Each provider gets an isolated unit test using `fixtures/` data.
- `--mock` runs are deterministic — re-running must produce byte-identical output
  modulo `fetched_at`.

## Code of conduct

By participating, you agree to follow [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## Questions

Open a [Discussion](https://github.com/dmthepm/research-pack/discussions) for
direction questions. Use [Issues](https://github.com/dmthepm/research-pack/issues)
for bugs or concrete feature requests.
