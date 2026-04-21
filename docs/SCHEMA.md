# Schema

The Pydantic v2 shape `companyctx` emits. The schema is the product — providers
are replaceable, the contract is not.

v0.1 ships a minimal placeholder model (`domain` + `fetched_at`) so the
package imports cleanly. The full schema below is implemented in Milestone 2.
The structure here is the contract that M2–M5 fill in — adding fields is
additive and backwards-compatible; removing or renaming fields is a
schema-version bump.

## The envelope

Every `companyctx fetch` invocation returns one wrapper around the payload:

```python
class Envelope(BaseModel):
    status: Literal["ok", "partial", "degraded"]
    data: CompanyContext
    provenance: dict[str, ProviderRunMetadata]
    error: str | None = None
    suggestion: str | None = None
```

Status semantics:

| `status`    | When |
|-------------|------|
| `ok`        | Every required provider succeeded; no per-field fallback fired. |
| `partial`   | One or more providers degraded (anti-bot, missing key, timeout). `data` is still schema-conformant; `error` + `suggestion` name the cause and fix. |
| `degraded`  | Result came from cache past its TTL and was used anyway. `error` states the cache age. |

`error` and `suggestion` are present only when `status != "ok"`. `suggestion`
is *actionable*: `"configure a smart-proxy provider key"`, `"skip this
prospect"`, `"run with --refresh"`.

## `CompanyContext`

```python
class CompanyContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Required — always present, even on partial runs.
    domain: str                   # e.g. "acme-bakery.com"
    fetched_at: datetime          # UTC

    # Optional — nullable / empty-collection on partial runs.
    site: SiteSignals | None = None
    reviews: ReviewSignals | None = None
    social: SocialSignals | None = None
    mentions: list[MediaMention] = []
    signals: CrossReferenceSignals | None = None
```

Nothing else goes at the top level in v0.1. People-data fields (contact,
decision-maker, enrichment) are out of scope — that enrichment belongs
upstream (Apollo / Clearbit / manual research).

## Sub-models

### `SiteSignals`

```python
class SiteSignals(BaseModel):
    homepage_text: str                # cleaned, extractor-agnostic
    about_text: str | None = None
    services: list[str] = []
    tech_stack: list[str] = []        # detected, not claimed
```

### `ReviewSignals`

```python
class ReviewSignals(BaseModel):
    count: int
    rating: float | None = None
    source: str                       # provider slug, e.g. "reviews_google_places"
```

### `SocialSignals`

```python
class SocialSignals(BaseModel):
    handles: dict[str, str] = {}           # platform → handle
    follower_counts: dict[str, int] = {}   # platform → count (nullable in v0.1)
```

### `MediaMention`

```python
class MediaMention(BaseModel):
    title: str
    url: str
    source: str                       # publication / podcast / award name
    kind: Literal["press", "podcast", "award", "mention"]
    date: datetime | None = None
```

### `CrossReferenceSignals`

```python
class CrossReferenceSignals(BaseModel):
    """Raw observations only — the collector never computes a judgment."""

    team_size_claim: str | None = None        # regex-captured, e.g. "team of 6"
    linkedin_employee_count: int | None = None   # company page only, no people
    hiring_page_active: bool | None = None
    last_funding_round: FundingRound | None = None
    copyright_year: int | None = None
    last_blog_post_at: datetime | None = None
    tech_vs_claim_mismatches: list[str] = []
```

### `ProviderRunMetadata`

```python
class ProviderRunMetadata(BaseModel):
    status: Literal["ok", "degraded", "failed", "not_configured"]
    latency_ms: int
    error: str | None = None
    provider_version: str
```

## Invariants

- **Raw observations, not inference.** `CrossReferenceSignals` captures what
  was present on the page; it never computes "small team but high headcount
  claim — possible inflation." Inference is the downstream synthesis
  model's job.
- **Missing is not broken.** Every optional field is nullable. A provider
  that can't fill its slot sets `provenance[slug].status: "degraded"` or
  `"not_configured"`; the field stays null.
- **`extra="forbid"`.** Unknown fields raise on construct — keeps drift
  loud.
- **Versioned.** Schema version lives alongside `__version__`; bumps follow
  SemVer. Adding an optional field is a PATCH; adding a required field or
  renaming is a MINOR (pre-1.0) / MAJOR (post-1.0).

## Validation

- `companyctx validate <path/to/file.json>` round-trips a payload through
  the Pydantic model and returns exit code 0 on success.
- The two-phase acceptance protocol (blind-eval → 2-week A/B) for integrating
  `companyctx` into a production pipeline lives in `docs/VALIDATION.md`.

## Further reading

- `docs/SPEC.md` — full frozen v0.1 spec.
- `docs/ARCHITECTURE.md` — how the envelope gets populated by the
  Deterministic Waterfall.
- `docs/PROVIDERS.md` — which provider fills which part of the schema.
