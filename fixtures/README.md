# Fixtures

Per-domain offline inputs that drive `companyctx --mock fetch <domain>`.
The 10-domain golden suite is curated in Milestone 5.

## Layout

```
fixtures/
  <domain>/
    homepage.html         # raw landing page HTML
    about.html            # /about (when present)
    services.html         # /services or equivalent (when present)
    google_places.json    # API response for the Places provider
    yelp.json             # API response for the Yelp Fusion provider
    youtube.json          # API response for the YouTube channels.list provider
    expected.json         # hand-curated golden CompanyContext
  seeds.csv               # one column "domain", used by `companyctx batch`
```

Provider files are optional per fixture. If a provider's input file is
missing, `--mock` should record `provenance[slug].status: "degraded"` with
reason `"fixture not provided"` — the same shape as a missing API key in a
live run.

## Determinism rule

`companyctx --mock fetch <domain>` must produce byte-identical output
across runs, modulo the `fetched_at` timestamp. Any non-determinism in
provider output is a bug in that provider, not in the test harness.

## Adding a fixture

1. Create `fixtures/<domain>/`.
2. Drop in raw HTML and any API response JSON the providers consume.
3. Hand-curate `expected.json` — this is the contract, not a re-run of the
   collector.
4. Add the domain to `fixtures/seeds.csv`.
5. Wire a unit test under `tests/` that loads the fixture and asserts the
   collector reproduces `expected.json`.

## Out of scope

Fixtures are not allowed to embed any API key or secret. If a provider
requires auth, the fixture supplies the *response*, never the credential.
