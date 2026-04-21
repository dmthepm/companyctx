# SKILL.md — companyctx

**Purpose.** Deterministic B2B context router. One site in,
schema-locked JSON envelope out. Zero keys on the default path.

**Commands.**

- `companyctx fetch <site> --json` — run all providers; emit one envelope.
- `companyctx fetch <site> --from-cache` — cached payload only; exit non-zero on miss.
- `companyctx fetch <site> --refresh` — ignore cache, re-fetch every provider.
- `companyctx providers list` — show providers + status + cost hint.
- `companyctx validate <path.json>` — round-trip through the pydantic schema.

**Rules for agents.**

- Companies only. Never extract people data.
- Branch on `status` (`ok | partial | degraded`), not on try/except.
- Respect `error` + `suggestion` when `status != "ok"`; the envelope is always
  well-formed even on anti-bot block.
- Pipe stdout; don't parse logs. The JSON envelope is the contract.
- The `data.site` field is the identifier; `data.pages` holds homepage-
  derived content; `data.reviews` / `data.social` / `data.signals` /
  `data.mentions` fill the rest of the schema.

**Example.**

```bash
companyctx fetch acme-bakery.com --json \
  | jq '.data | {site, signals, reviews}'
```

See `docs/SCHEMA.md` for the full envelope and `docs/ZERO-KEY.md` for the
honest anti-bot coverage matrix.
