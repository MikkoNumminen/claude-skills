"""Quality ruleset for skills-quality.

Edit this file to evolve the ruleset. skills-quality.py hashes THIS FILE's
bytes and folds the result into each manifest entry's key, so a change here
re-enters every skill into "needs review" on the next audit. That includes
changing thresholds, adding rules, removing rules, or rewording suggestions.

Comment-only edits also bump the hash — accept the small cost of a wide
re-review, or move comments outside this file if you need to avoid it.

Stdlib only. Python 3.11+.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


# ---------- thresholds ----------

# SKILL.md longer than this many lines triggers the "very long" rule.
# Above this, the skill is probably trying to do too many things; consider
# splitting into multiple skills or moving prose into linked docs.
VERY_LONG_LINES = 300

# This many imperative-loop patterns + NO companion script = HIGH.
# A skill that says "for each X, do Y" five times with no script is asking
# the LLM to be the loop — a script would do this for ~0 LLM tokens.
LOOP_PROSE_HIGH_THRESHOLD = 5

# This many imperative-loop patterns + NO companion script = MEDIUM.
LOOP_PROSE_MEDIUM_THRESHOLD = 2

# This many code blocks in SKILL.md suggests inline executable instructions
# that may belong in a script or a separate file the script reads.
CODE_BLOCK_HIGH_THRESHOLD = 20


# ---------- pattern catalogs ----------

# Patterns suggesting "iterate over a known set mechanically" - the kind of
# work a deterministic script does well. NOT every match is a real smell -
# the LLM review judges. The count is a recall-biased signal: a few false
# positives are cheap (LLM dismisses); a missed smell is the failure case.
LOOP_PROSE_PATTERNS = [
    re.compile(r"\bfor each\b", re.IGNORECASE),
    re.compile(r"\bfor every\b", re.IGNORECASE),
    re.compile(r"\bfor all (?:of )?(?:the|every|each)\b", re.IGNORECASE),
    re.compile(r"\biterate\b", re.IGNORECASE),
    re.compile(r"\bgo through\b", re.IGNORECASE),
    re.compile(r"\bstep through\b", re.IGNORECASE),
    re.compile(r"\bwalk (?:through|over|every)\b", re.IGNORECASE),
    re.compile(r"\bloop (?:through|over)\b", re.IGNORECASE),
    re.compile(r"\brepeat (?:for|until)\b", re.IGNORECASE),
    re.compile(r"\b(?:process|handle|review|check|examine|verify) each\b", re.IGNORECASE),
    re.compile(r"\bone by one\b", re.IGNORECASE),
    re.compile(r"\bin turn\b", re.IGNORECASE),
]

# Filename extensions that count as a "companion script" for the skill.
SCRIPT_EXTENSIONS = {".py", ".mjs", ".js", ".ts", ".sh", ".rb", ".go", ".rs"}

# Frontmatter is parsed as YAML-ish key:value pairs separated by --- fences.
# Stdlib has no YAML parser; we extract only the fields we need. Value capture
# requires at least one space/tab after the colon and disallows newlines, so
# multi-line YAML values don't bleed across keys (a known regex pitfall).
FRONTMATTER_FENCE_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FRONTMATTER_FIELD_RE = re.compile(r"^([a-zA-Z0-9_-]+):[ \t]+(\S.*?)\s*$", re.MULTILINE)

# Counts triple-backtick and tilde code fences. Even number = balanced;
# we report half. CommonMark allows either fence style.
CODE_FENCE_RE = re.compile(r"^(?:```|~~~)", re.MULTILINE)


# Cost-trap patterns (added 2026-05-31 after the local-computation A/B study
# in D:/tmp/skills-optim-study/ — 3 of 6 cells went negative because the
# AFTER arm followed procedural language more conscientiously than the
# improvised BEFORE arm. These rules catch the three mechanisms surfaced
# there: read-granularity regression, post-script review depth, and
# parallel-batch staging).

# "read each/all/every X" or "read the flagged/listed X" — capable models
# read with no limit param and pull large files in full. The guard pattern
# below accepts an explicit limit / first-N-lines / frontmatter-only nearby.
UNLIMITED_READ_PATTERNS = [
    re.compile(r"\bread\s+(?:each|all|every)\s+\w+", re.IGNORECASE),
    re.compile(r"\bread\s+the\s+(?:flagged|listed|matching|relevant|cited)\s+\w+", re.IGNORECASE),
]
LIMIT_GUARD_RE = re.compile(
    r"\blimit\s*=\s*\d+|\bfirst\s+\d+\s+(?:lines?|chars?|sections?)|"
    r"\bfrontmatter[\s\-]?(?:only|alone)|\bonly\s+the\s+(?:frontmatter|first|header)|"
    r"\bno\s+deep\s+read|\bskim\b|\b10[\s\-]?second\s+skim\b",
    re.IGNORECASE,
)

# "verify/check/trace/investigate/chase each X" with no cap on how deep
# to go. Models will spelunk thoroughly when not capped — skills-freshness/opus
# AFTER arm spent 4 extra Bash calls tracing path refs into the source repo.
UNCAPPED_FOLLOWUP_PATTERNS = [
    re.compile(r"\b(?:verify|check|trace|investigate|chase|inspect|examine)\s+(?:each|every|all)\s+\w+", re.IGNORECASE),
    re.compile(r"\b(?:verify|check)\s+(?:all\s+)?(?:referenced|cited|listed)\s+(?:paths?|files?|links?)", re.IGNORECASE),
]
CAP_GUARD_RE = re.compile(
    r"\b(?:max(?:imum)?|cap(?:ped)?|stop\s+after|at\s+most|no\s+more\s+than|"
    r"up\s+to)\s+\d+|\bone\s+(?:ls|grep|read|check)\s+per\b|\bdon[''']t\s+(?:spelunk|chase|trace)\b",
    re.IGNORECASE,
)

# "in parallel" without an explicit single-batch constraint. Models may stage
# parallel reads into multiple batches, creating extra cache checkpoints.
PARALLEL_RE = re.compile(r"\bin\s+parallel\b", re.IGNORECASE)
BATCH_GUARD_RE = re.compile(
    r"\bsingle\s+batch\b|\bone\s+batch\b|\bdon[''']t\s+stage\b|"
    r"\bnot\s+in\s+(?:multiple|two|several)\s+batches?\b|\ball\s+at\s+once\b",
    re.IGNORECASE,
)


# ---------- per-skill content snapshot ----------


@dataclass(frozen=True)
class SkillContent:
    """Pre-computed cheap metrics, built once per skill so rules don't re-scan."""

    skill_dir: Path
    skill_md_text: str
    skill_md_lines: int
    skill_md_chars: int
    frontmatter: dict[str, str]  # empty dict if absent
    has_companion_script: bool
    loop_prose_count: int
    code_block_count: int


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = FRONTMATTER_FENCE_RE.search(text)
    if not m:
        return {}
    body = m.group(1)
    fields = {}
    for fm in FRONTMATTER_FIELD_RE.finditer(body):
        key, value = fm.group(1), fm.group(2).strip()
        if value:
            fields[key] = value
    return fields


