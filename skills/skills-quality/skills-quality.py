#!/usr/bin/env python3
"""skills-quality - audit Claude Code skills for token-economy hygiene.

Question: do my skills follow "maximize local deterministic computation,
minimize AI / token usage"? A pure-stdlib pre-pass scans each skill for
smells (long imperative prose with no script, missing frontmatter, etc.)
and only surfaces skills that need LLM review.

Manifest key = (skill_content_hash + quality_ruleset_version_hash). When
the ruleset changes, every skill re-enters "needs review" even if it
didn't change.

Reuses skills_audit_lib (hash + manifest IO) - the change-detection gate
is identical to skills-freshness. Rules live in sibling rules.py and ARE
the ruleset.

Stdlib only. Python 3.11+.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# UTF-8 stdout so the table renders cleanly on Windows consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

# Locate the shared skills_audit_lib. Path.resolve() follows symlinks so
# both install modes work:
#   - install-mikko.sh (copy): lib lives as a sibling of this script.
#   - install.sh (symlink) + source-repo direct run: __file__ resolves into
#     the source tree, where ../_lib/ holds the lib (3rd candidate).
_HERE = Path(__file__).resolve().parent
for _candidate in (_HERE, _HERE.parent / "_lib"):
    if (_candidate / "skills_audit_lib.py").is_file():
        sys.path.insert(0, str(_candidate))
        break
else:
    raise ImportError(
        "skills_audit_lib.py not found next to script or in ../_lib/ "
        "(install-mikko.sh should copy it as a sibling)"
    )

# rules.py must live as a sibling - it IS the ruleset and its hash is the
# manifest-key component. Friendly error if the install missed it.
if not (_HERE / "rules.py").is_file():
    raise ImportError(
        f"rules.py not found next to skills-quality.py at {_HERE} - "
        "the skill install is incomplete."
    )
sys.path.insert(0, str(_HERE))

from skills_audit_lib import (  # noqa: E402
    compute_skill_hash,
    find_skill_dirs,
    load_json_file,
    save_json_file_atomic,
)
import rules  # noqa: E402


MANIFEST_FILENAME = "skills-quality.manifest.json"
SCRIPT_VERSION = 1


# ---------- manifest ----------


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    """Read the quality manifest, validating per-entry shape.

    Schema:
      {
        "version": int,
        "skills": {
          "<name>": {
            "skill_hash": str,
            "ruleset_hash_at_review": str,
            "pre_pass": "clean" | "flagged"
          }
        }
      }

    The per-entry `ruleset_hash_at_review` is the load-bearing key for the
    skip decision. There is no top-level ruleset_hash - it would be dead
    information and could drift from per-entry values on hand-edit.
    """
    default: dict[str, Any] = {"version": SCRIPT_VERSION, "skills": {}}
    data = load_json_file(manifest_path, default)
    if not isinstance(data, dict) or not isinstance(data.get("skills"), dict):
        return default
    skills = {
        k: v
        for k, v in data["skills"].items()
        if (
            isinstance(v, dict)
            and isinstance(v.get("skill_hash"), str)
            and isinstance(v.get("ruleset_hash_at_review"), str)
        )
    }
    return {"version": data.get("version", SCRIPT_VERSION), "skills": skills}


def save_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
    save_json_file_atomic(manifest_path, manifest)


# ---------- audit ----------


def audit_scope(
    scope_name: str, scope_root: Path, ruleset_hash: str
) -> dict[str, Any]:
    """Run the two-stage audit for one scope.

    Stage 1: pre-pass for every skill (cheap, deterministic, no LLM).
    Stage 2: classify each skill as
      - SKIP   : (skill_hash unchanged) AND (ruleset_hash unchanged) AND
                 (last pre-pass was clean) -> never surfaced
      - CLEAN  : (changed OR ruleset changed) AND (pre-pass clean now)  ->
                 surfaced as 'needs LLM verify' (briefly)
      - FLAGGED: pre-pass returns any HIGH finding -> surfaced for deeper review

    Returns the report dict plus a freshly-computed new_manifest for --update.
    """
    manifest_path = scope_root / ".claude" / MANIFEST_FILENAME
    manifest = load_manifest(manifest_path)
    stored_skills = manifest.get("skills", {})

    skill_dirs = find_skill_dirs(scope_root)
    new_skills: dict[str, dict[str, str]] = {}
    findings: list[dict[str, Any]] = []

    for skill_dir in skill_dirs:
        name = skill_dir.name
        skill_hash = compute_skill_hash(skill_dir)
        stored = stored_skills.get(name, {})
        prev_skill_hash = stored.get("skill_hash")
        prev_ruleset_hash = stored.get("ruleset_hash_at_review")
        prev_pre_pass = stored.get("pre_pass", "")

        key_unchanged = (
            prev_skill_hash == skill_hash
            and prev_ruleset_hash == ruleset_hash
        )

        # Cheap pre-pass runs every audit - it's local computation.
        content = rules.build_content(skill_dir)
        if content is None:
            # SKILL.md unreadable - surface as a high-severity issue.
            pre_findings = [
                {
                    "rule_id": "skill_md_unreadable",
                    "severity": "high",
                    "message": "SKILL.md exists but could not be read as UTF-8.",
                }
            ]
        else:
            pre_findings = rules.run_rules(content)

        has_high = any(f["severity"] == "high" for f in pre_findings)
        pre_pass_label = "flagged" if has_high else "clean"

        # Record the new manifest entry regardless of surface decision so a
        # subsequent --update writes a coherent baseline.
        new_skills[name] = {
            "skill_hash": skill_hash,
            "ruleset_hash_at_review": ruleset_hash,
            "pre_pass": pre_pass_label,
        }

        # Skip when key unchanged AND last pre-pass was clean. Under
        # deterministic rules, key_unchanged implies pre_findings is identical
        # to the prior run, so prev_pre_pass==clean implies has_high is False;
        # explicit `not has_high` defends against hand-edited manifests.
        if key_unchanged and prev_pre_pass == "clean" and not has_high:
            continue

        status = "flagged" if has_high else "changed"
        findings.append(
            {
                "name": name,
                "scope": scope_name,
                "status": status,
                "skill_dir": str(skill_dir),
                "pre_findings": pre_findings,
                "needs_llm_review": True,  # by construction, anything surfaced needs review
            }
        )

    # Removed skills (in manifest but no longer on disk)
    on_disk = {d.name for d in skill_dirs}
    for name in stored_skills:
        if name not in on_disk:
            findings.append(
                {
                    "name": name,
                    "scope": scope_name,
                    "status": "removed",
                    "skill_dir": None,
                    "pre_findings": [],
                    "needs_llm_review": False,
                }
            )

    return {
        "scope": scope_name,
        "scope_root": str(scope_root),
        "manifest_path": str(manifest_path),
        "findings": findings,
        "new_manifest": {"version": SCRIPT_VERSION, "skills": new_skills},
    }


# ---------- output ----------


def _severity_rank(f: dict[str, Any]) -> int:
    order = {"high": 0, "medium": 1, "low": 2}
    sevs = [order.get(pf["severity"], 3) for pf in f["pre_findings"]]
    return min(sevs) if sevs else 9


def render_table(reports: list[dict[str, Any]]) -> str:
    rows = [(r["scope"], f) for r in reports for f in r["findings"]]
    if not rows:
        return "All skills pass quality + unchanged - nothing to review."
    name_w = max(32, max(len(f["name"]) for _, f in rows))
    lines = [
        f"{'SCOPE':<8} {'SKILL':<{name_w}} {'STATUS':<10} TOP FINDING",
        "-" * (8 + name_w + 10 + 4 + 40),
    ]
    # Sort by severity then by name for predictable scanning
    rows.sort(key=lambda r: (_severity_rank(r[1]), r[1]["name"]))
    for scope, f in rows:
        if f["status"] == "removed":
            top = "skill directory no longer exists"
        elif f["pre_findings"]:
            sev = f["pre_findings"][0]["severity"].upper()
            msg = f["pre_findings"][0]["message"]
            extra = (
                f" (+{len(f['pre_findings']) - 1} more)"
                if len(f["pre_findings"]) > 1
                else ""
            )
            top = f"[{sev}] {msg}{extra}"
        else:
            top = "pre-pass clean - needs LLM verify (changed since last review)"
        lines.append(f"{scope:<8} {f['name']:<{name_w}} {f['status']:<10} {top}")
    return "\n".join(lines)


def render_details(reports: list[dict[str, Any]]) -> str:
    """High-severity additional findings only; mediums stay in --json output.

    Keeps the human/LLM table view scannable - the table's TOP FINDING column
    already surfaces the lead, and mediums are by definition not urgent.
    """
    out: list[str] = []
    for r in reports:
        for f in r["findings"]:
            highs_after_first = [
                pf for pf in f["pre_findings"][1:] if pf["severity"] == "high"
            ]
            if not highs_after_first:
                continue
            out.append(f"\n[{f['scope']}/{f['name']}] additional HIGH findings:")
            for pf in highs_after_first:
                out.append(f"  [{pf['severity'].upper()}] {pf['rule_id']}: {pf['message']}")
    return "\n".join(out)


# ---------- main ----------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit Claude Code skills for token-economy hygiene "
        "(deterministic pre-pass + LLM review only for flagged/changed skills)."
    )
    parser.add_argument(
        "--scope",
        choices=["project", "global", "both"],
        default="both",
        help="which scope to audit (default: both)",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="project root containing .claude/skills/ (default: cwd)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="rewrite manifests to reflect current state (baseline update)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON instead of the table",
    )
    args = parser.parse_args(argv)

    ruleset_hash = rules.compute_ruleset_hash()

    scopes: list[tuple[str, Path]] = []
    project_root = Path(args.project_root).resolve()
    home = Path.home().resolve()
    if args.scope in ("project", "both"):
        if args.scope == "both" and project_root == home:
            print(
                "INFO: project-root resolves to $HOME; skipping project scope "
                "(global scope covers it)",
                file=sys.stderr,
            )
        else:
            scopes.append(("project", project_root))
    if args.scope in ("global", "both"):
        scopes.append(("global", home))

    reports = [audit_scope(name, root, ruleset_hash) for name, root in scopes]

    if args.json:
        print(json.dumps({"ruleset_hash": ruleset_hash, "reports": reports}, indent=2))
    else:
        print(render_table(reports))
        details = render_details(reports)
        if details:
            print("\nAdditional findings:")
            print(details)

    if args.update:
        for r in reports:
            save_manifest(Path(r["manifest_path"]), r["new_manifest"])
        if not args.json:
            for r in reports:
                print(f"\nmanifest updated: {r['manifest_path']}")
        return 0

    any_findings = any(r["findings"] for r in reports)
    if any_findings and not args.json:
        print(
            "\nReview the table above. After accepting the findings, re-run with --update "
            "to baseline the current state. The script does NOT auto-fix any skill file."
        )

    # Exit 1 if any HIGH finding surfaced - lets CI catch regressions.
    any_high = any(
        pf["severity"] == "high"
        for r in reports
        for f in r["findings"]
        for pf in f["pre_findings"]
    )
    return 1 if any_high else 0


if __name__ == "__main__":
    sys.exit(main())
