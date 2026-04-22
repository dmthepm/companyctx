# Security policy

`companyctx` is a CLI that fetches user-supplied URLs over the network. That
surface is a classical security hotspot: SSRF, DNS rebinding, resource
exhaustion, and supply-chain risk all apply. This document tells you how to
report vulnerabilities, what versions we fix, and what defences the tool
ships.

The full threat catalogue — attack → current behaviour → remediation → test
coverage — lives in [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md).

## Supported versions

During the `0.1.x` line we fix security issues only on the latest minor
release. Users on older `0.1.x` are asked to upgrade. Past `1.0.0` we will
maintain fixes on the current and previous minor.

| Version   | Security fixes |
| --------- | -------------- |
| `0.1.x`   | Latest patch only |
| `< 0.1`   | No fixes — pre-release |

## Reporting a vulnerability

Please report vulnerabilities privately. We do **not** want security reports
filed as public GitHub issues.

Preferred channels, in order:

1. **GitHub Security Advisories.** Open a private advisory at
   [`dmthepm/companyctx` → Security → Advisories → Report a vulnerability`](https://github.com/dmthepm/companyctx/security/advisories/new).
   GitHub notifies the maintainer, gives us a private fork to work in, and
   coordinates the CVE when relevant. This is the preferred path.
2. **Email.** `security@noontide.co`. Include a description of the issue,
   reproduction steps, affected versions, and your preferred disclosure
   timeline. Encrypt with the Noontide Collective GPG key if you need to
   (fingerprint published in `docs/SECURITY-PGP.md` once issued).

Please do not contact the maintainer over Slack, Twitter, Linear, or any
channel that would make the report public before we can ship a fix.

## What counts as a vulnerability

In scope:

- SSRF, DNS rebinding, or any way `companyctx fetch <url>` can reach a
  non-public destination it should have rejected (loopback, RFC 1918,
  link-local, cloud metadata endpoints).
- Path traversal out of the `fixtures/` tree during `--mock`.
- Resource-exhaustion bypasses (response-size cap, redirect cap, timeout).
- Secrets leakage via `--verbose`, logs, or error output.
- Supply-chain issues in direct dependencies (active CVEs, abandoned
  packages, typosquatting).

Out of scope:

- Issues that require an attacker to already control the `companyctx`
  process (arbitrary-code-execution on a machine where the CLI is installed
  is not a privilege escalation).
- DoS attacks against user-deployed instances (not our layer; see issue #53
  scope).
- Theoretical TLS-impersonation weaknesses in `curl_cffi` whose fix must
  land upstream — we will track and pin, not patch.

## Response timeline

- Initial acknowledgement: within **3 working days** of receipt.
- Triage + severity call: within **7 working days**.
- Fix or mitigation in `main`: within **30 days** for high/critical,
  **90 days** for low/medium, or coordinated disclosure if a longer window
  is appropriate.
- Public advisory published at fix release. Reporter credited unless they
  opt out.

## Defences shipped by the tool

This is a summary; the source of truth is `docs/THREAT-MODEL.md`.

- **SSRF.** Scheme whitelist (`http`, `https` only); every URL is DNS-
  resolved and every resolved IP is checked against the non-global blocklist
  (`ipaddress.IPv4Address.is_global`); redirects are followed manually with
  per-hop revalidation; cloud-metadata vanity hostnames (e.g.
  `metadata.google.internal`) are refused without DNS.
- **Resource limits.** Response bodies are streamed and capped at 10 MiB;
  `Content-Length` is checked up front; redirects are capped at 5; per-
  request timeout is 10 seconds.
- **Path traversal.** Fixture slugs must match `^[a-z0-9][a-z0-9_-]*$`; the
  resolved fixture root must lie under `fixtures_dir` (symlink escape is
  refused).
- **Secrets.** `--verbose` prints only slug, envelope status, and latency —
  no headers, env vars, or response bodies. No `.env` is read; secrets flow
  via provider-specific env vars (none on the default zero-key path).
- **Supply chain.** `curl_cffi` is pinned `~=0.15.0` so a major bump that
  changes the bundled libcurl-impersonate is a deliberate version change.
- **robots.txt.** Respected by default. `--ignore-robots` is a CLI-only
  flag; there is no environment variable or TOML key that can enable it.

## Hardening defaults for operators

If you run `companyctx` inside an automated pipeline, we recommend:

- Run as an unprivileged user with no cloud credentials in the environment.
- Confine outbound network egress to the public internet (egress firewall
  blocking RFC 1918 and link-local at the network layer). Our in-process
  blocklist is defence-in-depth, not a substitute for network policy.
- Pin `companyctx` to an exact version in your lockfile.

---

_Last reviewed: 2026-04-22 (issue #53 / COX-23)._
