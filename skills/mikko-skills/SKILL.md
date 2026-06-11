---
name: mikko-skills
description: List every installed `mikko-*` skill with a plain-English (barney) one-liner — for "what mikko skills do I have", "list my skills", "remind me what's installed", or onboarding a machine. Runs a bundled script (deterministic; reads each skill's `barney:` field, falls back to `description`). One-screen output. For dense per-skill detail use `/mikko-help`.
barney: Lists your mikko- skills with plain-English descriptions. For when you forgot which one does what.
---

# mikko-skills

Print every installed `mikko-*` skill with a barney-style one-liner — the friendly, scannable counterpart to `mikko-help`'s denser table. Same deterministic work (glob + frontmatter parse), run as a script rather than LLM prose.

## How to run

Run the bundled script and print its output verbatim:

```
python3 ~/.claude/skills/mikko-skills/mikko-skills.py
```

(From the source repo: `python3 skills/mikko-skills/mikko-skills.py`.) It globs `~/.claude/skills/mikko-*/SKILL.md` and the project-local `.claude/skills/mikko-*/SKILL.md`, reads each skill's `barney:` field (falling back to a truncated `description`, tagged `(no barney yet)`), dedupes with project-local winning, and prints a vertical name-then-one-liner list.

## Why barney style

The `description:` field is written for Claude — dense, trigger-loaded. Barney is written for **you**: one or two punchy plain-English sentences so a scan of the list answers "which skill do I want right now?" without re-reading dense prose. When you add a new `mikko-*` skill, add a `barney:` field — one or two jargon-free sentences describing what it does and the outcome, not how.

## Freshness check

Staleness checks run by `/mikko-skills-freshness` on any change to this skill.

```toml
[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "^barney:"

[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "mikko-\\*/SKILL\\.md"

[[check]]
kind = "path_exists"
path = "mikko-skills.py"
```
