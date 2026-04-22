# Threat model

`companyctx` is a public MIT CLI that fetches user-supplied URLs over the
network. The surface — *user passes a URL, tool fetches it* — is a
well-known class of security risk. This document catalogues every threat
we have considered, the current implementation, the residual risk, and the
tests that lock the behaviour in.

First audit: **2026-04-22** (issue
[#53](https://github.com/dmthepm/companyctx/issues/53) / COX-23 / Linear
`COX-23`). Re-review cadence: on every non-trivial change to
`companyctx/security.py`, `companyctx/providers/site_text_trafilatura.py`,
`companyctx/robots.py`, or to the declared direct dependencies in
`pyproject.toml`.

For the reporting procedure and disclosure timeline see
[`SECURITY.md`](../SECURITY.md).

## Trust model

- **Adversary.** Any third party who can influence the URL the operator
  passes to `companyctx fetch`. In practice this is the list of prospect
  URLs supplied to a cold-outreach pipeline — often scraped or
  user-submitted, therefore untrusted.
- **Operator.** The human or pipeline running the CLI. Assumed benign,
  assumed to supply honest flags (`--ignore-robots` is a deliberate
  operator action).
- **Tool.** `companyctx` itself. Runs in the operator's environment with
  whatever network egress and filesystem access the operator grants. We
  minimise what the tool *requests*; we cannot minimise what the host
  *grants*.
- **Residual assumption.** Operators deploy the tool behind a network
  egress policy that blocks RFC 1918 and link-local at the network layer.
  The in-process SSRF check is defence-in-depth, not a substitute.

## Threat catalogue

### 1. SSRF (Server-Side Request Forgery)

**Attack.** Adversary supplies a URL that points at a non-public destination
the operator's host can reach: cloud-metadata endpoints, local services,
RFC 1918 intranets, IPv6 loopback/link-local. Variants include
DNS-rebinding (a hostname resolves public at registration, private at
fetch time).

| Probe                                         | Expected response             |
| --------------------------------------------- | ----------------------------- |
| `http://169.254.169.254/latest/meta-data/`    | reject (cloud metadata)       |
| `http://localhost:5432/`                      | reject (loopback)             |
| `http://127.0.0.1:6379/`                      | reject (loopback)             |
| `http://10.0.0.1/`, `http://192.168.0.1/`     | reject (RFC 1918)             |
| `http://172.16.0.1/` / `172.31.255.255/`      | reject (RFC 1918)             |
| `http://[::1]/`, `http://[fe80::1]/`          | reject (IPv6 loopback / LL)   |
| `file:///etc/passwd`                          | reject (scheme)               |
| `gopher://`, `ldap://`, `dict://`, `ftp://`   | reject (scheme)               |
| `http://metadata.google.internal/`            | reject (metadata vanity host) |
| DNS-rebinding target (A record → private IP)  | reject at time-of-check       |

**Current behaviour.** `companyctx/security.py::validate_public_http_url`:

- scheme must be `http` or `https`;
- hostname cannot be empty;
- known cloud-metadata vanity hostnames are refused before DNS (belt and
  suspenders against a hostile resolver);
- `socket.getaddrinfo` resolves the hostname; every returned address is
  checked with `ipaddress.ip_address(...).is_global`, which collapses
  loopback / link-local / RFC 1918 / reserved / multicast / unspecified
  into one predicate.

The provider
(`companyctx/providers/site_text_trafilatura.py::_stealth_fetch`) calls the
validator up front, disables curl_cffi's auto-redirects
(`allow_redirects=False`), and follows redirects manually so each
`Location` hop is re-validated before the next request is issued. Up to
`MAX_REDIRECTS=5` hops.

The robots.txt fetch path (`companyctx/robots.py::is_allowed`) has the
same exposure — a public host can 302 its `/robots.txt` into a private
destination — and applies the same guardrails:
`validate_public_http_url` on the robots URL, a `_NoRedirectHandler`
urllib handler that raises on every 3xx, and a bounded `response.read`.
Any failure here falls open (robots treated as unreachable); the primary
fetch is still SSRF-validated separately.

**Remediation status.** Closed.

**Residual risk — time-of-use DNS rebinding.** An attacker can flip the
hostname's A record between our `getaddrinfo` call and `curl_cffi`'s own
resolution. Fixing this at the client layer requires pinning the resolved
IP into the `Host`-header/TLS pairing on each request, which curl_cffi
does not expose today. Mitigation: operators should run the tool behind a
network egress policy that blocks RFC 1918 and link-local at the network
layer. Tracked as an accepted residual.

**Tests.** `tests/test_security_url.py::test_non_http_scheme_rejected`,
`test_non_public_address_rejected`, `test_metadata_hostname_rejected_without_dns`,
`test_stealth_fetch_rejects_ssrf_before_network`, `test_dns_rebinding_is_caught_on_resolve`.
`tests/test_security_fetch.py::test_redirect_to_private_ip_rejected`.
`tests/test_security_robots.py::test_robots_redirect_refused_without_following`,
`test_robots_unsafe_url_falls_open_without_fetching`.

---

### 2. Path traversal (`--mock` fixture loader)

**Attack.** `--mock` reads `fixtures/<slug>/*.html`. A malicious slug
(`../../../etc/passwd`, absolute paths, dotted paths) or a symlink planted
inside `fixtures/<slug>/` could read files outside the fixture tree.

**Current behaviour.** Three independent guardrails:

1. `_slug_for` derives the slug from `urlparse(site).netloc`, then requires
   it to match `^[a-z0-9][a-z0-9_-]*$`. Dots, slashes, backslashes,
   leading-`.`, uppercase all fail.
2. `_safe_fixture_root` resolves both `fixtures_dir` and
   `fixtures_dir / slug` with `Path.resolve(strict=False)` and verifies
   containment via `Path.relative_to`. A symlink pointing outside the
   fixture tree is refused.
3. `_safe_child` applies the same resolve + `relative_to` check to every
   file read inside the site directory (`homepage.html`, `about.html`,
   `services.html`, `fixture-block.txt`). This catches the
   file-level escape a dir-level check misses: a legitimate
   `fixtures/acme/` that contains `homepage.html -> /etc/passwd`.

**Remediation status.** Closed.

**Residual risk.** None anticipated. The slug is a strict allow-list
regex; the path-boundary check is symlink-safe because `Path.resolve()`
collapses symlinks before the comparison.

**Tests.** `tests/test_security_url.py::test_slug_for_rejects_traversal_and_unsafe`,
`test_safe_fixture_root_rejects_symlink_escape`,
`test_from_fixture_rejects_symlinked_escape`,
`test_from_fixture_rejects_symlinked_file_inside_legit_dir`,
`test_safe_fixture_root_accepts_normal_subdir`.

---

### 3. Resource exhaustion

**Attack.** A target serves a 10 GB body, a decompression bomb (a small
gzipped response that inflates to hundreds of GB), a redirect loop, or a
pathologically nested HTML tree that blows up `trafilatura` / BS4 on
parse. Any of these consumes memory, CPU, or wall-clock time.

**Current behaviour.**

- **Timeout.** `ctx.timeout_s = 10.0s` per request (hard-coded today; a
  future `M4` setting may make it configurable).
- **Redirect cap.** `companyctx/security.py::MAX_REDIRECTS = 5`. The
  provider follows redirects manually and refuses the sixth hop.
- **Body-size cap.** `companyctx/security.py::MAX_RESPONSE_BYTES =
  10 * 1024 * 1024` (10 MiB). Enforced two ways in `_stealth_fetch`:
  - up-front `Content-Length` check — reject before reading;
  - streaming — `iter_content(chunk_size=8192)` accumulates into a buffer
    that refuses the next chunk once the cap is exceeded. This catches
    lying `Content-Length` headers and decompression bombs (since
    `iter_content` yields already-decompressed bytes when
    `Content-Encoding: gzip` is present).
- **robots.txt size cap.** `companyctx/robots.py::MAX_ROBOTS_BYTES =
  512 * 1024` (512 KiB). Enforced by `response.read(MAX_ROBOTS_BYTES+1)`
  plus a post-read length check — a robots.txt that ships more than 512
  KiB cannot inflate memory before the main fetch runs.
- **Parse blow-ups.** Not currently bounded beyond the size cap.
  `trafilatura.extract` and `BeautifulSoup('lxml')` are both external.
  Capping the input at 10 MiB is the proxy bound.

**Remediation status.** Closed for size + redirects; parse-time is an
**accepted residual** — the 10 MiB ceiling keeps the worst-case bounded
in practice, and no real target we care about approaches it.

**Tests.** `tests/test_security_fetch.py::test_content_length_over_cap_rejected`,
`test_streamed_body_over_cap_rejected`, `test_redirect_loop_capped`,
`test_redirect_without_location_header_rejected`, `test_under_cap_succeeds`.
`tests/test_security_robots.py::test_robots_oversize_body_refused`,
`test_robots_under_cap_parses_normally`.

---

### 4. Secrets leakage (`--verbose`, logs, errors)

**Attack.** `--verbose` dumps something that reveals secrets: request
headers (`Authorization`, `Cookie`), environment variables containing API
keys, fixture bodies planted with secrets, or error stack traces that
reveal filesystem layout.

**Current behaviour.** `--verbose` is scope-minimal by inspection of
`companyctx/cli.py::fetch` (lines 142–153). It prints only:

- `companyctx <version> — <site> → status=<envelope.status>`;
- for each provider slug: `<slug>: <status> (<latency_ms>ms)`.

It does **not** print headers, bodies, env vars, or stack traces.
Orchestrator-level exceptions are caught at the boundary
(`companyctx/core.py::run`) and surfaced as
`ProviderRunMetadata.error = "<ExceptionClass>: <str(exc)>"`. Tracebacks
do not reach stdout/stderr by default.

No `COMPANYCTX_DEBUG` env var is wired today. If one is added, the rule
is: it must be opt-in, must not be the default, and must redact
`Authorization`, `Cookie`, and `*-key`/`*-token` headers if it ever logs
requests.

**Remediation status.** Closed (current surface is small). Documented as
a maintenance invariant so any future expansion of `--verbose` gets an
audit pass.

**Residual risk.** A provider author might log a response body that
happens to contain a user secret (e.g., a customer pasted an API key into
their own about-page). The tool can't know what the site contains; the
mitigation is that we don't log response bodies.

**Tests.** Covered implicitly by `tests/test_smoke.py::test_cli_help_runs`
and by visual inspection in review. A regression test that greps
`--verbose` output for header names is deliberately **not** added: the
surface today is three fields; a grep test would ossify the wrong thing.
If `--verbose` grows, add a positive allow-list test at that point.

---

### 5. Supply chain

**Attack.** A direct dependency ships malware (compromised maintainer,
typosquat), an active CVE is left unpatched because our pin is too loose,
or the dependency is abandoned and we have no swap path.

**Current behaviour — `curl_cffi`.** The zero-key fetch path depends on
`curl_cffi`, which wraps a vendored `libcurl-impersonate` native library.
The pick is recorded in
[`decisions/2026-04-20-zero-key-stealth-strategy.md`](../decisions/2026-04-20-zero-key-stealth-strategy.md)
and measured in
[`research/2026-04-21-tls-impersonation-spike.md`](../research/2026-04-21-tls-impersonation-spike.md).

- **Pin.** `curl_cffi~=0.15.0` in `pyproject.toml` — PEP 440 compatibility-
  release pinning, accepts `>=0.15.0, <0.16.0` only. A minor bump that
  changes the bundled libcurl-impersonate requires a deliberate version
  change in this repo.
- **Maintenance signal.** Actively maintained as of the audit date
  (commits within the last 30 days; multi-maintainer repo at
  `lexiforest/curl_cffi`). If that changes we will re-evaluate.
- **Swap path.** `primp` and `rnet` were the runners-up in the
  impersonation spike; both remain viable swaps if `curl_cffi` is
  abandoned or a CVE forces a move. The provider shape already treats the
  HTTP client as an internal implementation detail — swapping requires
  changes only inside
  `companyctx/providers/site_text_trafilatura.py::_stealth_fetch`.

**Other direct dependencies.** `pydantic`, `typer`, `beautifulsoup4`,
`lxml`, `trafilatura`, `requests-cache`, `tenacity`, `platformdirs`,
`pydantic-settings`. All are mainstream Python packages with active
release cadences; pinned `>=` with a lower bound sufficient for the
features we use. CVE monitoring happens through Dependabot (enabled in
`.github/dependabot.yml` — see `ci: CI gates — pip-audit + pyroma +
Dependabot + CodeQL (closes #30) (#47)` for the wiring).

**Remediation status.** Closed for `curl_cffi`; Dependabot + `pip-audit`
cover the rest (see #47).

**Tests.** Supply chain is a process invariant, not a runtime one; CI
gates (`pip-audit`, Dependabot) carry the load. No unit test here.

---

### 6. `robots.txt` bypass

**Attack.** `--ignore-robots` is intended as a CLI-only, operator-owned
escape hatch ("I own this site, I want my own robots.txt ignored").
Bypass paths worth checking: a `COMPANYCTX_IGNORE_ROBOTS=1` environment
variable, a `companyctx.toml` key, or a malformed URL/fixture that
silently flips the flag.

**Current behaviour.**

- `--ignore-robots` is a Typer CLI option
  (`companyctx/cli.py::_IGNORE_ROBOTS_OPT`). The help text explicitly
  reads: *"Bypass robots.txt. Explicit CLI-only; not config-file-
  settable."*
- `companyctx/config.py::Settings` does **not** declare an
  `ignore_robots` field. `pydantic_settings` with `extra="ignore"` means
  a stray `COMPANYCTX_IGNORE_ROBOTS=1` environment variable is silently
  dropped and cannot be read back off the settings object.
- The flag reaches the provider through `FetchContext.ignore_robots`,
  a dataclass field set only by the CLI (default `False`). No other
  code path writes to it.

**Remediation status.** Closed by design (pre-existing structure). Tests
added to lock it in.

**Tests.** `tests/test_security_url.py::test_ignore_robots_not_a_settings_field`,
`test_ignore_robots_env_var_is_ignored`,
`test_ignore_robots_default_is_false`,
`test_no_module_reads_ignore_robots_from_config`.

---

## Non-goals

- **Release-artefact signing (sigstore / cosign).** Deferred to a separate
  issue. When we tag releases, we sign them; that is not this audit.
- **Obfuscation / anti-reverse-engineering of the wheel.** This is OSS.
  No.
- **DDoS protection of user-deployed instances.** Not our layer.

## Change log

- **2026-04-22 — initial audit** (issue #53 / COX-23). SSRF URL validator
  added, fetch path hardened (size + redirect caps, per-hop re-validation),
  fixture path boundary + symlink check added, `curl_cffi` pinned to
  `~=0.15.0`. See PR for COX-23.
- **2026-04-22 — review follow-up.** Three gaps from the review closed in
  the same PR:
  (1) robots.txt no longer follows redirects (they were an SSRF bypass —
  a public host could 302 into a private destination before `_stealth_fetch`
  ran);
  (2) robots.txt response read is capped at `MAX_ROBOTS_BYTES = 512 KiB`
  (an unbounded `response.read()` previously meant a hostile robots could
  inflate memory);
  (3) fixture file reads go through `_safe_child`, catching the
  `fixtures/<slug>/homepage.html -> /etc/passwd` escape the directory-level
  check missed.
