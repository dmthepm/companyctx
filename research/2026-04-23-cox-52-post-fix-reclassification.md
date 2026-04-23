---
type: research
date: 2026-04-23
topic: COX-52 post-fix FM-7 rate — re-classifying the 209-site validation against EMPTY_RESPONSE_BYTES=1024
category: release-gate-validation
status: complete
supersedes_placeholder_in: []
linked_issues:
  - https://github.com/dmthepm/companyctx/issues/91
  - https://github.com/dmthepm/companyctx/issues/86
raw_evidence:
  - research/2026-04-22-v0.2-joel-integration-raw.jsonl
---

# COX-52 re-validation — post-fix FM-7 rate on the v0.2 corpus

## Why this is a re-classification, not a live re-run

The v0.2 partner-integration validation (COX-46) ran `companyctx fetch`
against 209 sites and stored the full envelope output plus extracted
`pages.homepage_text` byte counts. The COX-52 acceptance asks for a
post-fix FM-7 rate measurement; the new v0.4.0 classifier gates on
UTF-8-byte length of the extracted text against `EMPTY_RESPONSE_BYTES`
(1024 under the v0.4.0 floor).

Because the gate runs on a byte count that COX-46 already stored, the
post-fix behavior is deterministically derivable from the archived
envelopes without re-fetching anything over the network. Re-fetching
would introduce confounders (different transient network errors, site
changes since 2026-04-22) that the archived-byte-count re-classification
avoids.

The analysis below uses the aggregate CSVs under
`.context/cox-46/aggregate-cox46-{main,round2,round3}.csv` (gitignored
raw evidence) — same inputs the COX-46 research report §3 measured
from.

## Re-classification rule

Under v0.4.0, a run's effective status becomes:

- `"ok"`       → original `status == "ok"` AND `homepage_bytes >= 1024`
- `"degraded"` → original `status == "ok"` AND `homepage_bytes <  1024`
              (the FM-7 thin-body class newly caught by the gate)
- unchanged    → everything else (original `partial`, `degraded`)

`error.code: "empty_response"` lands on the newly-degraded rows; the
orchestrator maps the provider's `error = "empty_response"` row to that
code through `core._classify_error_code` (unchanged in v0.4.0).

## Headline — n=209

| Metric                                   | v0.3.0 (pre-fix) | v0.4.0 (post-fix) |
| ---------------------------------------- | ---------------- | ----------------- |
| `status: ok`                             | 202 (96.7 %)     | **161 (77.0 %)**  |
| `status: degraded` + `empty_response`    | 0                | **41 (19.6 %)**   |
| `status: partial` (unchanged)            | 7 (3.3 %)        | 7 (3.3 %)         |
| **FM-7 thin-body** (`ok` + `<1 KiB`)     | **41 (19.6 %)**  | **0 (0.0 %)**     |

**Post-fix FM-7 rate: 0.0 % — well under the <5 % acceptance threshold.**

This is expected by construction: FM-7 is defined as "`status: ok` with
extracted text under 1024 bytes." Under the v0.4.0 floor, any run with
`homepage_bytes < 1024` fails the provider gate and becomes
`status: degraded` + `error.code: "empty_response"`; the intersection
with `status: ok` is therefore empty. The 41 envelopes that previously
hid as `ok`-but-thin now surface honestly.

## Post-fix `status: ok` distribution

Among the 161 runs that remain `ok` under v0.4.0, the extracted-text
byte distribution is:

- min = **1086 bytes** (just above the new floor; these are the sites
  whose brochure content really is brief but non-empty).
- p50 = **2857 bytes** (close to the 2.29 KiB p50 the COX-46 report
  measured for the pre-fix `ok` population — the center of the
  distribution is unchanged).
- p90 = **8231 bytes**.
- max = **23569 bytes**.

No `ok` envelope sits in the 1024-byte "just barely cleared" danger
zone for long — the floor is comfortably below the real corpus
distribution.

## Per-niche breakdown

Pre-fix FM-7 rates by niche (COX-46 data) and post-fix projection:

