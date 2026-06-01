---
name: mikko-skills
description: List every installed `mikko-*` skill with a short plain-English (barney-style) description of what it does. Use when the user types `/mikko-skills`, asks "what mikko skills do I have", "list my skills", "remind me what's installed", or onboards a new machine. Reads each skill's `barney:` frontmatter field (falls back to `description` if missing). One-screen output, no walls of text.
barney: Lists your mikko- skills with plain-English descriptions. For when you forgot which one does what.
---

# mikko-skills

Print every installed `mikko-*` skill with a barney-style one-liner.

## When to use

- `/mikko-skills`, "what mikko skills do I have", "list my skills"
- After a fresh `claude-skills` install — quick sanity check that everything landed
- Before invoking another `mikko-*` skill, to confirm the exact name

NOT for: full SKILL.md contents (read the file directly), cross-repo registry (`/mikko-skill-registry`), or token-usage metrics (`/mikko-skill-usage`).

## Procedure

1. `Glob` `~/.claude/skills/mikko-*/SKILL.md` (user-wide) and `.claude/skills/mikko-*/SKILL.md` (project-local).
2. For each match, `Read` the first ~20 lines and parse the YAML frontmatter.
3. Extract `name` and `barney`. If `barney` is missing, fall back to the first sentence of `description` and add ` (no barney yet)` after the name.
4. Deduplicate by `name`; project-local wins and gets `(project)` appended.
5. Sort alphabetically.
6. Print as:

```
your mikko-* skills:

  mikko-ai-codegen-smell-audit
    <barney one-liner>

  mikko-audit
    <barney one-liner>

  ...
```

Skill name on its own line (bold/green if the terminal supports it), barney indented two spaces below. One blank line between entries. No table — barney lines are too varied in length to align cleanly.

Close with:

```
tip: `/mikko<Tab>` shows names only. For technical detail, open the skill's SKILL.md.
```

## Failure modes

- **No skills directory.** Print "no mikko-* skills installed yet" and a hint to run `./install.sh` from a `claude-skills` clone. Exit cleanly.
- **Frontmatter parse failure.** Don't fail the run — print dirname with `(unreadable frontmatter)` and continue.
- **Missing `barney:` field.** Print the first sentence of `description` and tag the name with `(no barney yet)` so the skill author knows to add one.

## Token expectations

For 5-10 installed skills: 1-2 globs, 5-10 small reads, one formatted print. ~5K tokens total. Should complete in under 5 seconds.

## Why barney style

The `description:` field is written for Claude (dense, trigger-keyword-loaded, multi-paragraph). Barney is written for **you** — one or two punchy sentences in plain English so a scan of the list answers "which skill do I want right now?" without re-reading dense prose every time.

If you add a new `mikko-*` skill, add a `barney:` field to its frontmatter. Keep it to one or two sentences. No jargon. Describe what it does and the outcome, not how it works.

## Freshness check

Staleness checks run by `/mikko-skills-freshness` on any change to this skill — they assert the skill's load-bearing pieces still ship / stay documented. See that skill for the check vocabulary.

```toml
[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "^barney:"

[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "mikko-\\*/SKILL\\.md"
```