def _strip_code_fences(text: str) -> str:
    """Remove fenced code blocks (backtick OR tilde) so prose-pattern counts
    aren't polluted by code examples that incidentally contain words like
    'for each'. Backreference ensures matched fence types."""
    return re.sub(r"^(```|~~~).*?^\1\s*$", "", text, flags=re.MULTILINE | re.DOTALL)


def build_content(skill_dir: Path) -> SkillContent | None:
    """Cheap, deterministic snapshot. Returns None if SKILL.md is unreadable."""
    skill_md = skill_dir / "SKILL.md"
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    prose = _strip_code_fences(text)
    loop_count = sum(len(p.findall(prose)) for p in LOOP_PROSE_PATTERNS)
    code_fences = len(CODE_FENCE_RE.findall(text))
    # os.walk(followlinks=False) so a symlink-to-/usr can't false-positive a
    # companion script. Mirror of the lib's compute_skill_hash defense.
    # Once any script is found we short-circuit — the boolean is all we need —
    # so deeper subdirs may go un-walked. Acceptable: the symlink guard only
    # needs to defend against the first symlinked subdir's contents leaking
    # through, and that's gated above before any descent.
    has_script = False
    for root, dirs, files in os.walk(skill_dir, followlinks=False):
        root_p = Path(root)
        dirs[:] = [d for d in dirs if not (root_p / d).is_symlink()]
        for fname in files:
            full = root_p / fname
            if not full.is_symlink() and full.suffix in SCRIPT_EXTENSIONS:
                has_script = True
                break
        if has_script:
            break

    return SkillContent(
        skill_dir=skill_dir,
        skill_md_text=text,
        skill_md_lines=text.count("\n") + 1,
        skill_md_chars=len(text),
        frontmatter=_parse_frontmatter(text),
        has_companion_script=has_script,
        loop_prose_count=loop_count,
        code_block_count=code_fences // 2,  # fences come in pairs
    )


