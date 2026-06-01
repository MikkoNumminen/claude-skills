"""Shared change-detection + manifest IO for skills-audit-family tools.

Single source of truth for hashing skill directories and reading/writing JSON
manifests. Used by `skills-freshness` (staleness audit) and `skills-quality`
(token-economy audit). Both skills share the gate — hash the skill, compare to
manifest, only surface changed entries — but layer their own per-skill checks
on top.

Layout:
  - Source repo: skills/_lib/skills_audit_lib.py
  - Installed:   ~/.claude/skills/<prefix><name>/skills_audit_lib.py
    (copied as a sibling by install-mikko.sh on demand — see that script)

Public surface:
  - SKILL_FILE, MAX_FILE_BYTES (constants)
  - find_skill_dirs(scope_root) -> list[Path]
  - compute_skill_hash(skill_dir) -> str
  - load_json_file(path, default) -> Any
  - save_json_file_atomic(path, data) -> None

Stdlib-only. Python 3.11+.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


SKILL_FILE = "SKILL.md"
# Files above this size get a content fingerprint (first 64K + last 64K + size)
# instead of a full hash, so a skill that ships a bundled asset doesn't pay the
# full-hash cost on every audit. The fingerprint still detects in-place edits.
MAX_FILE_BYTES = 5 * 1024 * 1024


def find_skill_dirs(scope_root: Path) -> list[Path]:
    """Return sorted skill directories under <scope_root>/.claude/skills/.

    A skill directory is any subdir of `.claude/skills/` that contains a
    `SKILL.md` file. Underscore-prefixed dirs (e.g. `_lib/`) are naturally
    excluded because they don't carry SKILL.md.
    """
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

    Oversized files (>MAX_FILE_BYTES) get a content fingerprint (first 64 KB +
    last 64 KB + size), not bare size - a same-size content edit must still
    change the hash.

    Symlinks are recorded by their target string (not followed) so retargets
    register but symlink-to-/etc can't read /etc.
    """
    h = hashlib.sha256()
    entries: list[tuple[str, str, Path]] = []  # (rel_posix_path, kind, abs_path)
    try:
        for root, dirs, files in os.walk(skill_dir, followlinks=False):
            root_p = Path(root)
            keep: list[str] = []
            for d in dirs:
                # __pycache__ holds compiled bytecode regenerated whenever a
                # companion script runs (and whose headers shift after a fresh
                # install resets source mtimes). Hashing it would mark every
                # Python-bearing skill "changed" on the next audit — it is build
                # output, not skill content, so prune it from the walk.
                if d == "__pycache__":
                    continue
                full = root_p / d
                if full.is_symlink():
                    rel = full.relative_to(skill_dir).as_posix()
                    entries.append((rel, "symlink", full))
                else:
                    keep.append(d)
            dirs[:] = keep
            for fname in files:
                # Same reason as __pycache__ above: compiled bytecode is not
                # source-of-truth and churns independently of the skill.
                if fname.endswith((".pyc", ".pyo")):
                    continue
                full = root_p / fname
                rel = full.relative_to(skill_dir).as_posix()
                if full.is_symlink():
                    entries.append((rel, "symlink", full))
                else:
                    entries.append((rel, "file", full))
    except OSError as e:
        h.update(b"<walk-error:")
        h.update(str(e.errno or 0).encode("ascii"))
        h.update(b">\x00")

    entries.sort(key=lambda x: x[0])
    for rel, kind, p in entries:
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        try:
            if kind == "symlink":
                target = str(p.readlink())
                h.update(b"SYMLINK:")
                h.update(target.encode("utf-8"))
            else:
                size = p.stat().st_size
                if size > MAX_FILE_BYTES:
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
            # errno-only; rendered errno message can drift between runs/locales
            # and produce spurious 'changed' on stable failures.
            h.update(b"<unreadable:")
            h.update(str(e.errno or 0).encode("ascii"))
            h.update(b">")
        h.update(b"\x00")
    return h.hexdigest()


def load_json_file(path: Path, default: Any) -> Any:
    """Soft-handling JSON read.

    If the file doesn't exist, is corrupt, or unreadable, returns `default` and
    prints a WARN to stderr. Callers layer their own schema validation on top
    of the returned value.
    """
    if not path.is_file():
        return default
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"WARN: corrupt JSON {path}: {e} - treating as empty",
            file=sys.stderr,
        )
        return default


def save_json_file_atomic(path: Path, data: Any) -> None:
    """Atomic JSON write.

    Writes to <path>.tmp first, then renames. Sort keys + indent=2 for stable
    diffs. Uses byte write to pin LF line endings regardless of platform —
    Windows Python's text-mode write would translate \\n to \\r\\n, which would
    flip hashes if the manifest itself were ever fed back into compute_skill_hash.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    tmp.write_bytes(body)
    tmp.replace(path)
