---
name: mikko-skills-freshness
description: Audit Claude Code skills (project + global scopes) for staleness. A pure-stdlib Python script does sha256-based change detection — only new/changed/removed skills are surfaced, unchanged skills are never loaded into context. Skills can declare their own freshness checks under '# Freshness check' as TOML; otherwise the LLM does a generic review (frontmatter, description-vs-behavior, broken refs). Asks before editing anything. Use whenever the user says "are my skills up to date", "audit my skills", "check for skill drift", or invokes `/mikko-skills-freshness`.
barney: Tells you which of your Claude Code skills have changed since you last verified them — without re-reading the ones that haven't. Run quarterly.
---

# When to use

User says "are my skills up to date", "audit my skills", "check for skill drift", invokes `/mikko-skills-freshness`.

NOT for every commit. Cadence: when you suspect a referenced path has moved, after a refactor that renamed things, or quarterly.

# Workflow

## 0. First run — baseline first

Fresh install with no manifest yet? Run `--update` BEFORE the review loop. The script writes the manifest unconditionally and the next invocation starts from "all up to date." Skip step 1; jump to step 5 syntax with `--update`.

## 1. Run the audit

Pick the right script path for how the skill was installed:

| Install method | Script path |
|---|---|
| `install-mikko.sh` (prefixed) | `python ~/.claude/skills/mikko-skills-freshness/skills-freshness.py` |
| `install.sh skills-freshness --target user` (unprefixed) | `python ~/.claude/skills/skills-freshness/skills-freshness.py` |
| Library checkout (no install) | `python skills/skills-freshness/skills-freshness.py` (from claude-skills repo root) |

Windows PowerShell — same paths with `$env:USERPROFILE` instead of `~` and `\` separators.

Defaults: both scopes (project under `cwd/.claude/skills/`, global under `~/.claude/skills/`), no manifest write.

## 2. Read the table

```
SCOPE    SKILL                            STATUS   CHECKS / ISSUE
project  equipment                        changed  2 pass, 1 FAIL
project  new-mission                      changed  no declared criteria - needs LLM review
global   mikko-audit                      new      3 pass
```

If the table is `All skills up to date - nothing to review.`, **STOP**. Nothing further to do.

## 3. Per-row action

| Row says | What to do |
|---|---|
| `N pass` only | Tell the user it's clean. Don't load the SKILL.md. |
| `M FAIL` / `K ERROR` | Inspect the failing checks under "Failures / errors", read the cited paths, propose a fix or explain why the check itself is wrong. Don't auto-fix. |
| `no declared criteria - needs LLM review` | Read the SKILL.md once with `limit=80` (frontmatter + first one or two sections is all you need — no deep read). Verify: (a) frontmatter has `name` + `description`; (b) the description still matches what the skill does; (c) no broken file/command references in the body — cap path verification at **one `ls` per finding, max 3 traces total**, don't spelunk into source repos. Surface anything off. |
| `removed` | Confirm the deletion was intentional; the manifest update will drop the entry. |
| `TOML parse error: ...` | Quote the error verbatim to the user. Don't guess fixes. |

## 4. Ask before editing

Present findings as a short table first. Do not modify any skill file without explicit user approval.

## 5. Baseline once accepted

Same path as step 1, plus `--update`:

```
python <path-from-step-1> --update
```

Writes the manifest at each scope root. The next audit treats today's state as baseline.

The project manifest is **per-machine**, not committable across mixed-OS teams — a sha256 over CRLF (Windows checkout) differs from LF (Unix checkout) of the same skill. Mixed-OS contributors should gitignore `.claude/skills-freshness.manifest.json`.

# How to declare freshness criteria in a skill

In any SKILL.md, add a section under the exact heading `# Freshness check` (or `##`/`###`) followed by a fenced TOML block:

```toml
[[check]]
kind = "path_exists"
path = "src/game/data/weapons.json"

[[check]]
kind = "file_contains"
path = "src/lib/schemas/save.ts"
pattern = "WEAPON_IDS"

[[check]]
kind = "no_broken_md_links"
```

## Check kinds

| kind | required | optional | passes when |
|---|---|---|---|
| `path_exists` | `path` | `root` | file or dir exists |
| `file_contains` | `path`, `pattern` | `root` | regex matches (first 1 MB scanned) |
| `file_lacks` | `path`, `pattern` | `root` | regex does NOT match (catches deprecated refs) |
| `no_broken_md_links` | — | `path`, `root` | every relative `[text](path)` link resolves (default `path` is `SKILL.md`) |
| `command_exists` | `command` | — | binary is on PATH |

`pattern` is a Python `re` regex, evaluated multiline.

`root` selects the path anchor:
- `skill_dir` — this skill's own directory
- `scope_root` — the repo root (project scope) or `$HOME` (global scope)
- `home` — `$HOME`
- `absolute` — `path` must be absolute (`~` expanded)

Default: `scope_root` for project skills, `skill_dir` for global skills. Paths cannot escape their resolved root.

Content-reading checks (`file_contains`, `file_lacks`, `no_broken_md_links`) are restricted to `skill_dir` and `scope_root` — they reject `root="home"` / `root="absolute"` to prevent a skill from probing arbitrary files via a regex oracle. `file_lacks` on a missing file PASSES (use `path_exists` + `file_lacks` together to assert both).

# Freshness check

```toml
[[check]]
kind = "path_exists"
path = "skills-freshness.py"
root = "skill_dir"

[[check]]
kind = "file_contains"
path = "skills-freshness.py"
pattern = "SCRIPT_VERSION"
root = "skill_dir"

[[check]]
kind = "no_broken_md_links"
```
