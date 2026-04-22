# SOURCE — northarlington-pharmacy-01

Part of the **real golden corpus** (issue #24, v0.1.0 release gate). The
oracle (`expected.json`) is **hand-curated** from raw observations captured
by the external B2B brief pipeline against the real site this fixture is
sanitized from. The oracle is **frozen** — the `.hand-curated` marker in
this directory makes `scripts/build-fixtures.py` refuse to overwrite it.

## Source artifact

- Artifact date: `2026-04-10`
- Artifact id: `brief-b84ae44060b4` (opaque, stable across regeneration)

The underlying brief lives in the partner's private pipeline repository on
the local machine. It is not referenced by path, slug, or subject name from
this public repo; the opaque `artifact id` lets the partner reverse-map
privately without leaking client identity here. Only raw observations
(homepage text, about text, services list, review counts, ratings, social
follower counts) are reflected in this fixture.

## Sanitization

Site identity is rewritten to the slug `northarlington-pharmacy-01` (display name "Northarlington Pharmacy 01").
Contact PII is masked per `fixtures/README.md` (emails → `*.example.test`,
phones → `(555) 555-0100`, contact names → "the Owner"). No client name,
personal name, real domain, or real phone number appears in any file in
this directory.

Review counts, ratings, and social follower counts are **preserved
verbatim** because they are the raw signal the external pipeline captured
and the whole point of having an oracle.

## Drift detection

`tests/test_real_golden_corpus.py` runs `companyctx fetch
northarlington-pharmacy-01.example --mock --json` and diffs the output against `expected.json`
(modulo `fetched_at`). Any change in the envelope shape, extractor
behavior, or provider wiring that shifts the output away from this oracle
fails the test loudly — that is the point of the real golden corpus.
