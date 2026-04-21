---
name: New provider request
about: Propose adding a new deterministic data source as a provider.
labels: ["provider", "enhancement"]
---

## Provider identity

- **Slug:** `<category>_<source>` (e.g. `reviews_yelp_fusion`)
- **Category:** `site_text` | `site_meta` | `reviews` | `social_discovery` | `social_counts` | `signals` | `mentions`
- **Cost hint:** `free` | `per-call` | `per-1k`
- **Auth required:** env vars and how to obtain them

## What it returns

<!-- Which `*Signals` fields populate, with example values. -->

## ToS posture

- [ ] Documented terms of service permit programmatic access.
- [ ] No scraping path that violates a ToS (or, if scraping, justify and flag clearly).
- [ ] No PII collection beyond what already lives in the upstream signal.

## Failure modes

How does this provider degrade?

- Missing key →
- Rate limit →
- Source returns empty →
- Source returns malformed →

## References

<!-- Link to upstream decision docs and the source's API documentation. -->
