---
name: skills-quality
description: Audit Claude Code skills (project + global) for token-economy hygiene — do they push work onto the LLM that a deterministic script should handle? A deterministic Python pre-pass flags smells; only flagged or changed skills enter LLM review. Manifest key is (skill_hash + ruleset_hash), so editing the rules re-keys every skill. Use whenever the user says "audit my skills for quality / token waste / LLM-as-loop smells", "are my skills well-designed", or invokes `/mikko-skills-quality`.
barney: Flags Claude Code skills that ask the LLM to do work a script should — long imperative prose with no companion script, missing frontmatter, oversized SKILL.md. Pre-pass is deterministic; LLM only reviews flagged or changed.
---

# When to use

User says "audit my skills for quality", "any skills wasting tokens?", "look for LLM-as-loop smells", "are my skills well-designed", or invokes `/mikko-skills-quality`.

Quarterly cadence, or after writing a new skill. Companion to `/mikko-skills-freshness` (which checks for STALE skills); this one checks for BADLY-DESIGNED skills.

# Workflow

## 0. First run — baseline first

Fresh install with no manifest yet? Run `--update` BEFORE reviewing. The script writes the manifest unconditionally and the next invocation starts from "all clean". Skip to step 5.

## 1. Run the audit

Pick the right script path for how the skill was installed:

| Install method | Script path |
|---|---|
| `install-mikko.sh` (prefixed) | `python ~/.claude/skills/mikko-skills-quality/skills-quality.py` |
| `install.sh skills-quality --target user` (unprefixed) | `python ~/.claude/skills/skills-quality/skills-quality.py` |
| Library checkout (no install) | `python skills/skills-quality/skills-quality.py` (from claude-skills repo root) |

Windows PowerShell — same paths with `$env:USERPROFILE` instead of `~` and `\` separators.

Defaults: both scopes (project under `cwd/.claude/skills/`, global under `~/.claude/skills/`), no manifest write.

## 2. Read the table

```
SCOPE    SKILL                            STATUS     TOP FINDING
project  big-iterator                     flagged    [HIGH] 6 loop-style prose patterns with no companion script. Likely asking ...
project  no-frontmatter-skill             flagged    [HIGH] Frontmatter missing required field(s): description.
global   touched-but-clean                changed    pre-pass clean - needs LLM verify (changed since last review)
```

If the table is `All skills pass quality + unchanged - nothing to review.`, **STOP**. Nothing further to do.

## 3. Per-row action

The TOP FINDING column + the optional `Additional findings:` block carry the full signal. **Do NOT open the skill's SKILL.md by default** — only when the message is ambiguous or the user asks for a fix proposal.

| Status | What to do |
|---|---|
| `flagged` | Read the top finding. Decide if the smell is real; propose a concrete extraction (move iteration into a script, add the missing frontmatter field, etc.) — don't auto-fix. |
| `changed` | Pre-pass passed but the skill was edited since the last baseline. Three-bullet check: (a) frontmatter still has name + description; (b) description still matches what the skill does; (c) any new loop-prose the rules might have missed. No deep read needed if all three are obvious from a 10-second skim. |
| `removed` | Skill directory gone. Confirm intentional; `--update` will drop the entry. |

## 4. Ask before editing

Present findings as a short table first. Do not modify any skill file without an explicit per-skill go-ahead.

## 5. Baseline once accepted

Same path as step 1, plus `--update`:

```
python <path-from-step-1> --update
```

Writes the manifest at each scope root. The next audit treats today's state as baseline.

# The ruleset

Lives in `rules.py` next to this script. Each rule's own `message` is self-describing in the audit output — no per-rule cheat-sheet needed here. The single non-obvious property: **editing rules.py re-keys every skill**, because the manifest entry's key is `(skill_hash + sha256(rules.py))`. A rule change forces a full re-review next audit.

`install.sh skills-quality --target user` (symlink mode) keeps reading the source `rules.py` and `_lib/`; if the source tree moves or you delete it, the skill breaks. `install-mikko.sh` (copy mode) bundles a sibling copy of each.

# Freshness check

```toml
[[check]]
kind = "path_exists"
path = "skills-quality.py"
root = "skill_dir"

[[check]]
kind = "path_exists"
path = "rules.py"
root = "skill_dir"

[[check]]
kind = "file_contains"
path = "skills-quality.py"
pattern = "SCRIPT_VERSION"
root = "skill_dir"

[[check]]
kind = "file_contains"
path = "rules.py"
pattern = "RULES"
root = "skill_dir"

[[check]]
kind = "no_broken_md_links"
```
