"""URL-style smart-proxy provider — vendor-agnostic Attempt 2.

Reads a proxy URL from ``COMPANYCTX_SMART_PROXY_URL`` (user-embedded creds).
The env-unset case returns ``not_configured`` — the envelope surfaces it as
an actionable ``suggestion`` pointing at the env var. On configured failure
(auth error / upstream block / timeout) returns ``failed`` with a concrete
reason. Never raises.

Covers the 80% case: any residential or datacenter proxy that accepts plain
HTTP-over-CONNECT with the vendor's credentials folded into the URL. For
session-API-style vendors (per-request endpoints, JSON payload shape), a
different provider class will land alongside — this one is intentionally
narrow.

Mock mode reads ``fixtures/<slug>/homepage.html`` (same slug the zero-key
provider uses). When both ``fixture-block.txt`` and ``homepage.html`` are
present the zero-key path still raises (the sentinel wins inside that
provider), but the smart-proxy's mock path reads the homepage file to
simulate a vendor recovery — this is how the waterfall-recovery acceptance
test is wired.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import ClassVar, Literal
from urllib.parse import urlparse

from curl_cffi import requests

from companyctx.providers.base import FetchContext
from companyctx.providers.smart_proxy_base import failed_metadata, not_configured_metadata
from companyctx.robots import is_allowed
from companyctx.schema import ProviderRunMetadata

_VERSION = "0.1.0"
ENV_URL = "COMPANYCTX_SMART_PROXY_URL"
ENV_VERIFY = "COMPANYCTX_SMART_PROXY_VERIFY"
NOT_CONFIGURED_SUGGESTION = (
    "export COMPANYCTX_SMART_PROXY_URL='http://user:pass@host:port' "
    "to wire your residential-proxy vendor"
)
_SAFE_FIXTURE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class Provider:
    """Vendor-agnostic URL-style smart-proxy fetcher.

    Reads creds from ``COMPANYCTX_SMART_PROXY_URL`` and routes ``fetch()``
    calls through that proxy. The user picks their vendor; we ship the
    contract.
    """

    slug: ClassVar[str] = "smart_proxy_http"
    category: ClassVar[Literal["smart_proxy"]] = "smart_proxy"
    cost_hint: ClassVar[Literal["per-call"]] = "per-call"
    version: ClassVar[str] = _VERSION

    def fetch(
        self,
        url: str,
        *,
        ctx: FetchContext,
    ) -> tuple[bytes | None, ProviderRunMetadata]:
        proxy_url = os.environ.get(ENV_URL, "").strip()
        if not proxy_url:
            return None, not_configured_metadata(
                provider_version=self.version,
                missing_env=ENV_URL,
                suggestion=NOT_CONFIGURED_SUGGESTION,
            )

        start = time.monotonic()
        try:
            body = (
                _from_fixture(url, ctx.fixtures_dir)
                if ctx.mock
                else _from_network(url, proxy_url, ctx)
            )
        except _ProxyError as exc:
            return None, failed_metadata(
                provider_version=self.version,
                error=str(exc),
                latency_ms=0 if ctx.mock else _elapsed_ms(start),
            )
        except Exception as exc:  # pragma: no cover — defensive boundary
            return None, failed_metadata(
                provider_version=self.version,
                error=f"unexpected: {exc!r}",
                latency_ms=0 if ctx.mock else _elapsed_ms(start),
            )

        return body, ProviderRunMetadata(
            status="ok",
            latency_ms=0 if ctx.mock else _elapsed_ms(start),
            error=None,
            provider_version=self.version,
            cost_incurred=0,
        )


class _ProxyError(Exception):
    pass


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _from_fixture(url: str, fixtures_dir: str | None) -> bytes:
    if fixtures_dir is None:
        raise _ProxyError("mock mode requires fixtures_dir")
    slug = _slug_for(url)
    homepage = Path(fixtures_dir) / slug / "homepage.html"
    if not homepage.exists():
        raise _ProxyError(f"smart-proxy mock: fixture missing {homepage}")
    return homepage.read_bytes()


def _from_network(url: str, proxy_url: str, ctx: FetchContext) -> bytes:
    target = url if "://" in url else f"https://{url}"
    # Honor robots.txt on the smart-proxy path too. Residential-proxy egress
    # shouldn't launder a robots violation — the user opted into compliance
    # by not passing ``--ignore-robots``. Same policy as the zero-key path.
    if not ctx.ignore_robots and not is_allowed(target, user_agent=ctx.user_agent):
        raise _ProxyError("blocked_by_robots")
    verify_path = os.environ.get(ENV_VERIFY, "").strip()
    try:
        # curl_cffi types ``verify`` as ``bool | None`` but accepts a CA-bundle
        # path at runtime (same shape as ``requests``); the cast keeps the
        # mypy boundary honest without hiding the full signature.
        resp = requests.get(
            target,
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=ctx.timeout_s,
            verify=verify_path if verify_path else True,  # type: ignore[arg-type]
            allow_redirects=True,
        )
    except requests.RequestsError as exc:
        raise _ProxyError(f"proxy network error: {exc.__class__.__name__}") from exc
    status_code = getattr(resp, "status_code", 0)
    if status_code in (401, 403):
        raise _ProxyError(f"proxy auth/block (HTTP {status_code})")
    if status_code >= 400:
        raise _ProxyError(f"proxy upstream HTTP {status_code}")
    content = getattr(resp, "content", None)
    if isinstance(content, (bytes, bytearray)):
        return bytes(content)
    text = getattr(resp, "text", "")
    return text.encode("utf-8") if isinstance(text, str) else b""


def _slug_for(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or parsed.path).lower().rstrip("/")
    if host.startswith("www."):
        host = host[4:]
    slug, _, _ = host.partition(".")
    if not slug or not _SAFE_FIXTURE_SLUG_RE.fullmatch(slug):
        raise _ProxyError(f"invalid fixture slug: {slug or host!r}")
    return slug


__all__ = ["ENV_URL", "ENV_VERIFY", "NOT_CONFIGURED_SUGGESTION", "Provider"]
