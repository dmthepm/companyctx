# References

Open-source dependencies and architectural inspirations for `companyctx`.
This is a compact list, not a survey — see the canonical OSS hunt synthesis
in the upstream design workspace for the reasoning behind each pick.

## Runtime dependencies

| Package | License | Role |
|---|---|---|
| [Typer](https://github.com/fastapi/typer) | MIT | CLI framework |
| [Pydantic v2](https://github.com/pydantic/pydantic) | MIT | Schema + validation |
| [pydantic-settings](https://github.com/pydantic/pydantic-settings) | MIT | TOML + env config loader |
| [platformdirs](https://github.com/platformdirs/platformdirs) | MIT | XDG-compliant cache + config paths |
| [requests](https://github.com/psf/requests) | Apache-2.0 | HTTP client |
| [requests-cache](https://github.com/requests-cache/requests-cache) | BSD-2-Clause | HTTP-layer caching |
| [tenacity](https://github.com/jd/tenacity) | Apache-2.0 | Retry / backoff |
| [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) | MIT | HTML parsing |
| [lxml](https://github.com/lxml/lxml) | BSD-3-Clause | XML / HTML backend |

## Provider dependencies (optional extras)

| Package | License | Provider |
|---|---|---|
| [trafilatura](https://github.com/adbar/trafilatura) | Apache-2.0 | `site_text_trafilatura` (primary) |
| [readability-lxml](https://github.com/buriy/python-readability) | Apache-2.0 | `site_text_readability` (fallback — bus-factor mitigation) |
| [extruct](https://github.com/scrapinghub/extruct) | BSD-3-Clause | `site_meta_extruct` (JSON-LD / OG / `sameAs`) |
| [googlemaps](https://github.com/googlemaps/google-maps-services-python) | Apache-2.0 | `reviews_google_places` |
| [yelpapi](https://github.com/lanl/yelpapi) | BSD-3-Clause | `reviews_yelp_fusion` |
| [google-api-python-client](https://github.com/googleapis/google-api-python-client) | Apache-2.0 | `social_counts_youtube` |

## Architectural patterns (cribbed, not adopted)

- **`crawl4ai`** — `cache_mode` semantics and resumable-batch patterns
  informed how `--no-cache` and the SQLite TTL behave.
- **Firecrawl / Tavily / Exa** — provider-boundary shape (`search` /
  `scrape` / `map` / `research`) informed how the pluggable provider
  interface separates concerns.
- **`clig.dev`** — guidance for human-friendly CLI defaults
  (`--json` / `--markdown`, exit codes, `--verbose` shape).

## Why these picks

- **Two site-text providers day-one (`trafilatura` + `readability-lxml`)** —
  bus-factor mitigation. If one stalls or hard-deprecates, the other keeps
  the day-one path alive without a rewrite.
- **`extruct` separately from text extraction** — JSON-LD / OpenGraph /
  `sameAs` discovery is a different layer from boilerplate-stripping. The
  right primitive for finding social handles before falling through to
  per-platform discovery.
- **YouTube via the official Data API** — the only ToS-safe follower count
  source we wire day-one. IG / FB / TikTok counts intentionally stay
  nullable in v0.1.

## Out of scope for v0.1

LinkedIn / Crunchbase, IG / FB / TikTok follower-count scrapers, Apify
actors beyond a stub pattern, Brave / Exa / Tavily mention providers
beyond a `not_configured` stub, web UI.