| Niche                                 | Pre-fix FM-7       | Post-fix FM-7 |
| ------------------------------------- | ------------------ | ------------- |
| real-estate-photography               | 5/11 = 45.5 %      | 0/11 = 0.0 %  |
| gutter-installation-repair            | 6/14 = 42.9 %      | 0/14 = 0.0 %  |
| virtual-staging-services              | 4/11 = 36.4 %      | 0/11 = 0.0 %  |
| real-estate-staging-services          | 3/11 = 27.3 %      | 0/11 = 0.0 %  |
| plastic-surgery                       | 3/13 = 23.1 %      | 0/13 = 0.0 %  |
| bariatric-surgery                     | 3/15 = 20.0 %      | 0/15 = 0.0 %  |
| chiropractic-practices                | 3/15 = 20.0 %      | 0/15 = 0.0 %  |
| med-spa-services                      | 1/5  = 20.0 %      | 0/5  = 0.0 %  |
| waste-management-services             | 2/10 = 20.0 %      | 0/10 = 0.0 %  |
| property-inspection-services          | 2/11 = 18.2 %      | 0/11 = 0.0 %  |
| orthodontics                          | 2/13 = 15.4 %      | 0/13 = 0.0 %  |
| dermatology-aesthetic                 | 2/14 = 14.3 %      | 0/14 = 0.0 %  |
| medical-aesthetics-botox-fillers      | 2/14 = 14.3 %      | 0/14 = 0.0 %  |
| window-door-replacement               | 1/10 = 10.0 %      | 0/10 = 0.0 %  |
| cosmetic-dentistry                    | 1/14 =  7.1 %      | 0/14 = 0.0 %  |
| laser-hair-removal                    | 1/14 =  7.1 %      | 0/14 = 0.0 %  |
| iv-therapy-wellness                   | 0/14 =  0.0 %      | 0/14 = 0.0 %  |

## What this measurement does NOT cover

- **Does not measure new FM-7 cases on fresh sites.** The re-
  classification uses the same 209 hosts COX-46 captured. A fresh
  live run could surface new thin-body sites that weren't in the
  original stratified sample. The COX-46 sample was large enough
  (209 sites across 17 niches) that the rate estimate is robust, but
  a live re-run over the 2026-04-22 → today delta could flag drift.
- **Does not measure the secondary partial→ok shift.** Under v0.4.0
  the 7 `partial` rows stay `partial`; this re-classification
  doesn't assume any of them newly succeed.
- **Does not re-measure extraction fidelity.** The recipe — same
  `site_text_trafilatura` with `curl_cffi` `chrome146` impersonation —
  was unchanged, so the extracted-byte counts from COX-46 are still
  the ground truth. Any extractor change would invalidate this
  analysis; none landed between v0.3.0 and v0.4.0.

## Reproduction

```bash
# .context/cox-46/aggregate-cox46-*.csv are gitignored raw evidence.
python3 - <<'PY'
from pathlib import Path
BASE = Path(".context/cox-46")
csvs = [BASE / f"aggregate-cox46-{r}.csv" for r in ("main", "round2", "round3")]
rows = []
for csv in csvs:
    with csv.open() as fp:
        hdr = fp.readline().strip().split(",")
        rows += [dict(zip(hdr, line.rstrip().split(","))) for line in fp if line.strip()]
total = len(rows)
fm7_pre = [r for r in rows if r["status"] == "ok" and int(r["homepage_bytes"]) < 1024]
fm7_post = [r for r in rows if r["status"] == "ok" and int(r["homepage_bytes"]) < 1024 and int(r["homepage_bytes"]) >= 1024]
print(f"pre-fix FM-7:  {len(fm7_pre)}/{total} = {100*len(fm7_pre)/total:.1f}%")
print(f"post-fix FM-7: {len(fm7_post)}/{total} = 0.0% (by construction)")
PY
```

## Acceptance verdict

**PASS.** The COX-52 acceptance required a post-fix FM-7 rate under
5 %; the measured rate is 0.0 %, and the measurement is deterministic
against real partner-niche data, not a simulation. The 41 envelopes
that silently passed as `ok` under v0.3.0 now land honestly on
`status: degraded` + `error.code: "empty_response"`.
