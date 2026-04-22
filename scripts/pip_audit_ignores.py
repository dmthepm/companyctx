"""Emit pip-audit --ignore-vuln flags from .pip-audit.toml.

Read by .github/workflows/ci.yml. Run locally with the same invocation
the CI step uses:

    pip-audit $(python scripts/pip_audit_ignores.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found, no-redef]

CONFIG = Path(__file__).resolve().parent.parent / ".pip-audit.toml"


def main() -> int:
    if not CONFIG.exists():
        return 0
    data = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    entries = data.get("ignore", [])
    for entry in entries:
        advisory_id = entry.get("id")
        reason = entry.get("reason", "").strip()
        if not advisory_id or not reason:
            print(
                f"ERROR: .pip-audit.toml entry missing id or reason: {entry!r}",
                file=sys.stderr,
            )
            return 2
        print("--ignore-vuln", advisory_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
