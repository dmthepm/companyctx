---
type: research
date: 2026-04-22
topic: Shape-balanced zero-key probe for Wix / Webflow / SPA homepages
category: zero-key-coverage
status: complete
supersedes_placeholder_in: []
linked_issues:
  - https://github.com/dmthepm/companyctx/issues/32
  - https://github.com/dmthepm/companyctx/issues/21
  - https://github.com/dmthepm/companyctx/issues/22
raw_evidence: research/2026-04-22-wix-webflow-spa-probe-raw.jsonl
---

# Shape-balanced zero-key probe — Wix / Webflow / SPA homepages

## One-sentence summary

On a deliberately shape-balanced 15-site probe spanning Wix, Webflow, and
React/Next SPA marketing homepages, `curl_cffi @ chrome146` returned
**HTTP 200 on 14 of 15** reachable endpoints with **13 of those 14**
yielding ≥ 1 KB of extracted `homepage_text` — no zero-key coverage
regression vs. the [2026-04-21 TLS spike](2026-04-21-tls-impersonation-spike.md)
or the [100-site durability run](../fixtures/durability-report-2026-04-21.md)
on these platform cohorts.

## Why this probe

The TLS-library spike ([PR #26](https://github.com/dmthepm/companyctx/pull/26) /
issue [#21](https://github.com/dmthepm/companyctx/issues/21)) picked
`curl_cffi` on a 20-site probe; the 100-site durability run
([PR #41](https://github.com/dmthepm/companyctx/pull/41) /
issue [#22](https://github.com/dmthepm/companyctx/issues/22)) widened the
N. Both drew from a WordPress-dominated partner seed list — the TLS
spike's tech-stack breakdown recorded 16/20 WordPress, 0 Wix, 0 Webflow,
0 SPA. Issue [#21](https://github.com/dmthepm/companyctx/issues/21)'s
scope named Wix, Webflow, and JS-heavy SPA homepages explicitly, so the
`20/20` headline number was honestly scoped but did not yet cover those
classes. This probe closes that evidence gap per issue
[#32](https://github.com/dmthepm/companyctx/issues/32) (Linear COX-17).

## Scope boundary

**In scope for this probe:**

- Deliberately source ~5 Wix, 5 Webflow, and 5 React/Next SPA
  small-business-shape homepages and run the current zero-key fetcher
  against them.
- Report HTTP outcome, response bytes, extracted text bytes (after
  trafilatura), and the measured platform shape per site.
- Fold the results into the zero-key coverage story; touch `README.md`
  or `docs/ZERO-KEY.md` only if the new evidence **materially** changes
  the current measured claim.

**Out of scope (carry-overs, not blockers):**

- Re-litigating the `curl_cffi` library pick — the license + API-match
  rationale is platform-independent and is not affected by any finding
  below.
- Adding SPA-framework signatures to the production
  `companyctx.extract.detect_tech_stack` detector — the probe-local
  shape detector in `scripts/run-shape-probe.py` is harness-only; the
  production detector's scope decision stays with its owning issue.
- Probing Cloudflare-fronted or DataDome-fronted sites specifically —
  that's the fingerprint-freshness axis, covered by the TLS spike's
  `chrome131` stale-fingerprint run.

## Cohort design

Fifteen public sites, five per hypothesized platform. The candidate
list lives at `.context/cox-17-probe/candidates.csv` (gitignored
scratch — the host list is reproduced below so every number in this
write-up can be re-derived without the scratch file).

Sources follow the three clusters issue #21 named: Wix platform /
customer pages, documented Webflow-customer marketing sites, and public
React/Next-framework marketing homepages.

| Expected | Host                    | Sourcing rationale |
|----------|-------------------------|--------------------|
| wix      | `www.wix.com`           | Wix corporate site — built on Wix |
| wix      | `www.editorx.com`       | Wix Studio / EditorX marketing — Wix-owned |
| wix      | `www.wixanswers.com`    | Wixanswers support product — Wix-owned (domain retirement surfaced mid-probe) |
| wix      | `support.wix.com`       | Wix help-centre top-level — Wix-rendered |
| wix      | `manage.wix.com`        | Wix account dashboard landing — JS-rendered shell |
| webflow  | `webflow.com`           | Webflow's own marketing — built on Webflow |
| webflow  | `www.lattice.com`       | Documented Webflow customer |
| webflow  | `www.attentive.com`     | Documented Webflow customer |
| webflow  | `www.ramp.com`          | Documented Webflow customer (snapshot shows Next.js — see §Platform drift) |
| webflow  | `www.loom.com`          | Documented Webflow customer (snapshot shows Next.js — see §Platform drift) |
| spa      | `vercel.com`            | Next.js (Vercel's own marketing site) |
| spa      | `linear.app`            | Next.js marketing site |
| spa      | `supabase.com`          | Next.js marketing site |
| spa      | `resend.com`            | Next.js marketing site |
| spa      | `railway.com`           | React-rendered marketing site |

## Methodology

- **Fetcher.** `curl_cffi` pinned to `impersonate="chrome146"` — the
  exact library + fingerprint
  [`companyctx/providers/site_text_trafilatura.py`](../companyctx/providers/site_text_trafilatura.py)
  ships in v0.1.0. The harness calls `curl_cffi.requests.get(url,
  impersonate="chrome146", timeout=15, allow_redirects=True)` directly
  — mirroring the provider's `_stealth_fetch` at the one-URL level
  without the redirect-manual-walk + response-size cap (neither fired
  on this cohort).
- **Extractor.** `companyctx.extract.extract_body_text` — the same
  trafilatura wrapper the provider uses. Extract-length is the
  UTF-8-encoded byte length of what trafilatura emits.
- **Shape detection.** Probe-local
  ([`scripts/run-shape-probe.py:detect_shape`](../scripts/run-shape-probe.py)).
  Checks high-specificity SPA-build-artefact markers
  (`__NEXT_DATA__`, `/_next/static/`, `__NUXT__`, `/_nuxt/`,
  `data-wf-page`, `data-wf-site`, `class="w-layout`,
  `static.parastorage.com`) first, then falls back to the
  production `detect_tech_stack` loose substring matches. The stricter
  pass corrects known false-positives — e.g. `linear.app` mentions the
  string "webflow" three times in its Next.js-rendered marketing copy,
  which the production detector would label as Webflow.
- **Pacing + robots.** 2-second pacing floor between requests;
  `robots.txt` checked via `companyctx.robots.is_allowed` before every
  fetch (no `--ignore-robots` on this run).
- **Harness source.**
  [`scripts/run-shape-probe.py`](../scripts/run-shape-probe.py) —
  committed; re-runnable against any CSV with `expected_shape,host,note`
  columns. The harness writes per-site JSON to
  `.context/cox-17-probe/runs/` (gitignored) and a shape-bucketed
  JSONL (this file's raw evidence) to whatever `--out` points at.
- **Run date:** 2026-04-22.
- **Library versions:** `curl_cffi 0.15.0`, `trafilatura 2.0.0`.

**Committed evidence.**
[`research/2026-04-22-wix-webflow-spa-probe-raw.jsonl`](2026-04-22-wix-webflow-spa-probe-raw.jsonl)
— 15 rows carrying `expected_shape`, `host`, `detected_shape`,
`outcome`, `status`, `bytes`, `extract_bytes`, `elapsed_ms`, `error`,
`tech_stack`. Hostnames are committed because the sources (corporate
marketing sites, documented public customers, public SaaS homepages)
are already-public — unlike the TLS spike's partner-private slug list.

## Results

### Per-site

| Host                  | Measured shape | HTTP | Response bytes | Extract bytes | Outcome |
|-----------------------|----------------|------|----------------|---------------|---------|
| `www.wix.com`         | wix            | 200  | 2,289,322      | 13,008        | ok      |
| `www.editorx.com`     | wix            | 200  | 2,101,942      | 11,464        | ok      |
| `www.wixanswers.com`  | —              | 404  | 3,059          | 0             | http_404 |
| `support.wix.com`     | wix            | 200  | 989,843        | 1,250         | ok      |
| `manage.wix.com`      | wix            | 200  | 11,998         | 0             | thin    |
| `webflow.com`         | webflow        | 200  | 708,707        | 2,231         | ok      |
| `www.lattice.com`     | webflow        | 200  | 326,165        | 2,404         | ok      |
| `www.attentive.com`   | webflow        | 200  | 293,504        | 1,532         | ok      |
| `www.ramp.com`        | next           | 200  | 1,442,003      | 3,215         | ok      |
| `www.loom.com`        | next           | 200  | 208,217        | 2,510         | ok      |
| `vercel.com`          | next           | 200  | 954,469        | 1,874         | ok      |
| `linear.app`          | next           | 200  | 2,303,172      | 1,119         | ok      |
| `supabase.com`        | next           | 200  | 377,330        | 10,517        | ok      |
| `resend.com`          | next           | 200  | 449,707        | 12,580        | ok      |
| `railway.com`         | react          | 200  | 687,757        | 1,573         | ok      |

`outcome` is thin when HTTP 200 returned but extract < 1,024 bytes (the
durability-report `FM7_THIN_BYTES` threshold); ok when both fetch and
extract cleared that threshold; `http_4xx` otherwise.

### Aggregate

| Cohort (measured shape) | n  | HTTP 200 | ≥ 1 KB extract | Blocked | Thin | 404 |
|-------------------------|----|----------|----------------|---------|------|-----|
| Wix                     | 4\*| 4/4      | 3/4            | 0       | 1    | 0   |
| Webflow                 | 3  | 3/3      | 3/3            | 0       | 0    | 0   |
| Next.js SPA             | 6  | 6/6      | 6/6            | 0       | 0    | 0   |
| React SPA               | 1  | 1/1      | 1/1            | 0       | 0    | 0   |
| **Total (reachable)**   | 14 | 14/14    | 13/14          | 0       | 1    | —   |
| Unreachable (404)       | 1  | —        | —              | —       | —    | 1   |

\* Excludes `www.wixanswers.com` which returned HTTP 404 (the Wixanswers
product was rebranded into `support.wix.com`; the domain still resolves
but serves a 404 HTML). Not a fetcher failure — the endpoint is gone.

## Plain-language findings

1. **`curl_cffi @ chrome146` is not the bottleneck on any of the three
   site classes in this cohort.** Every reachable Wix, Webflow,
   Next.js-SPA, and React-SPA endpoint returned HTTP 200. No
   Cloudflare / Akamai / DataDome challenge fired. No `blocked_by_antibot`
   observations. This is consistent with the TLS-spike finding that
   fingerprint-freshness is the real decay mode — none of these
   platforms index the current Chrome 146 JA3 at a level that blocked
   the probe.
2. **Usable text-extract on the Wix / Webflow / Next-SPA cohorts is
   essentially the same as the WordPress-heavy durability cohort.**
   13 / 14 reachable sites cleared the 1 KB extract threshold — 93%.
   The single thin result is `manage.wix.com`, Wix's own account
   dashboard, which serves a 12 KB React-shell HTML with the real
   content rendered client-side. That matches
   [`docs/ZERO-KEY.md`](../docs/ZERO-KEY.md)'s existing "JS-heavy SPAs
   that need a real browser" row — the dashboard ships the shell, the
   shell lacks extractable copy, the provider reports thin, the
   waterfall routes to Attempt 2. No matrix copy change needed.
3. **Next.js marketing sites are in the covered cohort, not the SPA
   failure cohort.** Every site the probe labelled `next` returned
   ≥ 1 KB of body text because SaaS marketing pages SSR-render their
   copy. The "JS-heavy SPA" decay pattern in
   [`docs/ZERO-KEY.md`](../docs/ZERO-KEY.md) triggers on
   *client-only-rendered* app shells — the dashboard class, not the
   marketing class. Worth a one-line footnote in ZERO-KEY, which is
   being added in this PR; not a material claim change.
4. **No zero-key coverage regression to report for Wix / Webflow /
   SPA-heavy cohorts.** The 100-site durability run's **97 / 100**
   `status: ok` number is not affected by this probe — this probe is
   evidence *alongside* that run, not a recount of it.

## Platform drift — a methodology lesson

Two of the five `expected_shape=webflow` picks (`www.ramp.com`,
`www.loom.com`) came back `detected_shape=next`. Both are documented
Webflow customers in older public customer lists. Either the
documentation is stale or these companies migrated their marketing
sites to Next.js since. Either way the probe's shape labelling follows
what the HTML returned on 2026-04-22, not what a third-party customer
list claimed. Future re-runs should re-verify platform before
publishing, not rely on the candidate list's expected-shape column —
the harness records both, so mis-classifications surface immediately.

## Reproducibility

Re-run against the same 15-site list:

```bash
python3 scripts/run-shape-probe.py \
    --candidates <path-to-candidates.csv> \
    --out .context/cox-17-probe
```

The committed CSV header is `expected_shape,host,note`; any file with
those columns works. Per-site JSON lands in `--out/runs/`; the
shape-bucketed JSONL (matching
[`research/2026-04-22-wix-webflow-spa-probe-raw.jsonl`](2026-04-22-wix-webflow-spa-probe-raw.jsonl)
byte-for-byte given the same snapshot) lands in `--out/probe-raw.jsonl`.

Every headline number in this addendum is reconstructable from that
JSONL:

```bash
python3 -c "
import json, collections
rows = [json.loads(l) for l in open('research/2026-04-22-wix-webflow-spa-probe-raw.jsonl')]
print('outcome:', dict(collections.Counter(r['outcome'] for r in rows)))
print('shape  :', dict(collections.Counter(r['detected_shape'] for r in rows)))
print('ok  (>=1KB extract):', sum(r['outcome'] == 'ok' for r in rows))
print('thin (<1KB extract):', sum(r['outcome'] == 'thin' for r in rows))
print('http_4xx           :', sum((r['outcome'] or '').startswith('http_') for r in rows))
"
```

## Does this change the current measured claim?

**No material change.** [`docs/ZERO-KEY.md`](../docs/ZERO-KEY.md)'s
matrix was already correctly structured: small-biz Wix/Webflow in the
"full payload" row, JS-heavy app-shell SPAs in the "HTML shell only"
row. This addendum adds empirical backing for both rows and one
footnote clarifying that SSR-rendered SPA *marketing* sites sit in the
covered cohort, not the decay cohort. The README hero's measured-claim
text (20/20 on the TLS spike) is untouched — this probe is a separate
sample, not a re-measurement of the spike's 20 sites.

## Out of scope (deferred)

- Broadening the SPA cohort to include *client-only-rendered* SPAs
  (not dashboards) — the decay mode ZERO-KEY.md flags. Target candidates
  would be create-react-app-style marketing sites that never SSR.
  Tracked as candidate follow-up; not a v0.1.0 gate.
- Folding a SPA-framework signature set into the production
  `detect_tech_stack` — would let the envelope's `tech_stack` field
  report Next/Nuxt/React/Vue. The probe's strict detector is the
  prototype; promotion is a separate design/test pass.
- Cross-CDN probe (DataDome / Akamai / Kasada) — the fingerprint-freshness
  decay axis; tracked against smart-proxy work
  ([#6](https://github.com/dmthepm/companyctx/issues/6)).
