"""Security tests — fetch-path resource limits and redirect discipline.

Covers the threats enumerated in ``docs/THREAT-MODEL.md``:

- §3 resource exhaustion — response-size cap (body stream + Content-Length),
  redirect cap.
- §1 SSRF redirect re-validation — a 302 redirect into a private IP must be
  refused before the second hop is issued.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from companyctx.providers.base import FetchContext
from companyctx.providers.site_text_trafilatura import (
    _BlockedError,
    _stealth_fetch,
)
from companyctx.security import MAX_REDIRECTS, MAX_RESPONSE_BYTES

UA = "companyctx-test/0.1"


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin DNS so every host in these tests resolves to a public IP."""

    def fake_getaddrinfo(
        host: str, *args: Any, **kwargs: Any
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("companyctx.security.socket.getaddrinfo", fake_getaddrinfo)


@pytest.fixture
def allow_robots(monkeypatch: pytest.MonkeyPatch) -> None:
    """robots.txt: always allow — these tests exercise fetch-path limits, not
    the robots module."""
    monkeypatch.setattr(
        "companyctx.providers.site_text_trafilatura.is_allowed",
        lambda url, *, user_agent: True,
    )


def _fake_response(
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    chunks: list[bytes] | None = None,
    encoding: str = "utf-8",
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.encoding = encoding
    resp.iter_content.return_value = iter(chunks or [])
    resp.close = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# §3 Response size cap
# ---------------------------------------------------------------------------


def test_content_length_over_cap_rejected(
    monkeypatch: pytest.MonkeyPatch, public_dns: None, allow_robots: None
) -> None:
    huge = str(MAX_RESPONSE_BYTES + 1)

    def fake_get(*args: Any, **kwargs: Any) -> MagicMock:
        return _fake_response(
            status_code=200,
            headers={"content-length": huge},
            chunks=[b"x"],
        )

    monkeypatch.setattr("companyctx.providers.site_text_trafilatura.requests.get", fake_get)
    ctx = FetchContext(user_agent=UA, timeout_s=1.0, ignore_robots=True)
    with pytest.raises(_BlockedError, match="response_too_large"):
        _stealth_fetch("https://example.com/", ctx)


def test_streamed_body_over_cap_rejected(
    monkeypatch: pytest.MonkeyPatch, public_dns: None, allow_robots: None
) -> None:
    """Decompression-bomb analogue: Content-Length lies (or is absent) and the
    body balloons past the cap on iteration."""
    big_chunk = b"x" * (MAX_RESPONSE_BYTES // 2 + 1)

    def fake_get(*args: Any, **kwargs: Any) -> MagicMock:
        # No content-length header → cap only trips on the stream.
        return _fake_response(
            status_code=200,
            headers={},
            chunks=[big_chunk, big_chunk],
        )

    monkeypatch.setattr("companyctx.providers.site_text_trafilatura.requests.get", fake_get)
    ctx = FetchContext(user_agent=UA, timeout_s=1.0, ignore_robots=True)
    with pytest.raises(_BlockedError, match="response_too_large"):
        _stealth_fetch("https://example.com/", ctx)


def test_under_cap_succeeds(
    monkeypatch: pytest.MonkeyPatch, public_dns: None, allow_robots: None
) -> None:
    def fake_get(*args: Any, **kwargs: Any) -> MagicMock:
        return _fake_response(
            status_code=200,
            headers={"content-type": "text/html"},
            chunks=[b"<html>", b"<body>", b"ok", b"</body></html>"],
        )

    monkeypatch.setattr("companyctx.providers.site_text_trafilatura.requests.get", fake_get)
    ctx = FetchContext(user_agent=UA, timeout_s=1.0, ignore_robots=True)
    body = _stealth_fetch("https://example.com/", ctx)
    assert "<body>" in body


# ---------------------------------------------------------------------------
# §3 Redirect cap
# ---------------------------------------------------------------------------


def test_redirect_loop_capped(
    monkeypatch: pytest.MonkeyPatch, public_dns: None, allow_robots: None
) -> None:
    """A redirect chain longer than MAX_REDIRECTS must raise, not loop forever."""
    hops = {"n": 0}

    def fake_get(*args: Any, **kwargs: Any) -> MagicMock:
        hops["n"] += 1
        return _fake_response(
            status_code=302,
            headers={"location": "https://example.com/next"},
        )

    monkeypatch.setattr("companyctx.providers.site_text_trafilatura.requests.get", fake_get)
    ctx = FetchContext(user_agent=UA, timeout_s=1.0, ignore_robots=True)
    with pytest.raises(_BlockedError, match="redirect limit"):
        _stealth_fetch("https://example.com/", ctx)
    # Initial fetch + MAX_REDIRECTS follow-ups, then the (MAX_REDIRECTS+1)-th
    # redirect response is the one that trips the cap.
    assert hops["n"] == MAX_REDIRECTS + 1


def test_redirect_without_location_header_rejected(
    monkeypatch: pytest.MonkeyPatch, public_dns: None, allow_robots: None
) -> None:
    def fake_get(*args: Any, **kwargs: Any) -> MagicMock:
        return _fake_response(status_code=302, headers={})

    monkeypatch.setattr("companyctx.providers.site_text_trafilatura.requests.get", fake_get)
    ctx = FetchContext(user_agent=UA, timeout_s=1.0, ignore_robots=True)
    with pytest.raises(_BlockedError, match="no Location"):
        _stealth_fetch("https://example.com/", ctx)


# ---------------------------------------------------------------------------
# §1 SSRF redirect re-validation
# ---------------------------------------------------------------------------


def test_redirect_to_private_ip_rejected(
    monkeypatch: pytest.MonkeyPatch, allow_robots: None
) -> None:
    """First hop resolves public; 302 points at 127.0.0.1 which the second
    pre-flight must refuse. Emulates the classic "redirect to metadata" SSRF
    primitive."""

    # DNS returns a public IP for example.com, loopback for 127.0.0.1 (it's
    # already a literal).
    def fake_getaddrinfo(
        host: str, *args: Any, **kwargs: Any
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        if host == "127.0.0.1":
            return [(2, 1, 6, "", ("127.0.0.1", 0))]
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("companyctx.security.socket.getaddrinfo", fake_getaddrinfo)

    state = {"n": 0}

    def fake_get(*args: Any, **kwargs: Any) -> MagicMock:
        state["n"] += 1
        if state["n"] == 1:
            return _fake_response(
                status_code=302,
                headers={"location": "http://127.0.0.1/admin"},
            )
        raise AssertionError("redirect destination must not be fetched")

    monkeypatch.setattr("companyctx.providers.site_text_trafilatura.requests.get", fake_get)
    ctx = FetchContext(user_agent=UA, timeout_s=1.0, ignore_robots=True)
    with pytest.raises(_BlockedError, match="unsafe_url"):
        _stealth_fetch("https://example.com/", ctx)
    assert state["n"] == 1
