"""robots.txt enforcement.

Default behavior: respected. The `--ignore-robots` CLI flag is the only
opt-out path and is not settable via TOML or env (see config.py).
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser


def is_allowed(url: str, *, user_agent: str) -> bool:
    """Return True if the URL is allowed by the host's robots.txt.

    Best-effort by design: a fetch/parsing failure on ``robots.txt`` falls open
    rather than turning transient infrastructure issues into hard fetch blocks.
    """
    robots_url = _robots_url(url)
    if robots_url is None:
        return False

    parser = RobotFileParser()
    try:
        request = Request(robots_url, headers={"User-Agent": user_agent})
        with urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
    except Exception:
        return True

    parser.parse(body.splitlines())
    return parser.can_fetch(user_agent, url)


def _robots_url(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))


__all__ = ["is_allowed"]
