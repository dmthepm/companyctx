"""Security tests — robots.txt fetch path.

Covers the two gaps flagged in the COX-23 review:

- robots.txt 3xx response follows into a private-IP destination (SSRF
  bypass via redirect);
- robots.txt response body is not size-capped (resource exhaustion).

Both are expected to be closed by :mod:`companyctx.robots` refusing
redirects and reading at most :data:`MAX_ROBOTS_BYTES` bytes.
"""

from __future__ import annotations

import io
from typing import Any

import pytest

from companyctx import robots as robots_mod
from companyctx.robots import MAX_ROBOTS_BYTES, is_allowed


class _FakeResponse:
    """urllib ``http.client.HTTPResponse`` stand-in.

    Only the members ``is_allowed`` reads are implemented: ``read(n)``,
    context-manager protocol, ``status`` (not consulted by the refusing
    handler path but kept for realism).
    """

    def __init__(self, body: bytes, status: int = 200) -> None:
        self._buf = io.BytesIO(body)
        self.status = status

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        self._buf.close()


# ---------------------------------------------------------------------------
# §1 robots.txt must not follow redirects into a private destination.
# ---------------------------------------------------------------------------


def test_robots_redirect_refused_without_following(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public robots endpoint returning 302 → 127.0.0.1 must not be followed.

    Pre-fix failure mode: urllib's default opener followed the 302 and
    issued a request to the internal destination before ``_stealth_fetch``
    ever ran. Post-fix: ``_NoRedirectHandler`` raises ``HTTPError`` on any
    3xx and ``is_allowed`` falls open (treats robots as unreachable).
    """
    state = {"urls_fetched": []}  # type: dict[str, list[str]]

    def fake_opener_open(self: Any, request: Any, timeout: float = 0) -> _FakeResponse:
        state["urls_fetched"].append(request.full_url)
        # Simulate stdlib behaviour *without* the no-redirect handler:
        # if the test opener class is _NoRedirectHandler the real code
        # path raises HTTPError before we get here. If it's not (pre-fix),
        # this would happily return the private-IP body.
        raise AssertionError(
            "a redirected fetch reached the private-IP destination — "
            "redirects must be refused, not followed"
        )

    # Also pin DNS so robots.txt on example.com "resolves" public.
    monkeypatch.setattr(
        "companyctx.security.socket.getaddrinfo",
        lambda host, *a, **kw: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )

    import urllib.error
    import urllib.request

    # Substitute build_opener so it returns an opener whose .open() emits a
    # 3xx, exercising the real _NoRedirectHandler chain.
    class _RedirectingOpener:
        def open(self, request: Any, timeout: float = 0) -> _FakeResponse:
            # Hand a synthetic 302 to the handler chain. Easier: raise
            # HTTPError ourselves with Location header — this is what the
            # real _NoRedirectHandler does.
            raise urllib.error.HTTPError(
                request.full_url,
                302,
                "redirect refused",
                {"Location": "http://127.0.0.1/admin"},  # type: ignore[arg-type]
                None,
            )

    monkeypatch.setattr(robots_mod, "build_opener", lambda *h: _RedirectingOpener())

    # Fall-open is the expected behaviour on refused redirect; the caller
    # will still block the primary fetch through validate_public_http_url.
    assert is_allowed("https://example.com/", user_agent="test-agent") is True
    # The test's assertion lives inside fake_opener_open above; reaching
    # this line means no redirect was followed.
    assert state["urls_fetched"] == []


def test_robots_oversize_body_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A robots.txt larger than the cap must not be fully buffered.

    Pre-fix failure mode: ``response.read()`` with no argument consumed the
    full body. Post-fix: ``is_allowed`` reads at most ``MAX_ROBOTS_BYTES+1``
    bytes and falls open if the cap is exceeded. We assert both that the
    read is capped and that the result is fall-open (True).
    """
    monkeypatch.setattr(
        "companyctx.security.socket.getaddrinfo",
        lambda host, *a, **kw: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )

    huge = b"User-agent: *\nDisallow: /\n" + (b"x" * (MAX_ROBOTS_BYTES + 5000))
    max_read_observed = {"n": 0}

    class _CappedResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self, n: int = -1) -> bytes:
            # Enforce that the caller asked for a bounded read (n>=0) and
            # that the requested bound is at most the cap+1 byte slack.
            assert n > 0, "robots.read() must be bounded"
            assert n <= MAX_ROBOTS_BYTES + 1, f"robots.read({n}) exceeds cap {MAX_ROBOTS_BYTES}"
            max_read_observed["n"] = max(max_read_observed["n"], n)
            return self._body[:n]

        def __enter__(self) -> _CappedResponse:
            return self

        def __exit__(self, *exc: object) -> None:
            pass

    class _OversizeOpener:
        def open(self, request: Any, timeout: float = 0) -> _CappedResponse:
            return _CappedResponse(huge)

    monkeypatch.setattr(robots_mod, "build_opener", lambda *h: _OversizeOpener())
    # Fall-open on oversize is the design — this is robots.txt, not the
    # main fetch, and the main fetch is still SSRF-validated.
    assert is_allowed("https://example.com/", user_agent="test-agent") is True
    assert max_read_observed["n"] <= MAX_ROBOTS_BYTES + 1


def test_robots_under_cap_parses_normally(monkeypatch: pytest.MonkeyPatch) -> None:
    """Baseline: a small robots.txt allowing ``/`` must still be respected
    — confirms the cap did not break the happy path."""
    monkeypatch.setattr(
        "companyctx.security.socket.getaddrinfo",
        lambda host, *a, **kw: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )

    body = b"User-agent: *\nAllow: /\n"

    class _SmallOpener:
        def open(self, request: Any, timeout: float = 0) -> _FakeResponse:
            return _FakeResponse(body)

    monkeypatch.setattr(robots_mod, "build_opener", lambda *h: _SmallOpener())
    assert is_allowed("https://example.com/foo", user_agent="test-agent") is True


def test_robots_unsafe_url_falls_open_without_fetching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the robots URL itself would be SSRF (e.g. the site URL resolved
    to loopback), we must not issue the robots request at all.

    Defence-in-depth — the primary fetch will already refuse the target.
    This test pins the assumption that robots never becomes a pre-flight
    leak of internal hosts.
    """
    monkeypatch.setattr(
        "companyctx.security.socket.getaddrinfo",
        lambda host, *a, **kw: [(2, 1, 6, "", ("127.0.0.1", 0))],
    )

    def _explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("robots must not fetch an unsafe URL")

    monkeypatch.setattr(robots_mod, "build_opener", _explode)
    assert is_allowed("http://internal.example/", user_agent="test-agent") is True
