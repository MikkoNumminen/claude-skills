"""Shared discovery + rendering for the mikko-* skill *listing* skills.

Used by:
  - mikko-help   : table view, plus --barney and --detect.
  - mikko-skills : barney-style vertical list.

Both skills do the same mechanical work — glob the installed skill dirs,
parse each SKILL.md's frontmatter, dedupe, sort, format — which is pure
deterministic computation. Keeping it here (and running it as a script)
instead of as LLM prose is the whole point: the listing costs ~one Bash
call instead of ~8-11K tokens of glob+read+format per invocation.

Layout (mirrors skills_audit_lib):
  - Source repo: skills/_lib/skills_listing.py
  - Installed:   ~/.claude/skills/<prefix><name>/skills_listing.py
    (copied as a sibling by install-mikko.sh on demand — it greps each
     skill's scripts for `import skills_listing` and copies the lib in.)

Stdlib only. Python 3.11+.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

PREFIX = "mikko-"
SKILL_FILE = "SKILL.md"
NAME_COL_CAP = 24
DESC_CAP = 120


@dataclass
class Skill:
    name: str
    description: str
    barney: str | None
    scope: str  # "user" or "project"


# ---------- discovery + frontmatter ----------


def parse_frontmatter(text: str) -> dict[str, str]:
    """Extract simple top-level `key: value` pairs from a SKILL.md frontmatter.

    Deliberately tiny: the listing only needs name/description/barney, all of
    which are single-line scalars. Returns {} if the file has no `---` block.
    Multi-line YAML values are not supported (the listing fields never use them).
    """
    if not text.startswith("---"):
        return {}
    # Body after the opening fence, up to the closing fence.
    rest = text[3:]
    end = rest.find("\n---")
    if end == -1:
        return {}
    block = rest[:end]
    out: dict[str, str] = {}
    for line in block.splitlines():
        # Only treat unindented `key: value` lines as fields — indented lines
        # belong to a previous key's block scalar, which we don't parse.
        if not line or line[0] in " \t#":
            continue
        if ": " not in line and not line.endswith(":"):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in ("name", "description", "barney"):
            out[key] = value.strip()
    return out


def _read_skill(skill_md: Path, scope: str) -> Skill | None:
    try:
        fm = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    name = fm.get("name") or skill_md.parent.name
    return Skill(
        name=name,
        description=fm.get("description", "(no description)"),
        barney=fm.get("barney"),
        scope=scope,
    )


def discover_skills(cwd: Path, home: Path) -> list[Skill]:
    """Find installed mikko-* skills, user-wide and project-local.

    Project-local wins on a name clash (matches Claude Code's own resolution
    order) and is tagged so the override is visible. Sorted by name.
    """
    found: dict[str, Skill] = {}
    # User-wide first, then project — project overwrites so it wins the dedupe.
    for root, scope in ((home / ".claude" / "skills", "user"),
                        (cwd / ".claude" / "skills", "project")):
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir(), key=lambda p: p.name):
            if not d.name.startswith(PREFIX):
                continue
            md = d / SKILL_FILE
            if not md.is_file():
                continue
            skill = _read_skill(md, scope)
            if skill is not None:
                found[skill.name] = skill
    return sorted(found.values(), key=lambda s: s.name)


# ---------- rendering ----------


def _truncate(text: str, cap: int) -> str:
    """First sentence if it's present and shorter than cap, else a hard cap + ellipsis."""
    for sep in (" — ", ". "):
        if sep in text:
            head = text.split(sep, 1)[0]
            if len(head) <= cap:
                return head
    if len(text) <= cap:
        return text
    return text[: cap - 1].rstrip() + "…"


def _label(skill: Skill) -> str:
    return f"{skill.name} (project)" if skill.scope == "project" else skill.name


def render_table(skills: list[Skill], barney: bool = False) -> str:
    """Two-column name + (description|barney) table, one line per skill."""
    if not skills:
        return _empty_message()
    width = min(max(len(_label(s)) for s in skills), NAME_COL_CAP)
    title = "your installed mikko-* skills" + (" (barney style)" if barney else "")
    lines = [f"{title}:", ""]
    for s in skills:
        if barney:
            col = s.barney or (_truncate(s.description, DESC_CAP) + " (no barney)")
        else:
            col = _truncate(s.description, DESC_CAP)
        name = _label(s)
        if len(name) > NAME_COL_CAP:
            name = name[: NAME_COL_CAP - 1] + "…"
        lines.append(f"  {name.ljust(width)}  {col}")
    lines += ["", "tip: `/mikko<Tab>` shows names only. For the cross-repo "
              "registry with token math, run `/skill-registry`."]
    return "\n".join(lines)


