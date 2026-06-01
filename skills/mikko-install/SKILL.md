---
name: mikko-install
description: Install, update, list, or uninstall `mikko-*` skills from the cloned `claude-skills` source repo into the user-wide skill directory (`~/.claude/skills/mikko-*`). Wraps the existing `install-mikko.sh` and `install.sh` scripts so the install loop is reachable from inside any Claude Code session via a slash command — no need to leave the conversation, find the repo, and run bash by hand. Use whenever the user says "install the mikko skills", "install everything", "add mikko-readme-drift-sync", "update my mikko skills", "what's new since last install", or "uninstall mikko-foo". Locates the source repo via the current working directory, parent directories, or known sibling locations (configurable). Does NOT clone the repo (the user clones it once, by hand). Does NOT touch skills outside the `mikko-*` prefix.
barney: Installs, updates, or removes mikko-* skills from the claude-skills source repo, without you having to leave the chat. Wraps install-mikko.sh / install.sh so you don't have to remember where they live.
---

# mikko-install

The slash-command face of the `claude-skills` installers. Reads `mikko-*` skills from a cloned source repo on disk and writes them into `~/.claude/skills/` via the repo's existing bash scripts. Lets you install / update / remove from inside any Claude Code session.

## When to invoke

- "install the mikko skills" / "install everything" — bulk install all `mikko-*` skills, mikko-prefixed.
- "install `<name>`" (e.g. "install readme-drift-sync", "install ai-codegen-smell-audit") — install one specific skill.
- "update my mikko skills" / "re-run the install" — after a `git pull` in the source repo, re-copy everything so installed copies match source.
- "what mikko skills are new since last install" / "anything new to install" — list source skills that aren't installed yet.
- "uninstall `mikko-foo`" / "remove `mikko-foo`" — delete the user-wide install of one skill.

## When NOT to invoke

- **Not** for cloning the source repo. The user clones `claude-skills` once, by hand. This skill assumes the clone already exists on disk.
- **Not** for non-`mikko-*` skills. Anthropic-shipped skills and skills under other namespaces are out of scope.
- **Not** for editing skill content. Edit the source repo and re-run install; never hand-edit the installed copy.
- **Not** for installing into a project (only user-wide is in scope here). For per-project install, use the underlying `./install.sh <name> --target project --repo <path>` directly — that's a different use case.

## Procedure

### 1. Locate the source repo

The source repo is the cloned `claude-skills` directory. The skill looks for it, in order:

1. **Current working directory** — if `cwd` contains `install-mikko.sh` AND a `skills/` directory, use cwd.
2. **Parent directory of cwd** — walk up two levels checking for the same markers (handles "I'm in `<repo>/some/sub/dir/`").
3. **Ask the user once** — if neither hits, ask: "Where's your claude-skills clone? (full path)". Bail with a clear message if no answer. Do NOT probe hardcoded author-specific paths — every fork lives somewhere different.

Once located, verify by checking that `<source>/install-mikko.sh` and `<source>/skills/*/SKILL.md` both exist. Cache the resolved path in the conversation context for the rest of the turn.

### 2. Map intent to action

The skill dispatches based on what the user asked for. Default to **install all** when intent is unclear.

