"""robots.txt enforcement.

Default behavior: respected. The ``--ignore-robots`` CLI flag is the only
opt-out path and is not settable via TOML or env (see config.py).

Security notes — this module issues an HTTP request to a user-supplied
origin, so it carries the same SSRF / resource-exhaustion exposure as the
main fetch path and applies the same guardrails:

- the robots URL is validated through :func:`companyctx.security.validate_public_http_url`;
- redirects are **not** followed — a 3xx response causes ``is_allowed`` to
  fall open (treat robots as unreachable) rather than follow into a
  potentially private destination;
- the body read is capped at :data:`MAX_ROBOTS_BYTES`.
"""

from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from companyctx.security import UnsafeURLError, validate_public_http_url

# A robots.txt that won't fit in 512 KiB is almost certainly hostile. The
# parser only inspects a few lines per user-agent anyway, so reading past
# this cap only burns memory.
MAX_ROBOTS_BYTES: int = 512 * 1024


class _NoRedirectHandler(HTTPRedirectHandler):
    """urllib redirect handler that refuses every 3xx.

    The stdlib default silently follows redirects, which means a public
    host could 302 its ``/robots.txt`` into ``http://169.254.169.254/`` or
    any other internal target. We refuse instead and let the caller fall
    open (treat robots as unreachable), matching the pre-existing
    fail-open design for transient robots failures.
    """

    def http_error_301(  # type: ignore[no-untyped-def]
        self, req, fp, code, msg, headers
    ):
        raise HTTPError(req.full_url, code, "redirect refused", headers, fp)

    http_error_302 = http_error_301
    http_error_303 = http_error_301
    http_error_307 = http_error_301
    http_error_308 = http_error_301


def is_allowed(url: str, *, user_agent: str) -> bool:
    """Return True if the URL is allowed by the host's robots.txt.

    Best-effort by design: a fetch/parsing failure on ``robots.txt`` falls
    open rather than turning transient infrastructure issues into hard
    fetch blocks. An unsafe robots URL (non-public IP, non-HTTP scheme)
    also falls open — the main fetch path will block the actual request
    through its own :func:`validate_public_http_url` call, so there is no
    benefit to emitting a robots request at a refused destination.
    """
    robots_url = _robots_url(url)
    if robots_url is None:
        return False

    try:
        validate_public_http_url(robots_url)
    except UnsafeURLError:
        return True

    parser = RobotFileParser()
    try:
        opener = build_opener(_NoRedirectHandler)
        request = Request(robots_url, headers={"User-Agent": user_agent})
        with opener.open(request, timeout=10) as response:
            # ``response.read(n)`` caps the in-memory buffer. Read one byte
            # past the cap so we can detect and reject oversize bodies
            # without buffering an attacker-controlled response in full.
            raw = response.read(MAX_ROBOTS_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError):
        return True

    if len(raw) > MAX_ROBOTS_BYTES:
        return True

    body = raw.decode("utf-8", errors="replace")
    parser.parse(body.splitlines())
    return parser.can_fetch(user_agent, url)


def _robots_url(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))


__all__ = ["MAX_ROBOTS_BYTES", "is_allowed"]
