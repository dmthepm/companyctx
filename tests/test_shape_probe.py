"""Regression coverage for the shape-probe harness's SSRF pre-flight (COX-49).

The research harness at ``scripts/run-shape-probe.py`` reuses the same
SSRF guardrails the zero-key provider applies. When ``security.py``
introduced :class:`DNSResolutionError` (COX-49), the harness's wrapper
was updated to catch it before the generic :class:`UnsafeURLError` so
an unresolvable hostname buckets as ``dns_resolve_failure`` in the
probe report instead of ``unsafe_url``. This test pins that parity
directly against the script rather than the in-tree provider, since
the harness runs against the same error strings for its outcome
classification.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run-shape-probe.py"


def _load_shape_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("shape_probe", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shape_probe_emits_dns_resolve_failure_prefix_on_nxdomain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NXDOMAIN pre-flight in the probe harness raises a ``dns_resolve_failure:`` error.

    Keeps the probe's outcome bucketing honest: the ``dns_resolve_failure``
    bucket in ``scripts/run-shape-probe.py`` is gated on the error-string
    prefix, so the harness must emit the distinct prefix (not
    ``unsafe_url:``) when DNS resolution fails.
    """
    module = _load_shape_probe()

    def _fake_getaddrinfo(host: str, *args: Any, **kwargs: Any) -> list[Any]:
        raise OSError("[Errno 8] nodename nor servname provided, or not known")

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("network must not be reached for NXDOMAIN input")

    monkeypatch.setattr("companyctx.security.socket.getaddrinfo", _fake_getaddrinfo)
    monkeypatch.setattr(module.requests, "get", _boom)

    with pytest.raises(module._ProbeFetchError, match=r"^dns_resolve_failure:"):
        module._stealth_fetch_guarded("http://this-does-not-exist-abc123xyz.example/", 1.0)
