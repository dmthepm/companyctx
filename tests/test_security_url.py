"""Security tests — URL validation and fixture path boundary.

Covers the threats enumerated in ``docs/THREAT-MODEL.md``:

- §1 SSRF       — non-HTTP schemes, loopback, RFC 1918, link-local, cloud
  metadata addresses, IPv6 loopback/link-local.
- §2 path traversal — dotted slugs, absolute slugs, symlinked fixture roots.
- §6 robots.txt — ``--ignore-robots`` cannot be set via env or a ``Settings``
  field.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from companyctx.config import Settings
from companyctx.providers.base import FetchContext
from companyctx.providers.site_text_trafilatura import (
    _BlockedError,
    _from_fixture,
    _MissingFixtureError,
    _safe_fixture_root,
    _slug_for,
    _stealth_fetch,
)
from companyctx.security import (
    UnsafeURLError,
    validate_public_http_url,
)

UA = "companyctx-test/0.1"


# ---------------------------------------------------------------------------
# §1 SSRF — scheme whitelist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/",
        "gopher://example.com/",
        "ldap://example.com/",
        "dict://example.com/",
        "javascript:alert(1)",
        "data:text/html,hi",
        "ws://example.com/",
    ],
)
def test_non_http_scheme_rejected(url: str) -> None:
    with pytest.raises(UnsafeURLError, match="scheme"):
        validate_public_http_url(url)


def test_empty_host_rejected() -> None:
    with pytest.raises(UnsafeURLError):
        validate_public_http_url("http:///etc/passwd")


# ---------------------------------------------------------------------------
# §1 SSRF — IP blocklist after resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://127.0.0.1:5432/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",  # AWS metadata
        "http://10.0.0.1/",
        "http://10.255.255.255/",
        "http://192.168.0.1/",
        "http://192.168.1.100:8080/",
        "http://172.16.0.1/",
        "http://172.31.255.255/",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://[fe80::1]/",
    ],
)
def test_non_public_address_rejected(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        validate_public_http_url(url)


def test_metadata_hostname_rejected_without_dns() -> None:
    # GCP metadata vanity hostnames must be rejected on the host-literal path
    # even if a lab DNS server maps them to a public IP.
    with pytest.raises(UnsafeURLError, match="metadata"):
        validate_public_http_url("http://metadata.google.internal/")


def test_public_host_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pin DNS so the test does not depend on live resolution.
    def fake_getaddrinfo(
        host: str, *args: Any, **kwargs: Any
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("companyctx.security.socket.getaddrinfo", fake_getaddrinfo)
    assert validate_public_http_url("https://example.com/") == "https://example.com/"


def test_dns_rebinding_is_caught_on_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hostname resolves to a private IP → rejected.

    This is the time-of-check defense: a hostname whose A record points at
    127.0.0.1 (common DNS-rebinding primitive) is refused before the fetch.
    Time-of-use rebinding (attacker flips the A record between our check and
    curl_cffi's resolution) is an accepted residual per the threat model.
    """

    def fake_getaddrinfo(
        host: str, *args: Any, **kwargs: Any
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        return [(2, 1, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr("companyctx.security.socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeURLError, match="non-public"):
        validate_public_http_url("http://rebind.example.com/")


def test_stealth_fetch_rejects_ssrf_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """The provider's fetch path must refuse SSRF without issuing a request."""
    called = {"count": 0}

    def fake_get(*args: Any, **kwargs: Any) -> Any:
        called["count"] += 1
        raise AssertionError("network must not be reached for SSRF input")

    monkeypatch.setattr("companyctx.providers.site_text_trafilatura.requests.get", fake_get)
    ctx = FetchContext(user_agent=UA, timeout_s=1.0, ignore_robots=True)
    with pytest.raises(_BlockedError, match="unsafe_url"):
        _stealth_fetch("http://169.254.169.254/latest/meta-data/", ctx)
    assert called["count"] == 0


# ---------------------------------------------------------------------------
# §2 Path traversal — slug regex + path boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "site",
    [
        "../../../etc/passwd",
        "../etc/passwd",
        "/etc/passwd",
        "./acme",
        "acme\\..\\secret",
        "http://../evil/",
        "http:///etc/passwd",  # empty host, path falls into slug
    ],
)
def test_slug_for_rejects_traversal_and_unsafe(site: str) -> None:
    with pytest.raises(_MissingFixtureError):
        _slug_for(site)


def test_slug_for_discards_path_component() -> None:
    """``acme/../secret`` parses with ``netloc='acme'``, so the slug resolves
    cleanly to ``acme``. The path component is discarded before the fixture
    root is assembled — which is why path-traversal protection hinges on
    :func:`_safe_fixture_root`, not on the slug regex alone.
    """
    assert _slug_for("acme/../secret") == "acme"


def test_safe_fixture_root_rejects_symlink_escape(tmp_path: Path) -> None:
    """A symlink inside fixtures_dir that points outside must be refused."""
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.html").write_text("SECRET")
    # Create fixtures/evil -> ../outside
    (fixtures / "evil").symlink_to(outside, target_is_directory=True)

    with pytest.raises(_MissingFixtureError, match="escapes"):
        _safe_fixture_root(str(fixtures), "evil")


def test_safe_fixture_root_accepts_normal_subdir(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    site_dir = fixtures / "acme"
    site_dir.mkdir(parents=True)
    resolved = _safe_fixture_root(str(fixtures), "acme")
    assert resolved == site_dir.resolve()


def test_from_fixture_rejects_symlinked_escape(tmp_path: Path) -> None:
    """End-to-end: ``_from_fixture`` refuses to read through a symlink escape."""
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "homepage.html").write_text("<html><body>secret</body></html>")
    (fixtures / "acme").symlink_to(outside, target_is_directory=True)

    with pytest.raises(_MissingFixtureError):
        _from_fixture("https://acme.com/", str(fixtures))


# ---------------------------------------------------------------------------
# §6 robots.txt bypass — --ignore-robots must stay CLI-only
# ---------------------------------------------------------------------------


def test_ignore_robots_not_a_settings_field() -> None:
    """Settings must not expose ``ignore_robots`` — it is CLI-only by design."""
    assert "ignore_robots" not in Settings.model_fields


def test_ignore_robots_env_var_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even if a user sets ``COMPANYCTX_IGNORE_ROBOTS=1``, Settings does not
    accept the value (``extra="ignore"`` in the model config) and no public
    attribute is exposed."""
    monkeypatch.setenv("COMPANYCTX_IGNORE_ROBOTS", "1")
    settings = Settings()
    assert not hasattr(settings, "ignore_robots")


def test_ignore_robots_default_is_false() -> None:
    """Orchestrator default must be to respect robots.txt."""
    ctx = FetchContext(user_agent=UA, timeout_s=1.0)
    assert ctx.ignore_robots is False


def test_no_module_reads_ignore_robots_from_config() -> None:
    """Grep guard: the phrase ``ignore_robots`` must not appear in a config/env
    load path. Keeping this check as a test so adding such a path trips CI.
    """
    import companyctx.config as cfg_mod

    src = Path(cfg_mod.__file__).read_text(encoding="utf-8")
    # The docstring mentions the word; check it's ONLY in the docstring.
    # Remove the docstring lines and then assert absence.
    lines = [line for line in src.splitlines() if not line.lstrip().startswith("#")]
    non_docstring = "\n".join(lines)
    # Now strip module-level docstring block between first pair of triple-quotes.
    # Crude but sufficient: assert the attribute name isn't assigned.
    assert "ignore_robots:" not in non_docstring
    assert "ignore_robots =" not in non_docstring
