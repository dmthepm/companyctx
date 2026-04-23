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
    """Raised when a URL fails the public-HTTP guardrail.

    Carries a ``category`` attribute so the classifier can distinguish
    DNS-resolution failures (not an SSRF attempt; the user typed a bad
    host) from genuine SSRF concerns (private IP, metadata host,
    loopback). Provider wrappers embed the category in the error string
    as ``unsafe_url:<category>: <detail>``. See ``core._classify_error_code``
    and COX-49 / #86.
    """

    # Category tokens kept in a closed vocabulary so the classifier's
    # substring match is stable and greppable.
    CATEGORY_DNS = "dns_resolve_failure"
    CATEGORY_PRIVATE_IP = "private_ip"
    CATEGORY_METADATA = "metadata_host"
    CATEGORY_SCHEME = "unsupported_scheme"
    CATEGORY_EMPTY_HOST = "empty_host"
    CATEGORY_PARSE = "parse_error"

    def __init__(self, message: str, *, category: str = "other") -> None:
        super().__init__(message)
        self.category = category


def validate_public_http_url(url: str) -> str:
    """Reject URLs that point at non-public or non-HTTP destinations.

    Returns the URL unchanged on success. Raises :class:`UnsafeURLError` if
    any of the following holds:

    - scheme is not ``http`` or ``https`` (``category="unsupported_scheme"``);
    - hostname is empty (``category="empty_host"``);
    - hostname is a known cloud-metadata vanity hostname (``category="metadata_host"``);
    - DNS lookup returns no addresses or raises ``OSError``
      (``category="dns_resolve_failure"``);
    - DNS resolves the hostname to an IP that is loopback, link-local,
      private (RFC 1918), multicast, reserved, or otherwise non-global
      (``category="private_ip"``).

    The DNS resolution happens here once; the caller should re-invoke this
    on every redirect hop. This does not defend against active DNS rebinding
    (attacker flips the A record between our resolution and curl_cffi's
    resolution), which is documented as a residual risk in ``THREAT-MODEL``.
    """
    split = urlsplit(url)
    if split.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(
            f"unsupported scheme: {split.scheme or '<empty>'!s}",
            category=UnsafeURLError.CATEGORY_SCHEME,
        )
    host = split.hostname
    if not host:
        raise UnsafeURLError("URL has no host", category=UnsafeURLError.CATEGORY_EMPTY_HOST)
    lowered = host.lower()
    if lowered in _METADATA_HOSTS:
        raise UnsafeURLError(
            f"metadata host not allowed: {lowered}",
            category=UnsafeURLError.CATEGORY_METADATA,
        )

    for ip_text in _resolve_all(host):
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError as exc:
            raise UnsafeURLError(
                f"could not parse resolved IP {ip_text!r}",
                category=UnsafeURLError.CATEGORY_PARSE,
            ) from exc
        if not _is_public(ip):
            raise UnsafeURLError(
                f"host {lowered} resolves to non-public address {ip_text}",
                category=UnsafeURLError.CATEGORY_PRIVATE_IP,
            )
    return url


def _resolve_all(host: str) -> list[str]:
    """Return every address the host resolves to (IPv4 + IPv6).

    A literal IP in the host position — e.g. ``http://127.0.0.1/`` — also
    goes through :func:`socket.getaddrinfo`, which returns the literal back;
    that keeps the blocklist check uniform for hostnames and IPs both.

    DNS failures carry ``category="dns_resolve_failure"`` so the downstream
    classifier routes NXDOMAIN / no-such-host to ``no_provider_succeeded``
    rather than ``ssrf_rejected`` (COX-49 / #86). An unresolvable domain is
    not an SSRF attempt — it's a dead or mistyped host.
    """
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeURLError(
            f"DNS resolution failed for {host}: {exc}",
            category=UnsafeURLError.CATEGORY_DNS,
        ) from exc
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
        raise UnsafeURLError(
            f"no addresses for {host}",
            category=UnsafeURLError.CATEGORY_DNS,
        )
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