# ---------- rule definitions ----------
# Each rule returns None if the skill passes, or (severity, suggestion) if not.
# severity is one of: "high", "medium", "low".


Finding = tuple[str, str]  # (severity, suggestion)
Rule = Callable[[SkillContent], Finding | None]


def rule_missing_frontmatter(c: SkillContent) -> Finding | None:
    if not c.frontmatter:
        return ("high", "SKILL.md has no `---` frontmatter block; add `name:` and `description:`.")
    missing = [k for k in ("name", "description") if k not in c.frontmatter]
    if missing:
        return (
            "high",
            f"Frontmatter missing required field(s): {', '.join(missing)}.",
        )
    return None


def rule_long_imperative_no_script(c: SkillContent) -> Finding | None:
    if c.has_companion_script:
        return None
    if c.loop_prose_count >= LOOP_PROSE_HIGH_THRESHOLD:
        return (
            "high",
            f"{c.loop_prose_count} loop-style prose patterns with no companion script. "
            "Likely asking the LLM to be the loop - consider a Python helper that runs "
            "the iteration deterministically and reports results.",
        )
    return None


def rule_imperative_prose_no_script(c: SkillContent) -> Finding | None:
    if c.has_companion_script:
        return None
    if (
        LOOP_PROSE_MEDIUM_THRESHOLD
        <= c.loop_prose_count
        < LOOP_PROSE_HIGH_THRESHOLD
    ):
        return (
            "medium",
            f"{c.loop_prose_count} loop-style prose patterns with no companion script. "
            "Review whether the iteration is genuinely judgment-driven or could be scripted.",
        )
    return None


def rule_very_long_skill(c: SkillContent) -> Finding | None:
    if c.skill_md_lines > VERY_LONG_LINES:
        return (
            "medium",
            f"SKILL.md is {c.skill_md_lines} lines (>{VERY_LONG_LINES}). "
            "Long skills load on every invocation; consider splitting or moving "
            "reference material to linked docs.",
        )
    return None


def rule_excessive_code_blocks(c: SkillContent) -> Finding | None:
    if c.code_block_count > CODE_BLOCK_HIGH_THRESHOLD:
        return (
            "medium",
            f"SKILL.md has {c.code_block_count} code blocks (>{CODE_BLOCK_HIGH_THRESHOLD}). "
            "If many are templates/data, they may belong in a separate file the script reads "
            "instead of inline in the prompt.",
        )
    return None


def _matches_without_nearby_guard(
    text: str, signal_re: re.Pattern[str], guard_re: re.Pattern[str], window: int = 300
) -> int:
    """Count matches of signal_re that DON'T have guard_re within `window`
    chars after the match. The window is one-sided forward so guidance
    that lands AFTER the imperative (typical: 'Read each SKILL.md with
    limit=80') counts as a guard; guidance buried elsewhere in the file
    does not."""
    count = 0
    for m in signal_re.finditer(text):
        end = min(len(text), m.end() + window)
        if not guard_re.search(text[m.start():end]):
            count += 1
    return count


