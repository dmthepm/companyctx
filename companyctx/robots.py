"""robots.txt enforcement.

Default behavior: respected. The `--ignore-robots` CLI flag is the only
opt-out path and is not settable via TOML or env (see config.py).

Milestone 1: scaffolding only. Real fetcher + caching wired in M3.
"""

from __future__ import annotations


def is_allowed(url: str, *, user_agent: str) -> bool:
    """Return True if the URL is allowed by the host's robots.txt.

    Implemented in M3. M1 stub raises so callers can't silently ship without
    the real check landing.
    """
    raise NotImplementedError


__all__ = ["is_allowed"]
