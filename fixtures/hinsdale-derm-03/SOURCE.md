# SOURCE — hinsdale-derm-03

Part of the **real golden corpus** (issue #24, v0.1.0 release gate). This
fixture is a sanitized snapshot of a real site the external B2B brief
pipeline processed on `2026-04-11`. The oracle (`expected.json`) is frozen;
the `.hand-curated` marker in this directory makes
`scripts/build-fixtures.py` refuse to overwrite it.

## Inputs (what the extractor sees)

- `homepage.html`, `about.html`, `services.html` — **structural
  skeletons** produced by fetching the real site, dropping every
  non-content tag (scripts, styles, iframes, svgs, forms, navs, footers,
  tracking), then rewriting identity tokens to the fixture slug and
  masking contact PII. The surviving markup is the site's real h1..h6 /
  p / li / blockquote structure with its real text content after name and
  PII sanitization. Where the site returned 404 for /about or /services,
  the stub page explicitly says the external pipeline did not capture
  that URL.
- `google_places.json`, `yelp.json`, `youtube.json` — provider-response
  fixtures whose review counts, ratings, and channel metadata are
  cross-checked against `raw_observations.json` by
  `tests/test_real_golden_corpus.py` so they cannot drift silently.

## Oracle (what must match)

- `expected.json` — the envelope companyctx must produce when it runs
  against the sanitized HTML above. Any extractor, tech-stack detector,
  or envelope-serializer change that shifts the output fails the test.
- `raw_observations.json` — the **non-envelope** half of the oracle:
  review/rating/social signals the external pipeline recorded verbatim.
  Today these fields sit outside the envelope because v0.1 only wires
  `site_text_trafilatura`; when future providers surface them in the
  envelope, the regenerated `expected.json` must continue to agree with
  `raw_observations.json`.

## Source artifact

- Artifact date: `2026-04-11`
- Artifact id: `brief-29cc51c3333a` (opaque sha256 prefix — the partner
  reverse-maps this privately to the specific research-brief.md in a
  private partner repo on the local machine)

The brief path, subject name, and real domain never appear in this public
repo. Identifiers in the sanitized HTML are rewritten to
`hinsdale-derm-03.example` / "Hinsdale Derm 03" and any personal name to "the Owner";
contact PII is masked per `fixtures/README.md` (emails →
`hello@example.test`, phones → `(555) 555-0100`, ZIPs → `00000`).

## What drift trips which test

- Extractor change that decodes sanitized markup differently →
  `test_envelope_matches_hand_curated_oracle[hinsdale-derm-03]` fails.
- Provider-JSON fixture edit that diverges from the captured
  observations → `test_{google,yelp,youtube}_fixture_matches_observations[hinsdale-derm-03]`
  fails.
- Attempt to regenerate this directory with `scripts/build-fixtures.py`
  while the marker is present →
  `test_build_fixtures_refuses_to_overwrite_hand_curated` fails.
