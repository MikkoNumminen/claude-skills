#!/usr/bin/env python3
"""mikko-skills-freshness - audit Claude Code skills for staleness.

Pure-stdlib change detection. Computes a sha256 over every file in each skill
directory and compares against a stored manifest. Only changed/new/removed
skills are surfaced - unchanged skills are never reasoned about.

Scopes:
  project: ./.claude/skills/   manifest: ./.claude/skills-freshness.manifest.json
  global:  ~/.claude/skills/   manifest: ~/.claude/skills-freshness.manifest.json

Per-skill freshness criteria are optional. If present, declared in SKILL.md
under '# Freshness check' (heading levels 1-3 accepted) as a fenced TOML block.
See SKILL.md for the format.

Requires Python 3.11+ (tomllib).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

# Force UTF-8 stdout/stderr so the table renders cleanly on Windows consoles.
# Python 3.7+ supports reconfigure on the default text streams.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

try:
    import tomllib
except ImportError:
    print("ERROR: requires Python 3.11+ (tomllib)", file=sys.stderr)
    sys.exit(2)


SKILL_FILE = "SKILL.md"
MANIFEST_FILENAME = "skills-freshness.manifest.json"
SCRIPT_VERSION = 1
MAX_FILE_BYTES = 5 * 1024 * 1024  # skip files >5 MB to keep hashing cheap
MAX_PATTERN_SCAN_BYTES = 1_000_000  # only scan first 1 MB of any file for regex


# ---------- change detection ----------


def find_skill_dirs(scope_root: Path) -> list[Path]:
    """Return sorted skill directories (each containing SKILL.md)."""
    skills_dir = scope_root / ".claude" / "skills"
    if not skills_dir.is_dir():
        return []
    out: list[Path] = []
    for d in sorted(skills_dir.iterdir(), key=lambda p: p.name):
        if d.is_dir() and (d / SKILL_FILE).is_file():
            out.append(d)
    return out


def compute_skill_hash(skill_dir: Path) -> str:
    """sha256 of (sorted relative posix path + NUL + file content + NUL) per entry.

    Uses os.walk(followlinks=False) - Path.rglob follows symlinked directories on
    Python 3.11/3.12, which would cycle on symlink loops and double-count any
    symlink-to-sibling-dir layout.

    Hashing (not mtime) - git checkouts reset mtimes and would produce false
    'changed' results.

    Oversized files (>5 MB) get a content fingerprint (first 64 KB + last 64 KB
    + size), not bare size - a same-size content edit must still change the hash.
    """
    h = hashlib.sha256()
    entries: list[tuple[str, str, Path]] = []  # (rel_posix_path, kind, abs_path)
    try:
        for root, dirs, files in os.walk(skill_dir, followlinks=False):
            root_p = Path(root)
            # Record symlinked dirs as link entries; prune so os.walk doesn't descend.
            keep: list[str] = []
            for d in dirs:
                full = root_p / d
                if full.is_symlink():
                    rel = full.relative_to(skill_dir).as_posix()
                    entries.append((rel, "symlink", full))
                else:
                    keep.append(d)
            dirs[:] = keep
            for fname in files:
                full = root_p / fname
                rel = full.relative_to(skill_dir).as_posix()
                if full.is_symlink():
                    entries.append((rel, "symlink", full))
                else:
                    entries.append((rel, "file", full))
    except OSError as e:
        # Hash the walk error so the audit doesn't crash but does flip 'changed'
        # when permissions/structure first break.
        h.update(b"<walk-error:")
        h.update(str(e.errno or 0).encode("ascii"))
        h.update(b">\x00")

    entries.sort(key=lambda x: x[0])
    for rel, kind, p in entries:
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        try:
            if kind == "symlink":
                # Hash the link target string so retargets register, without following.
                target = str(p.readlink())
                h.update(b"SYMLINK:")
                h.update(target.encode("utf-8"))
            else:
                size = p.stat().st_size
                if size > MAX_FILE_BYTES:
                    # Cheap fingerprint: first + last + size. Catches in-place
                    # content edits without paying full-hash cost on bundled assets.
                    h.update(b"OVERSIZED:")
                    h.update(str(size).encode("ascii"))
                    h.update(b":")
                    with p.open("rb") as fh:
                        h.update(fh.read(65536))
                        if size > 2 * 65536:
                            fh.seek(-65536, os.SEEK_END)
                            h.update(fh.read(65536))
                else:
                    with p.open("rb") as fh:
                        for chunk in iter(lambda: fh.read(65536), b""):
                            h.update(chunk)
        except OSError as e:
            # errno-only - the rendered message can drift between runs (locale,
            # kernel version) and produce spurious 'changed' on stable failures.
            h.update(b"<unreadable:")
            h.update(str(e.errno or 0).encode("ascii"))
            h.update(b">")
        h.update(b"\x00")
    return h.hexdigest()


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        return {"version": SCRIPT_VERSION, "skills": {}}
    try:
        raw = manifest_path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        # Soft-handle so --update can overwrite a corrupt manifest with a fresh
        # baseline instead of forcing the user to delete the file by hand.
        print(
            f"WARN: corrupt manifest {manifest_path}: {e} - treating as empty",
            file=sys.stderr,
        )
        return {"version": SCRIPT_VERSION, "skills": {}}
    if not isinstance(data, dict) or not isinstance(data.get("skills"), dict):
        return {"version": SCRIPT_VERSION, "skills": {}}
    # Filter per-entry garbage so audit_scope's .get('hash') never trips on a non-dict.
    skills = {
        k: v
        for k, v in data["skills"].items()
        if isinstance(v, dict) and isinstance(v.get("hash"), str)
    }
    return {"version": data.get("version", SCRIPT_VERSION), "skills": skills}


def save_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replace to avoid leaving a half-written file if interrupted.
    tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    tmp.replace(manifest_path)


# ---------- freshness-criteria parsing ----------


FRESHNESS_HEADING_RE = re.compile(
    r"^#{1,3}\s+Freshness check\s*$.*?^```toml\s*$(.*?)^```\s*$",
    re.MULTILINE | re.DOTALL,
)


def parse_freshness_block(skill_md: Path) -> dict[str, Any] | None:
    """Return the parsed TOML block, or None if the section is absent.

    On parse failure returns {'_parse_error': '...'} so the caller surfaces it.
    """
    try:
        # errors='replace' so a SKILL.md with a stray non-UTF-8 byte doesn't
        # raise UnicodeDecodeError (subclass of ValueError, not caught below)
        # and abort the whole scope's audit.
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = FRESHNESS_HEADING_RE.search(text)
    if not m:
        return None
    try:
        return tomllib.loads(m.group(1))
    except tomllib.TOMLDecodeError as e:
        return {"_parse_error": str(e)}


# ---------- check runners ----------


CHECK_PASS = "pass"
CHECK_FAIL = "fail"
CHECK_ERROR = "error"

VALID_ROOTS = {"skill_dir", "scope_root", "home", "absolute"}

# Content-reading checks are restricted to in-scope roots so a malicious skill
# cannot turn the audit into a regex-oracle to probe arbitrary files (e.g.
# ~/.aws/credentials). path_exists and command_exists are not restricted -
# they don't read content.
CONTENT_READING_KINDS = {"file_contains", "file_lacks", "no_broken_md_links"}
SAFE_ROOTS_FOR_CONTENT = {"skill_dir", "scope_root"}


def _resolve(
    path_str: str, root: str, scope_root: Path, skill_dir: Path
) -> Path:
    """Resolve a check path against the requested root, refusing escape."""
    if root not in VALID_ROOTS:
        raise ValueError(f"unknown root: {root!r}")
    if root == "absolute":
        p = Path(path_str).expanduser()
        if not p.is_absolute():
            raise ValueError(f"root=absolute but path is relative: {path_str!r}")
        return p.resolve(strict=False)
    base = {"skill_dir": skill_dir, "scope_root": scope_root, "home": Path.home()}[root]
    candidate = Path(path_str)
    if candidate.is_absolute():
        raise ValueError(
            f"absolute path {path_str!r} requires root='absolute' (got root={root!r})"
        )
    resolved = (base / candidate).resolve(strict=False)
    base_resolved = base.resolve(strict=False)
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        raise ValueError(
            f"path {path_str!r} escapes root={root!r} ({base_resolved}) - refusing"
        )
    return resolved


def _safe_compile(pattern: str) -> re.Pattern[str]:
    """Compile a user-supplied regex with multiline by default."""
    return re.compile(pattern, re.MULTILINE)


def run_check(
    check: dict[str, Any],
    scope_root: Path,
    skill_dir: Path,
    scope_name: str,
) -> dict[str, Any]:
    """Run one check. Returns {kind, status, message}."""
    kind = check.get("kind")
    default_root = "scope_root" if scope_name == "project" else "skill_dir"
    root = check.get("root", default_root)

    # Security: content-reading checks cannot read outside skill_dir / scope_root.
    if kind in CONTENT_READING_KINDS and root not in SAFE_ROOTS_FOR_CONTENT:
        return {
            "kind": kind,
            "status": CHECK_ERROR,
            "message": (
                f"root={root!r} not allowed for {kind} - content-reading checks "
                f"are restricted to skill_dir or scope_root"
            ),
        }

    try:
        if kind == "path_exists":
            target = _resolve(check["path"], root, scope_root, skill_dir)
            ok = target.exists()
            return {
                "kind": kind,
                "status": CHECK_PASS if ok else CHECK_FAIL,
                "message": f"{check['path']}" + ("" if ok else " (missing)"),
            }

        if kind == "file_contains":
            target = _resolve(check["path"], root, scope_root, skill_dir)
            if not target.is_file():
                return {
                    "kind": kind,
                    "status": CHECK_FAIL,
                    "message": f"missing file: {check['path']}",
                }
            text = target.read_text(encoding="utf-8", errors="replace")[:MAX_PATTERN_SCAN_BYTES]
            try:
                pat = _safe_compile(check["pattern"])
            except re.error as e:
                return {"kind": kind, "status": CHECK_ERROR, "message": f"bad regex: {e}"}
            ok = pat.search(text) is not None
            return {
                "kind": kind,
                "status": CHECK_PASS if ok else CHECK_FAIL,
                "message": (
                    f"{check['path']} matches /{check['pattern']}/"
                    if ok
                    else f"{check['path']} missing /{check['pattern']}/"
                ),
            }

        if kind == "file_lacks":
            target = _resolve(check["path"], root, scope_root, skill_dir)
            if not target.is_file():
                return {
                    "kind": kind,
                    "status": CHECK_PASS,
                    "message": f"{check['path']} absent (pattern trivially absent)",
                }
            text = target.read_text(encoding="utf-8", errors="replace")[:MAX_PATTERN_SCAN_BYTES]
            try:
                pat = _safe_compile(check["pattern"])
            except re.error as e:
                return {"kind": kind, "status": CHECK_ERROR, "message": f"bad regex: {e}"}
            found = pat.search(text) is not None
            return {
                "kind": kind,
                "status": CHECK_FAIL if found else CHECK_PASS,
                "message": (
                    f"{check['path']} still matches /{check['pattern']}/"
                    if found
                    else f"{check['path']} clean of /{check['pattern']}/"
                ),
            }

        if kind == "no_broken_md_links":
            md_path = check.get("path", SKILL_FILE)
            # default root for md_links is skill_dir (markdown lives with the skill)
            md_root = check.get("root", "skill_dir")
            target = _resolve(md_path, md_root, scope_root, skill_dir)
            if not target.is_file():
                return {
                    "kind": kind,
                    "status": CHECK_FAIL,
                    "message": f"missing file: {md_path}",
                }
            text = target.read_text(encoding="utf-8", errors="replace")
            # Strip fenced code blocks and inline code spans so example link syntax
            # in documentation doesn't trigger false positives.
            text_for_links = re.sub(
                r"^```.*?^```\s*$", "", text, flags=re.MULTILINE | re.DOTALL
            )
            text_for_links = re.sub(r"`[^`\n]*`", "", text_for_links)
            broken: list[str] = []
            # Containment anchor: links must stay within scope_root.
            # Refuses probes like [x](../../../../etc/shadow) that would otherwise
            # do a filesystem existence check on arbitrary paths.
            containment_root = scope_root.resolve()
            link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
            for label, link in link_re.findall(text_for_links):
                if re.match(r"^[a-z][a-z0-9+.-]*://", link, re.I):
                    continue
                if link.startswith(("#", "mailto:", "tel:")):
                    continue
                link_path = link.split("#", 1)[0]
                if not link_path:
                    continue
                candidate = (target.parent / link_path).resolve(strict=False)
                try:
                    candidate.relative_to(containment_root)
                except ValueError:
                    broken.append(f"[{label}]({link}) (escapes scope)")
                    continue
                if not candidate.exists():
                    broken.append(f"[{label}]({link})")
            return {
                "kind": kind,
                "status": CHECK_PASS if not broken else CHECK_FAIL,
                "message": (
                    f"{target.name}: all md links resolve"
                    if not broken
                    else f"{target.name}: broken - {'; '.join(broken[:5])}"
                    + (" ..." if len(broken) > 5 else "")
                ),
            }

        if kind == "command_exists":
            cmd = check["command"]
            found = shutil.which(cmd) is not None
            return {
                "kind": kind,
                "status": CHECK_PASS if found else CHECK_FAIL,
                "message": f"{cmd}" + (" on PATH" if found else " (not on PATH)"),
            }

        return {
            "kind": kind or "<missing>",
            "status": CHECK_ERROR,
            "message": f"unknown check kind: {kind!r}",
        }

    except KeyError as e:
        return {
            "kind": kind or "<unknown>",
            "status": CHECK_ERROR,
            "message": f"missing required field: {e}",
        }
    except (ValueError, OSError) as e:
        return {
            "kind": kind or "<unknown>",
            "status": CHECK_ERROR,
            "message": str(e),
        }


# ---------- audit ----------


def audit_scope(scope_name: str, scope_root: Path) -> dict[str, Any]:
    manifest_path = scope_root / ".claude" / MANIFEST_FILENAME
    manifest = load_manifest(manifest_path)
    stored_skills = manifest.get("skills", {})

    skill_dirs = find_skill_dirs(scope_root)
    new_manifest_skills: dict[str, dict[str, str]] = {}
    findings: list[dict[str, Any]] = []

    for skill_dir in skill_dirs:
        name = skill_dir.name
        current_hash = compute_skill_hash(skill_dir)
        stored_hash = stored_skills.get(name, {}).get("hash")
        new_manifest_skills[name] = {"hash": current_hash}

        if current_hash == stored_hash:
            continue  # unchanged - never reasoned about

        status = "new" if stored_hash is None else "changed"

        criteria = parse_freshness_block(skill_dir / SKILL_FILE)
        if criteria is None:
            check_results: list[dict[str, Any]] = []
            has_criteria = False
            parse_error: str | None = None
        elif "_parse_error" in criteria:
            check_results = []
            has_criteria = True
            parse_error = criteria["_parse_error"]
        else:
            checks_raw = criteria.get("check", [])
            if not isinstance(checks_raw, list):
                check_results = []
                has_criteria = True
                parse_error = "'check' is not an array - use [[check]] table-array syntax"
            else:
                check_results = [
                    run_check(c if isinstance(c, dict) else {}, scope_root, skill_dir, scope_name)
                    for c in checks_raw
                ]
                has_criteria = True
                parse_error = None

        findings.append(
            {
                "name": name,
                "scope": scope_name,
                "status": status,
                "skill_dir": str(skill_dir),
                "has_criteria": has_criteria,
                "parse_error": parse_error,
                "checks": check_results,
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
                    "has_criteria": False,
                    "parse_error": None,
                    "checks": [],
                }
            )

    return {
        "scope": scope_name,
        "scope_root": str(scope_root),
        "manifest_path": str(manifest_path),
        "findings": findings,
        "new_manifest": {"version": SCRIPT_VERSION, "skills": new_manifest_skills},
    }


# ---------- output ----------


def summarize_checks(checks: list[dict[str, Any]]) -> str:
    if not checks:
        return "no declared checks"
    counts = {"pass": 0, "fail": 0, "error": 0}
    for c in checks:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    parts = []
    if counts["pass"]:
        parts.append(f"{counts['pass']} pass")
    if counts["fail"]:
        parts.append(f"{counts['fail']} FAIL")
    if counts["error"]:
        parts.append(f"{counts['error']} ERROR")
    return ", ".join(parts)


def render_table(reports: list[dict[str, Any]]) -> str:
    rows = [(r["scope"], f) for r in reports for f in r["findings"]]
    if not rows:
        return "All skills up to date - nothing to review."
    name_w = max(32, max(len(f["name"]) for _, f in rows))
    lines = []
    lines.append(f"{'SCOPE':<8} {'SKILL':<{name_w}} {'STATUS':<8} CHECKS / ISSUE")
    lines.append("-" * (8 + name_w + 8 + 4 + 40))
    for scope, f in rows:
        if f["parse_error"]:
            issue = f"TOML parse error: {f['parse_error']}"
        elif f["status"] == "removed":
            issue = "skill directory no longer exists"
        elif not f["has_criteria"]:
            issue = "no declared criteria - needs LLM review"
        else:
            issue = summarize_checks(f["checks"])
        lines.append(f"{scope:<8} {f['name']:<{name_w}} {f['status']:<8} {issue}")
    return "\n".join(lines)


def render_details(reports: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for r in reports:
        for f in r["findings"]:
            if not f["checks"]:
                continue
            failures = [c for c in f["checks"] if c["status"] != CHECK_PASS]
            if not failures:
                continue
            out.append(f"\n[{f['scope']}/{f['name']}]")
            for c in failures:
                out.append(f"  {c['status'].upper()} {c['kind']}: {c['message']}")
    return "\n".join(out)


# ---------- main ----------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit Claude Code skills for staleness (sha256-based change detection)."
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

    scopes: list[tuple[str, Path]] = []
    project_root = Path(args.project_root).resolve()
    home = Path.home().resolve()
    if args.scope in ("project", "both"):
        # If project_root == $HOME, the project scope is the global scope and would
        # write the same manifest twice. Skip the redundant pass and tell the user.
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

    reports = [audit_scope(name, root) for name, root in scopes]

    if args.json:
        print(json.dumps({"reports": reports}, indent=2))
    else:
        print(render_table(reports))
        details = render_details(reports)
        if details:
            print("\nFailures / errors:")
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
            "\nReview the table above. After accepting the changes, re-run with --update "
            "to baseline the current state."
        )

    any_problem = any(
        c["status"] in (CHECK_FAIL, CHECK_ERROR)
        for r in reports
        for f in r["findings"]
        for c in f["checks"]
    )
    return 1 if any_problem else 0


if __name__ == "__main__":
    sys.exit(main())
