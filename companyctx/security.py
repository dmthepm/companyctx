"""Security primitives for the user-URL fetch surface.

This module is the single place where we enforce the three guardrails that
keep ``companyctx fetch <url>`` from becoming an SSRF / resource-exhaustion
vector:

- :func:`validate_public_http_url` — scheme whitelist + post-DNS IP-range
  rejection (loopback, link-local, private, cloud metadata).
- :data:`MAX_REDIRECTS` — cap on redirect chains (applied by callers that
  follow redirects manually after re-validating each hop).
- :data:`MAX_RESPONSE_BYTES` — cap on streamed response bodies.

See ``docs/THREAT-MODEL.md`` for the full threat catalogue and rationale.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

MAX_REDIRECTS: int = 5
MAX_RESPONSE_BYTES: int = 10 * 1024 * 1024  # 10 MiB — covers every site we care about.
ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

# AWS/GCP/Azure/Alibaba/DO metadata endpoint host. Every major cloud responds
# on 169.254.169.254 which is already caught by the link-local /16, but we
# keep the literal here so the denial surface is obvious when grepped.
_METADATA_HOSTS: frozenset[str] = frozenset(
    {
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.goog",
    }
)


class UnsafeURLError(ValueError):
    """Raised when a URL fails the public-HTTP guardrail."""


def validate_public_http_url(url: str) -> str:
    """Reject URLs that point at non-public or non-HTTP destinations.

    Returns the URL unchanged on success. Raises :class:`UnsafeURLError` if
    any of the following holds:

    - scheme is not ``http`` or ``https``;
    - hostname is empty;
    - hostname is a known cloud-metadata vanity hostname;
    - DNS resolves the hostname to an IP that is loopback, link-local,
      private (RFC 1918), multicast, reserved, or otherwise non-global.

    The DNS resolution happens here once; the caller should re-invoke this
    on every redirect hop. This does not defend against active DNS rebinding
    (attacker flips the A record between our resolution and curl_cffi's
    resolution), which is documented as a residual risk in ``THREAT-MODEL``.
    """
    split = urlsplit(url)
    if split.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"unsupported scheme: {split.scheme or '<empty>'!s}")
    host = split.hostname
    if not host:
        raise UnsafeURLError("URL has no host")
    lowered = host.lower()
    if lowered in _METADATA_HOSTS:
        raise UnsafeURLError(f"metadata host not allowed: {lowered}")

    for ip_text in _resolve_all(host):
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError as exc:
            raise UnsafeURLError(f"could not parse resolved IP {ip_text!r}") from exc
        if not _is_public(ip):
            raise UnsafeURLError(f"host {lowered} resolves to non-public address {ip_text}")
    return url


def _resolve_all(host: str) -> list[str]:
    """Return every address the host resolves to (IPv4 + IPv6).

    A literal IP in the host position — e.g. ``http://127.0.0.1/`` — also
    goes through :func:`socket.getaddrinfo`, which returns the literal back;
    that keeps the blocklist check uniform for hostnames and IPs both.
    """
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeURLError(f"DNS resolution failed for {host}: {exc}") from exc
    seen: set[str] = set()
    addrs: list[str] = []
    for info in infos:
        sockaddr = info[4]
        ip = sockaddr[0]
        if not isinstance(ip, str):
            # Defensive: getaddrinfo's sockaddr tuple is typed as Tuple[Any, ...]
            # by stdlib. IPv4 / IPv6 always yield a string in position 0; fall
            # back to ``str()`` for any exotic address family that slips through.
            ip = str(ip)
        if ip not in seen:
            seen.add(ip)
            addrs.append(ip)
    if not addrs:
        raise UnsafeURLError(f"no addresses for {host}")
    return addrs


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True only for addresses we'll let the client contact.

    ``ipaddress.is_global`` collapses the full set of RFC 1918, link-local,
    loopback, multicast, reserved, and unspecified ranges into one predicate.
    IPv6 link-local (``fe80::/10``) and loopback (``::1``) are both covered.
    """
    return bool(ip.is_global)


__all__ = [
    "ALLOWED_SCHEMES",
    "MAX_REDIRECTS",
    "MAX_RESPONSE_BYTES",
    "UnsafeURLError",
    "validate_public_http_url",
]
