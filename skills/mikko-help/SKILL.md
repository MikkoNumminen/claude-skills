---
name: mikko-help
description: List every installed `mikko-*` skill with its description — the fast answer to "what mikko skills do I have" / "list my skills" / "remind me what's installed" when you remember you have a skill but not its name. Runs a bundled script (deterministic glob + frontmatter parse, ~no tokens). Pass `--detect` for codebase-aware audit recommendations on the current repo, `--barney` for plain-English one-liners; they combine. NOT a cross-repo registry (use `/skill-registry`) or a token-usage report (`/mikko-skill-usage`).
barney: Lists your mikko-* skills with their descriptions. Add --detect to recommend which audits to run on THIS repo, --barney for plain-English one-liners.
---

# mikko-help

The discoverability sidekick for the `mikko-*` namespace — for when you remember you have a skill for something but not its exact name. `/mikko<Tab>` already lists the *names* (free, built into the CLI); this adds the **descriptions** so you can pick by what each one does.

All the work — glob the skill dirs, parse each `SKILL.md` frontmatter, dedupe, sort, format — is deterministic, so it lives in a script rather than in LLM prose. One Bash call instead of ~8–11K tokens of glob+read+format per run.

## How to run

Run the bundled script and print its output verbatim:

```
python3 ~/.claude/skills/mikko-help/mikko-help.py [--barney] [--detect]
```

(From the source repo: `python3 skills/mikko-help/mikko-help.py`.) It globs `~/.claude/skills/mikko-*/SKILL.md` (user-wide) and `.claude/skills/mikko-*/SKILL.md` (project-local, wins on a name clash and gets a `(project)` tag), then prints a two-column name + description table. Nothing is written to disk.

## Flags

- *(none)* — list every skill with its `description`. Default; cheapest.
- `--barney` — show each skill's plain-English `barney:` line instead (falls back to the truncated `description`, tagged `(no barney)`, for skills without one).
- `--detect` — also fingerprint the current repo (reads a handful of root config files — `package.json`, `tsconfig.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `*.sln`/`*.csproj`/`global.json`, framework configs) and print an ordered "which audit should I run here" recommendation. Does not walk the source tree and does not dispatch audits — it's a hallway sign, not a tour guide.

`--detect` and `--barney` are independent and combine.

## Detection matrix (`--detect`)

The recommendation logic lives in `skills_listing.recommend_audits`. In short: React → `react-anti-patterns-audit` first, then the universal `ai-codegen-smell-audit` + `audit`; .NET / ASP.NET Core → `dotnet-audit` first, then `ai-codegen-smell-audit` + `audit`; other non-React → `audit` + `ai-codegen-smell-audit`; security-sensitive deps (auth/db/network/crypto libraries, or ASP.NET Core Identity / EF Core) lift `security-audit` from skip to suggest. React Native adds `--force` to bypass the web-shape pre-flight.

## Failure modes

- **No skills directory.** Prints "no mikko-* skills installed yet" and a hint to run `./install-mikko.sh`. Exits cleanly.
- **Malformed frontmatter.** Falls back to the directory name + `(no description)` rather than failing the run.
- **`--detect` with no config files.** Reports "language: unknown" and recommends `audit` only — honest about what it can't infer.

## Why this skill exists

`/mikko<Tab>` gives names; the gap `mikko-help` fills is needing **descriptions** to choose between similarly-named skills, or to recall what a freshly-installed skill does. For a portfolio audience it's a small, real signal that the `mikko-*` prefix is a deliberately-designed namespace with its own "what's in here" command — and that the listing is a cheap script, not an LLM loop.

## Freshness check

Staleness checks run by `/mikko-skills-freshness` on any change to this skill.

```toml
[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "^## Flags"

[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "`--detect`"

[[check]]
kind = "path_exists"
path = "mikko-help.py"
```