| Intent | Action |
| --- | --- |
| "install everything" / "install the mikko skills" / "update my mikko skills" | `bash <source>/install-mikko.sh` |
| "what's new" / "list new skills" / "anything to install" | Glob `<source>/skills/*/SKILL.md` AND `~/.claude/skills/*/SKILL.md` (no prefix filter — see the diff-logic note below). Normalise names so `<source>/skills/foo/` maps to either `foo` or `mikko-foo` already installed. Print the source skills that aren't represented in any form in the install dir. |
| "install `<name>`" (default — match the rest of the user's namespace) | `rm -rf ~/.claude/skills/mikko-<name>/ && cp -R <source>/skills/<name>/ ~/.claude/skills/mikko-<name>/`. The `rm -rf` before the `cp -R` is load-bearing — without it, `cp -R` merges into an existing directory and files removed upstream would persist as orphans. This matches the "replace existing" semantics of `install-mikko.sh`'s bulk path. The result is `/mikko-<name>` as a slash command, matching every other `mikko-*` skill the user has. |
| "install `<name>` without the mikko- prefix" / "install `<name>` symlinked" | `bash <source>/install.sh <name> --target user`. Symlink install, keeps the source name (no prefix). Use this only when the user explicitly wants the unprefixed name or live-update via `git pull` without re-running the installer. |
| "uninstall `mikko-<name>`" | Confirm with the user once, then `rm -rf ~/.claude/skills/mikko-<name>`. **Always confirm before deleting.** Symlinked installs (without prefix) get the same treatment at `~/.claude/skills/<name>`. |
| "dry run" / "show me what would happen" | Add `--dry-run` to `install-mikko.sh`; for the cp/rm paths describe what would happen in chat without invoking. |

**Diff-logic note (for the "what's new" intent):** the user's namespace may be mixed — most skills are mikko-prefixed (from `install-mikko.sh`) but some may be unprefixed (from `install.sh <name>`). To avoid reporting `mikko-foo` as "new" when an unprefixed `foo` already exists, the diff compares **source skill names** against installed directory names, treating `foo` and `mikko-foo` as equivalent. A source skill counts as installed if `~/.claude/skills/<source-name>/` OR `~/.claude/skills/mikko-<source-name>/` exists. When the source name is already mikko-prefixed (e.g. `mikko-help`), this naturally collapses to checking `~/.claude/skills/mikko-help/` once via the first form.

### 3. Execute the action

Run the bash command via the `Bash` tool. Capture stdout / stderr / exit code. On non-zero exit, print the error block to the user and bail — don't try to "fix" install failures from inside this skill.

### 4. Confirm + summarise

After a successful install, print a one-line summary:

```
installed N skill(s) into ~/.claude/skills/  (M new, K updated)
```

If the user requested "what's new" without installing, just print the list and stop — don't install on a list query.

### 5. Restart hint

End the run with: `Claude Code picks up new skills on the next conversation turn — no restart needed.` (Empirically true; the harness re-globs the skills dir each turn.)

## Output format

Default (install all):

```
mikko-install — source: <resolved-path-to-claude-skills>

[install-mikko.sh output here]

installed 9 skill(s) into ~/.claude/skills/ (1 new, 8 updated)
```

"What's new":

```
mikko-install — source: <resolved-path-to-claude-skills>

new skills available (not installed):
  mikko-readme-drift-sync
  mikko-foo  (if applicable)

run /mikko-install to add them.
```

Uninstall:

```
mikko-install — about to remove:
  ~/.claude/skills/mikko-foo

confirm? [y/N]
```

## What this skill does NOT do

- **Does not clone, fetch, or pull from a remote.** The user runs `git pull` in the source repo by hand. This skill reads from whatever's already on disk.
- **Does not edit installed skill content.** Source is the source of truth; the installed copy is downstream.
- **Does not touch skills outside the `mikko-*` prefix.** Anthropic-shipped skills (`init`, `review`, etc.) and other namespaces are invisible to this skill.
- **Does not double-prefix.** Source skills already starting with `mikko-` (like `mikko-help`, `mikko-audit-suite`, this skill itself) install as-is, not as `mikko-mikko-foo`. `install-mikko.sh` already handles that — the skill just delegates.
- **Does not auto-uninstall.** Removing a skill always asks for confirmation, even with explicit `--force` from the user.

## Failure modes

- **Source repo not found.** Probes the known locations; if nothing matches, asks the user once. If still nothing, exits with `error: can't find your claude-skills clone — pass the path explicitly.`
- **`install-mikko.sh` or `install.sh` missing from source.** Should never happen on a clean clone; if it does, the skill exits with `error: <source>/install-mikko.sh is missing — your clone might be partial. Re-clone or git pull.`
- **Permission denied writing to `~/.claude/skills/`.** Surface the underlying bash error; don't try to escalate privileges.
- **Symlink fails on Windows without Developer Mode (for `install.sh` per-skill).** `install.sh` symlinks; on Windows Git Bash with default settings, that may fall back to copy. `install-mikko.sh` copies by design — recommend `install-mikko.sh` on Windows when symlink-vs-copy doesn't matter.
- **Skill installed but not appearing as a slash command.** Tell the user: `Claude Code reads ~/.claude/skills/ each turn. If /<skill-name> still doesn't trigger, check that ~/.claude/skills/<name>/SKILL.md exists and the frontmatter has a name: field matching the directory.`

## Why this skill exists

The `claude-skills` repo ships with two bash installers (`install.sh`, `install-mikko.sh`) that work fine on the command line. They're not discoverable from inside a Claude Code conversation — to use them you have to (a) know they exist, (b) find the cloned repo, (c) `cd` there, (d) remember the flags, (e) run the script. Five steps no `/mikko-help` ever tells you about.

This skill closes that loop. Once installed (via `install-mikko.sh` one time on a fresh machine), `/mikko-install` lets you add the next skill, update everything after a `git pull`, or remove a skill — all without leaving the chat.

The chicken-and-egg of "you need install to install" is solved by `install-mikko.sh` being the bootstrap (one-time bash invocation), after which this skill is the steady-state installer (slash command from any session).

## Token expectations

~3–5K tokens per typical invocation:
- Source probe + verification: ~1K (Glob + existence checks)
- Action dispatch: ~1K (bash invocation + capture)
- Summary print: ~1K

Run `/mikko-skill-usage` for measured numbers after a few invocations.

Cadence: once at machine setup, then a handful of times per year when new skills land or you want to update.

## Freshness check

Staleness checks run by `/mikko-skills-freshness` on any change to this skill — they assert the skill's load-bearing pieces still ship / stay documented. See that skill for the check vocabulary.

```toml
[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "install-mikko\\.sh"

[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "mikko-\\*"
```
