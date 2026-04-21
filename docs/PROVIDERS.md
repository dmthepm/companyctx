# Providers

`companyctx` ships as a provider-plugin framework. Each deterministic call
class — site-text extraction, JSON-LD parsing, reviews lookup — lives in its
own provider, discovered at runtime via Python entry points under the
`companyctx.providers` group.

Providers sit on the [Deterministic Waterfall](ARCHITECTURE.md) and all return
the same envelope shape (see [`docs/SCHEMA.md`](SCHEMA.md)).

## Day-one providers (v0.1)

| Slug                       | Waterfall layer | Category         | Key needed            | Cost hint | M1 | M3 |
|----------------------------|-----------------|------------------|-----------------------|-----------|----|----|
| `site_text_trafilatura`    | Zero-key        | `site_text`      | —                     | free      | stub | ✓ |
| `site_text_readability`    | Zero-key        | `site_text`      | —                     | free      | stub | ✓ |
| `site_meta_extruct`        | Zero-key        | `site_meta`      | —                     | free      | stub | ✓ |
| `social_discovery_site`    | Zero-key        | `social_discovery` | —                   | free      | stub | ✓ |
| `signals_site_heuristic`   | Zero-key        | `signals`        | —                     | free      | stub | ✓ |
| `reviews_google_places`    | Direct-API      | `reviews`        | `GOOGLE_PLACES_API_KEY` | per-1k | stub | ✓ |
| `reviews_yelp_fusion`      | Direct-API      | `reviews`        | `YELP_API_KEY`        | per-call | stub | ✓ |
| `social_counts_youtube`    | Direct-API      | `social_counts`  | `YOUTUBE_API_KEY`     | free w/ quota | stub | ✓ |
| `mentions_brave_stub`      | Direct-API      | `mentions`       | `BRAVE_SEARCH_API_KEY`| per-call | stub | stub |

`companyctx providers list` surfaces the table above at runtime, filtered to
which providers are actually configured on the user's machine.

## The `SmartProxyProvider` interface

Attempt 2 of the Deterministic Waterfall is vendor-agnostic. We ship the
contract; the user supplies their own smart-proxy / headless-browser vendor.

```python
@runtime_checkable
class SmartProxyProvider(ProviderBase, Protocol):
    # slug / cost_hint / version inherited from ProviderBase
    category: ClassVar[Literal["smart_proxy"]]

    def fetch(
        self, url: str, *, ctx: FetchContext
    ) -> tuple[bytes | None, ProviderRunMetadata]:
        """Fetch one URL through the smart-proxy.

        Returns (response_bytes, metadata). On block/failure, returns
        (None, ProviderRunMetadata(status="failed", ...)). Never raises.
        """
        ...
```

The Protocol inherits from `ProviderBase` so the structural contract is one
chain — any future addition to `ProviderBase` propagates automatically.

The framework invokes a configured smart-proxy provider when the zero-key
fetcher returns HTTP 403 / challenge HTML / timeout. The response then flows
into the same `trafilatura` / `readability-lxml` / `extruct` chain as the
zero-key path — the schema doesn't know which layer produced the bytes.

**We don't ship a specific vendor.** Reference adapters may land as optional
extras after the measurement spike, but they're interchangeable — swap the
entry-point line in `pyproject.toml` or override at runtime.

> **v0.1 status.** Only the `SmartProxyProvider` Protocol
> (`companyctx/providers/smart_proxy_base.py`) ships today. The first
> concrete vendor implementation lands after the M2 zero-key provider
> (issue #15) and the M2 vendor eval spike — no vendor is named here until
> measurement is in.

## Provider rules (non-negotiable)

- **Never raise uncaught.** Every failure maps to
  `ProviderRunMetadata.status in {"degraded", "failed", "not_configured"}`.
- **Declare `cost_hint`.** `"free"`, `"per-call"`, or `"per-1k"` — so
  `companyctx providers list` can surface cost before the user wires a key.
- **Env-only secrets.** No API keys in code, tests, fixtures, or TOML.
- **Respect robots.txt by default.** `--ignore-robots` exists but is
  CLI-only; not settable via TOML or env.
- **No cross-provider imports.** Providers are isolated; CI lint enforces it.
- **Schema-first.** Provider output maps to the shared `CompanyContext`
  envelope. No shape-shifting per provider.

Full rules in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Writing a new provider

1. Drop a module under `companyctx/providers/<slug>.py` with a `Provider`
   class conforming to `ProviderBase` (see `companyctx/providers/base.py`).
2. Declare `slug`, `category`, `cost_hint`, `version` as `ClassVar`s.
3. Implement `fetch(site, *, ctx: FetchContext) -> tuple[Model | None, ProviderRunMetadata]`.
   Catch everything at your boundary; never let an exception escape.
4. Register under `[project.entry-points."companyctx.providers"]` in
   `pyproject.toml`.
5. Add a unit test under `tests/` using a fixture in `fixtures/<site>/`.
   `--mock` runs must be deterministic — re-running produces byte-identical
   output modulo `fetched_at`.
6. Open a PR. Keep it narrow — one provider per PR is the norm.

Stubs for the day-one providers land in Milestone 3.

## Out-of-scope providers (v0.1)

- LinkedIn / Crunchbase enrichment. Out of scope — that's people-data or
  duplicates Apollo/Clearbit territory.
- IG / FB / TikTok follower-count scrapers. ToS risk; stays nullable.
- Full hosted-actor runners beyond a stub pattern. Can be added under the
  `SmartProxyProvider` interface if/when wanted.
- Brave Search / Exa / Tavily mention providers beyond the
  `not_configured` stub.
- Multi-page / sitemap crawling. One site in, one structured object out.

See also [`docs/REFERENCES.md`](REFERENCES.md) for the upstream OSS libraries
each provider wraps.
