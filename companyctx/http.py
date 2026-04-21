"""Shared HTTP foundation.

Milestone 1: scaffolding only. The full session — `requests-cache` for
HTTP-layer caching plus `tenacity` for retry/backoff — is wired in M3 so
provider authors share one configured client.
"""

from __future__ import annotations

DEFAULT_USER_AGENT = "companyctx/0.1 (+https://github.com/dmthepm/companyctx)"
DEFAULT_TIMEOUT_S: float = 10.0


def build_session() -> object:
    """Return a configured requests session. Implemented in M3."""
    raise NotImplementedError


__all__ = ["DEFAULT_TIMEOUT_S", "DEFAULT_USER_AGENT", "build_session"]
