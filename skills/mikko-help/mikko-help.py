#!/usr/bin/env python3
"""mikko-help — list installed mikko-* skills (table view; --barney; --detect).

Thin CLI over skills_listing. All the work (glob, frontmatter parse, dedupe,
format, codebase fingerprint) is deterministic and lives in the shared lib —
this script just wires argv to it and prints. Stdlib only, Python 3.11+.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

# Locate skills_listing — sibling after install-mikko.sh (copy), ../_lib/ when
# run from the source repo. Mirrors skills-quality.py's preamble.
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

from skills_listing import (  # noqa: E402
    discover_skills,
    fingerprint,
    recommend_audits,
    render_detect,
    render_table,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mikko-help", description="List installed mikko-* skills.")
    ap.add_argument("--barney", action="store_true", help="show plain-English barney lines")
    ap.add_argument("--detect", action="store_true", help="also recommend audits for the cwd")
    args = ap.parse_args(argv)

    cwd, home = Path.cwd(), Path.home()
    print(render_table(discover_skills(cwd, home), barney=args.barney))
    if args.detect:
        shape = fingerprint(cwd)
        print(render_detect(shape, recommend_audits(shape)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
