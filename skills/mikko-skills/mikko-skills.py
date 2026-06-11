#!/usr/bin/env python3
"""mikko-skills — list installed mikko-* skills with plain-English barney lines.

Thin CLI over skills_listing (same shared lib as mikko-help, different view).
Stdlib only, Python 3.11+.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

# Locate skills_listing — sibling after install (copy), ../_lib/ in the source repo.
_HERE = Path(__file__).resolve().parent
for _candidate in (_HERE, _HERE.parent / "_lib"):
    if (_candidate / "skills_listing.py").is_file():
        sys.path.insert(0, str(_candidate))
        break
else:
    raise ImportError(
        "skills_listing.py not found next to script or in ../_lib/ "
        "(install-mikko.sh should copy it as a sibling)"
    )

from skills_listing import discover_skills, render_barney_list  # noqa: E402


if __name__ == "__main__":
    # No flags — this view is barney-only — but parse so `--help` works and a
    # stray flag errors instead of being silently ignored.
    argparse.ArgumentParser(
        prog="mikko-skills",
        description="List installed mikko-* skills with plain-English barney lines.",
    ).parse_args()
    print(render_barney_list(discover_skills(Path.cwd(), Path.home())))