def render_barney_list(skills: list[Skill]) -> str:
    """Vertical name-then-barney layout used by mikko-skills."""
    if not skills:
        return _empty_message()
    lines = ["your mikko-* skills:", ""]
    for s in skills:
        lines.append(f"  {_label(s)}")
        line = s.barney or (_truncate(s.description, DESC_CAP) + " (no barney yet)")
        lines.append(f"    {line}")
        lines.append("")
    lines.append("tip: `/mikko<Tab>` shows names only. For technical detail, "
                 "open the skill's SKILL.md.")
    return "\n".join(lines)


def _empty_message() -> str:
    return ("no mikko-* skills installed yet.\n"
            "run ./install-mikko.sh from a claude-skills clone to add them.")


# ---------- --detect: codebase fingerprint + audit recommendation ----------

_AUTH = {"jsonwebtoken", "passport", "next-auth", "iron-session", "lucia",
         "oauth4webapi", "clerk", "auth0"}
_DB = {"pg", "mongoose", "sqlite3", "drizzle-orm", "prisma", "kysely", "typeorm"}
_NET = {"express", "fastify", "hono", "koa", "nestjs", "trpc", "apollo-server"}
_CRYPTO = {"bcrypt", "argon2", "crypto-js", "node-forge"}


def fingerprint(cwd: Path) -> dict[str, object]:
    """Read up to ~5 root config files to fingerprint the codebase shape.

    Does NOT walk the source tree — that's each audit skill's own job. Returns
    a shape dict consumed by recommend_audits().
    """
    shape: dict[str, object] = {
        "languages": [], "framework": None, "react": False,
        "security_sensitive": False, "security_hits": [],
    }
    deps: dict[str, str] = {}
    pkg = cwd / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        except (json.JSONDecodeError, OSError):
            deps = {}
    dep_names = {d.lower() for d in deps}

    if deps:
        shape["languages"].append("JavaScript")
    if (cwd / "tsconfig.json").is_file():
        shape["languages"].append("TypeScript")
    if any(d in dep_names for d in ("react", "react-dom", "react-native")):
        shape["react"] = True
        shape["languages"].append("React Native" if "react-native" in dep_names else "React")
    for marker, lang in (("pyproject.toml", "Python"), ("requirements.txt", "Python"),
                         ("setup.py", "Python"), ("Cargo.toml", "Rust"), ("go.mod", "Go")):
        if (cwd / marker).is_file() and lang not in shape["languages"]:
            shape["languages"].append(lang)
    for cfg, fw in (("astro.config.mjs", "Astro"), ("next.config.js", "Next.js"),
                    ("next.config.mjs", "Next.js"), ("next.config.ts", "Next.js"),
                    ("vite.config.js", "Vite"), ("vite.config.ts", "Vite")):
        if (cwd / cfg).is_file():
            shape["framework"] = fw
            break

    hits = sorted(d for d in dep_names
                  if d in _DB or d in _NET or d in _CRYPTO
                  or any(d == a or d.startswith(a + "-") for a in _AUTH))
    if hits:
        shape["security_sensitive"] = True
        shape["security_hits"] = hits
    return shape


def recommend_audits(shape: dict[str, object]) -> list[tuple[str, str]]:
    """Map a fingerprint to an ordered (audit, rationale) list (the decision matrix)."""
    recs: list[tuple[str, str]] = []
    if shape.get("react"):
        rn = "React Native" in shape.get("languages", [])
        recs.append(("react-anti-patterns-audit" + (" --force" if rn else ""),
                     "targets the React-specific layer"))
        recs.append(("ai-codegen-smell-audit", "universal LLM-codegen patterns"))
        recs.append(("audit", "universal robustness audit"))
    else:
        recs.append(("audit", "universal robustness audit, always useful"))
        recs.append(("ai-codegen-smell-audit", "language-agnostic LLM-codegen patterns"))
    if shape.get("security_sensitive"):
        recs.append(("security-audit",
                     "security-sensitive deps: " + ", ".join(shape["security_hits"][:4])))
    return recs


def render_detect(shape: dict[str, object], recs: list[tuple[str, str]]) -> str:
    langs = ", ".join(shape.get("languages") or ["unknown"])
    lines = ["", "detected codebase shape:", f"  • language: {langs}"]
    if shape.get("framework"):
        lines.append(f"  • framework: {shape['framework']}")
    sec = ("yes — " + ", ".join(shape["security_hits"][:4])) if shape.get("security_sensitive") else "low"
    lines.append(f"  • security surface: {sec}")
    lines += ["", "suggested audits, in order:"]
    for audit, why in recs:
        lines.append(f"  /mikko-{audit:<32} → {why}")
    return "\n".join(lines)