def rule_unlimited_read_in_procedure(c: SkillContent) -> Finding | None:
    text = _strip_code_fences(c.skill_md_text)
    total = sum(
        _matches_without_nearby_guard(text, p, LIMIT_GUARD_RE)
        for p in UNLIMITED_READ_PATTERNS
    )
    if total >= 1:
        return (
            "medium",
            f"{total} 'read each/all/every X' instruction(s) with no nearby limit guidance "
            "(limit=N, first N lines, frontmatter-only, 10-second skim). Capable models "
            "follow the procedure literally and pull large files in full - the local-computation "
            "A/B study saw skills-freshness/haiku AFTER read 233,876 chars vs BEFORE's 116,731 "
            "from exactly this pattern.",
        )
    return None


def rule_uncapped_followup(c: SkillContent) -> Finding | None:
    text = _strip_code_fences(c.skill_md_text)
    total = sum(
        _matches_without_nearby_guard(text, p, CAP_GUARD_RE)
        for p in UNCAPPED_FOLLOWUP_PATTERNS
    )
    if total >= 1:
        return (
            "medium",
            f"{total} 'verify/check/trace each X' instruction(s) with no cap (max N, "
            "stop after N, at most N, one ls per finding). Capable models will spelunk - "
            "skills-freshness/opus AFTER spent 4 extra Bash calls chasing path refs into a "
            "source repo, costing +28K tokens (-21% sign flip).",
        )
    return None


def rule_batch_invitation(c: SkillContent) -> Finding | None:
    text = _strip_code_fences(c.skill_md_text)
    total = _matches_without_nearby_guard(text, PARALLEL_RE, BATCH_GUARD_RE)
    if total >= 1:
        return (
            "medium",
            f"{total} 'in parallel' instruction(s) with no 'single batch' constraint. Models "
            "may stage reads into multiple batches, creating extra cache checkpoints - "
            "skills-quality/sonnet AFTER staged 6+8 reads and paid +27K cache_creation tokens "
            "(-12% sign flip).",
        )
    return None


# Ordered: high-severity gates first so the LLM-review trigger evaluation
# short-circuits cleanly. Cost-trap rules at the end (all medium, picked up
# only after the unambiguous structural rules have fired).
RULES: list[tuple[str, Rule]] = [
    ("missing_frontmatter", rule_missing_frontmatter),
    ("long_imperative_no_script", rule_long_imperative_no_script),
    ("imperative_prose_no_script", rule_imperative_prose_no_script),
    ("very_long_skill", rule_very_long_skill),
    ("excessive_code_blocks", rule_excessive_code_blocks),
    ("unlimited_read_in_procedure", rule_unlimited_read_in_procedure),
    ("uncapped_followup", rule_uncapped_followup),
    ("batch_invitation", rule_batch_invitation),
]


def run_rules(content: SkillContent) -> list[dict[str, str]]:
    """Run every rule against the content. Returns a list of findings."""
    findings: list[dict[str, str]] = []
    for rule_id, rule in RULES:
        result = rule(content)
        if result is not None:
            severity, message = result
            findings.append(
                {"rule_id": rule_id, "severity": severity, "message": message}
            )
    return findings


def compute_ruleset_hash(rules_path: Path | None = None) -> str:
    """sha256 of the rules file's bytes. Embedded in each manifest entry's
    key, so any edit (even a comment) bumps the ruleset hash and forces
    re-review.

    Default: hashes THIS file's bytes via __file__. Tests pass an explicit
    path to a temp copy so they can assert the function actually changes
    output when the rules content changes (rather than only pinning a
    synthetic hash through audit_scope).
    """
    import hashlib

    if rules_path is None:
        rules_path = Path(__file__)
    return hashlib.sha256(rules_path.read_bytes()).hexdigest()
