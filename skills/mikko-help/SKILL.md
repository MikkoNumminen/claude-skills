---
name: mikko-help
description: List every installed `mikko-*` skill with its description (or with its `barney:` field when `--barney` is passed). The fast answer to "I know I have a skill for this but can't remember which one" / "what mikko skills do I have" / "list my skills" / "remind me what's installed." Pass `--detect` for codebase-aware audit recommendations ("which audit should I run on this repo" / "what's relevant for this codebase"). Pass `--barney` for plain-English short descriptions ("give me the friendly version" / "plain-English list"). `--detect` and `--barney` combine independently. No sub-agents, no network, no measurements — just a table. Full mode docs live in the body's "Flags" section.
barney: Lists your mikko-* skills with their descriptions. Add --detect to also recommend which audits to run on THIS repo. Add --barney to swap descriptions for plain-English one-liners.
---

# mikko-help

The discoverability sidekick for the `mikko-*` skill namespace. Type `/mikko-help` when you remember you have a skill for something but can't recall its exact name.

`/mikko<Tab>` from any Claude Code prompt already lists the *names* of every installed `mikko-*` skill (free, built into the CLI). `mikko-help` adds the **descriptions** so you can pick by what each one does, not just by name.

## When to use

- "/mikko-help", "what mikko skills do I have", "list my skills", "remind me what's installed"
- "/mikko-help --detect", "which audit should I run on this repo", "what's relevant for this codebase"
- "/mikko-help --barney", "give me the friendly version", "plain-English list", "I don't need the full pitch"
- Onboarding a new machine after a `claude-skills` `./install.sh` run — quick verification that everything landed
- Before invoking another `mikko-*` skill, to confirm the exact name and what it expects
- When you've just `cd`'d into an unfamiliar codebase and want a friendly "here's what your toolkit would do here" pointer
- When walking a colleague (or a recruiter) through what your skill catalog does — `--barney` reads like a tour, the full `description` reads like a contract

NOT for: cross-repo registry of skills (use `/skill-registry` for that — it walks sibling repos, this only reads the local skills directory), token-usage measurements (`/mikko-skill-usage` does that), or a full description of any one skill (use `man <name>` patterns or read its SKILL.md directly).

## Flags

- (no flag) — list every installed `mikko-*` skill with its `description` field. Default behavior; cheapest.
- `--detect` — also scan the current working directory's codebase shape (language, framework, security surface) and emit an ordered "which audit should I run here" recommendation alongside the listing. Adds ~10K tokens to the run.
- `--barney` — show each skill's optional `barney:` frontmatter field instead of the full `description`. Plain-English one-liners aimed at "what does this do" rather than "when does this fire / what's the full invocation surface." Falls back to `description` (truncated) for any skill without a `barney:` field. Cheap; same cost as default mode.

`--detect` and `--barney` are independent and can combine: `/mikko-help --detect --barney` recommends audits AND uses the barney-style copy in the suggestion table.

## What this skill does

**Default mode (no flag):**

1. Glob `~/.claude/skills/mikko-*/SKILL.md` (user-wide skills).
2. Glob `.claude/skills/mikko-*/SKILL.md` relative to the current working directory (project-local skills).
3. For each path, read the first ~15 lines and extract the YAML frontmatter `name`, `description`, and `barney` (optional) fields.
4. Deduplicate by `name` (a skill installed both user-wide AND project-local appears once; the project-local copy wins, matching Claude Code's own resolution order).
5. Sort alphabetically.
6. Print a two-column table: name (green) + description-first-sentence (dim). Truncate descriptions longer than ~120 characters with an em-dash continuation.

**`--barney` mode (substitutes step 6's source):**

6b. Use each skill's `barney` field as the description column, falling back to the truncated `description` field when `barney` is absent. Everything else (glob, dedupe, sort, formatting) is identical.

**`--detect` mode (everything above, plus):**

7. Run the codebase-shape detection (see "`--detect` mode" section below).
8. Map detected signals to a recommendation list using the decision matrix.
9. Print the recommendation list AFTER the regular skill table, with one-line rationale per audit (why it's relevant here, or why it's being skipped). When `--barney` is ALSO passed, the regular skill table at the top uses barney-style copy (same as bare `--barney`). **The recommendation rationales below stay codebase-specific** — they depend on `--detect` signals (e.g. "targets the React-specific layer, 12 .tsx files"), not on the skill's static description. `--barney` is presentation for the listing, not content for the recommendation reasoning.

End-to-end in one main-thread turn. No tools beyond `Glob` and `Read`. Output goes to the chat — nothing is written to disk.

## Output format

```
your installed mikko-* skills:

  mikko-audit            Run a multi-phase robustness audit of the current codebase…
  mikko-help             List every installed mikko-* skill with its one-line description.
  mikko-skill-registry   Walk every sibling repo under D:/koodaamista, find each .claude/…
  mikko-skill-usage      Measure actual Claude Code skill usage from local transcript JSONL…
  mikko-md-to-pdf        Render a markdown report (or any HTML) to a styled PDF using local…
  mikko-sync-readmes     Audit project data against sibling repos' READMEs and open a PR…

tip: `/mikko<Tab>` shows names only. For the cross-repo registry with token math, run `/skill-registry`.
```

Truncate descriptions at the first em-dash / period if shorter; otherwise hard-cap at 120 characters and append `…`. The goal is one-screen scannability, not full prose.

If both user-wide and project-local copies of the same skill exist, append `(project)` after the project-local one's name so the distinction is visible.

### `--barney` mode output

```
your installed mikko-* skills (barney style):

  mikko-audit                      Looks for bugs in your code — leaks, races, swallowed errors, missing timeouts…
  mikko-ai-codegen-smell-audit     Scans for ten patterns that show up most often in AI-generated code…
  mikko-help                       Lists your mikko-* skills with their descriptions. Add --detect to also…
  mikko-react-anti-patterns-audit  Checks your React code for six common gotchas (index-as-key, useEffect-for…
  mikko-security-audit             Walks your attack surface (auth, input, secrets, deps, etc.), finds security…
  mikko-skill-usage                Counts how often you've actually used each Claude Code skill by reading…
  mikko-audit-suite                Runs every audit that fits this codebase, then writes one summary doc…

tip: drop --barney for the full description, or add --detect to also see audit recommendations for THIS repo.
```

A skill without a `barney:` field shows the truncated `description` with an `(no barney)` annotation so the gap is visible — encourages adding the field when authoring new skills, doesn't break the listing for skills that don't have it.

### `--detect` mode output

```
your installed mikko-* skills:

  mikko-audit                      Run a multi-phase robustness audit of the current codebase…
  mikko-ai-codegen-smell-audit     Read-only audit for ten LLM-codegen failure modes…
  mikko-help                       List every installed mikko-* skill with its description.
  mikko-react-anti-patterns-audit  Read-only audit for six React anti-patterns with a pre-flight fit check.
  mikko-security-audit             Multi-phase security audit + remediation, gated per phase.
  mikko-skill-usage                Measure actual Claude Code skill usage from local transcript JSONL.

detected codebase shape:
  • language: TypeScript + React (12 .tsx files, react in package.json)
  • framework: Astro (astro.config.mjs present)
  • testing: Vitest (vitest in devDependencies)
  • security surface: low (no auth/db/network deps detected)

suggested audits, in order:
  /mikko-react-anti-patterns-audit   → targets the React-specific layer (12 .tsx files)
  /mikko-ai-codegen-smell-audit      → universal LLM-codegen patterns, language-agnostic
  /mikko-audit                       → universal robustness audit, always useful

skipped:
  /mikko-security-audit              → low security surface detected; revisit if untrusted input is added
  /mikko-skill-usage                 → measurement skill, not an audit

tip: each suggestion is independent — invocations can be days/weeks apart.
```

## `--detect` mode

The detection pass is **fast and cheap** (~5K tokens) and produces a ranked list of which audit skills are most likely to find signal in the codebase Claude Code is currently rooted in. It deliberately doesn't run the audits — that's still the human's call. It just removes the "which one should I even start with?" friction.

### Detection signals

The detector reads up to ~5 files in the project root to fingerprint the codebase. It does NOT walk the source tree (that's each audit skill's own job):

| Signal | Reads | Detects |
| --- | --- | --- |
| `package.json` | dependencies + devDependencies | Node / JS / TS / React / React Native / Vue / Svelte / Next / Astro / Vite / framework versions; auth deps (`jsonwebtoken`, `passport`, `next-auth`); db deps (`pg`, `mongoose`, `sqlite3`, `drizzle-orm`); network/server (`express`, `fastify`, `hono`) |
| `tsconfig.json` (existence) | — | TypeScript layer |
| `pyproject.toml` / `requirements.txt` / `setup.py` | — | Python |
| `Cargo.toml` | — | Rust |
| `go.mod` | — | Go |
| `astro.config.mjs` / `next.config.{js,mjs,ts}` / `vite.config.{js,ts}` (existence) | — | Astro / Next.js / Vite (cross-checked with `package.json`) |
| `.eslintrc*` / `eslint.config.*` (existence) | — | Lint baseline present (suggests the linter already catches some patterns this skill's audits would otherwise duplicate) |
| `Glob` `*.{tsx,jsx,py,rs,go,vue,svelte}` (count) | — | File-extension density (used as secondary confirmation) |

### Decision matrix — which audits to suggest

| Detected shape | Suggested audits (in order) | Notes |
| --- | --- | --- |
| React (any flavor) | `react-anti-patterns-audit` → `ai-codegen-smell-audit` → `audit` | React-specific first because highest-signal-per-token |
| React Native | `react-anti-patterns-audit --force` → `ai-codegen-smell-audit` → `audit` | Five of six React checks apply; `--force` bypasses the web-shape pre-flight |
| TypeScript without React (Node API, CLI, library) | `audit` → `ai-codegen-smell-audit` | No framework-specific audit yet |
| Python | `audit` → `ai-codegen-smell-audit` | Universal-only; future `python-defensive-style-audit` would go first if it lands |
| Rust / Go | `audit` → `ai-codegen-smell-audit` | Same |
| Plain JS (no TS, no framework) | `audit` → `ai-codegen-smell-audit` | Universal-only |
| Unknown / mixed / no clear signal | `audit` | The safest fallback — runs on any source tree |
| Any of the above + security-sensitive deps detected | (above list) + `security-audit` | Auth / db / network deps lift `security-audit` from "skip" to "suggest" |

### What "security-sensitive" means

The detector flags a codebase as security-sensitive if `package.json` (or language equivalent) names any of:

- Auth libraries: `jsonwebtoken`, `passport`, `next-auth`, `iron-session`, `lucia`, `oauth4webapi`, `clerk-*`, `auth0-*`
- DB libraries: `pg`, `mongoose`, `sqlite3`, `drizzle-orm`, `prisma`, `kysely`, `typeorm`
- Server/network: `express`, `fastify`, `hono`, `koa`, `nestjs`, `tRPC`, `apollo-server`
- Crypto: `bcrypt`, `argon2`, `crypto-js`, `node-forge`

The list is intentionally conservative — a portfolio-rendering Astro site that imports `marked` for markdown is not security-sensitive; a Node API server with `express` + `pg` is. If your codebase has security surface that doesn't trigger any of these, that's still a fine reason to run `security-audit` — the detector is suggesting, not gatekeeping.

### What the detector does NOT do

- **Does not run audits.** It reads ~5 files, prints recommendations, and exits.
- **Does not walk the source tree.** Each audit skill walks its own scope; the detector is a hallway sign, not a tour guide.
- **Does not measure quality.** A codebase with many `.tsx` files isn't "more React than" one with few — the recommendation depends on whether the patterns apply, not how often.
- **Does not learn from history.** Each run starts fresh from the file signals. If you ran `mikko-audit` yesterday and it found nothing, `--detect` will still recommend it today because the recommendation is "this audit is relevant here," not "this audit hasn't fired yet."

## Procedure

### 1. Discover skills

```
Glob: ~/.claude/skills/mikko-*/SKILL.md
Glob: .claude/skills/mikko-*/SKILL.md   (relative to CWD)
```

Both globs are cheap. The user-wide path is platform-dependent — use `os.homedir()`-equivalent expansion (the `Glob` tool handles `~` on Unix; on Windows, expand `$USERPROFILE`/`$HOME` or use the absolute path explicitly).

### 2. Read frontmatter

For each matched `SKILL.md`, `Read` the first 15 lines (was 10 — bumped to comfortably cover `name`, `description`, and an optional `barney` line). Parse the YAML frontmatter between the `---` delimiters. Extract `name`, `description`, and `barney` (optional). When `--barney` is passed and the field is missing, fall back to the truncated `description` with a `(no barney)` annotation so authors are nudged to add the field at next edit.

If the frontmatter is malformed or the file has none, fall back to the parent directory name as the `name` and `(no description)` as the description — log the skip in a `notes` section at the bottom of the output.

### 3. Format + print

Sort by name. Find the longest skill name (cap at 24 chars; longer names get truncated with `…`). Pad to that width + 4 spaces, then print the truncated description. Use `printHTML` style if rendering through a terminal that supports color; plain print otherwise.

### 4. Check for new skills (cheap, non-blocking)

After the listing prints, attempt to locate the `claude-skills` source repo to see if there are skills in source that aren't installed yet. Probe order:

1. **Current working directory** — does it have `install-mikko.sh` AND a `skills/` directory? If yes, that's the source.
2. **Parent directory of cwd** — walk up two levels checking for the same markers.

If neither hits, **skip silently**. Don't badger the user about a possibly-missing repo, and don't probe hardcoded author-specific paths. This check is best-effort discovery, not a gate.

If the source IS found:
- `Glob` `<source>/skills/*/SKILL.md` and read the `name:` from each → set of source skills.
- `Glob` `~/.claude/skills/*/SKILL.md` (note: NO `mikko-*` prefix filter — the user's namespace may be mixed; some skills install unprefixed via `install.sh`).
- For each source skill, count it as "installed" if ANY of these match a real install-dir entry: the source name itself (`foo`), the mikko-prefixed form (`mikko-foo`), or the source name when already prefixed (`mikko-foo` source → look for `mikko-foo` install).
- Set difference: source skills NOT represented in any installed form.
- If non-empty, print a footer using a plain text marker — no emoji:

  ```
  NEW: N skill(s) available since your last install:
       mikko-readme-drift-sync
       mikko-foo
     Run /mikko-install to add them.
  ```

### 5. Done

Print the tip line about `/mikko<Tab>` and `/skill-registry`, then exit. The whole skill should complete in under 5 seconds end-to-end.

## Token expectations

**Default mode** (no `--detect`), for ~12-15 installed skills:

- 1-2 × `Glob` (~0.5K each)
- 12-15 × `Read` of first 10 lines (~0.5K each input, ~6-8K total)
- 1 × format + print (~1-2K output)

Total: ~8-11K tokens per invocation. Still among the cheapest in the catalog.

**`--detect` mode** adds:

- Up to 5 × `Read` of root-level config files (`package.json`, `tsconfig.json`, `pyproject.toml`, etc.) — ~3-5K input
- 3-5 × `Glob` to count file-extension density — ~1-2K
- 1 × matrix-mapping + formatted recommendation print — ~2-3K output

Total with `--detect`: ~10-15K tokens. Still cheap; the detection pass deliberately doesn't walk the source tree.

Cadence: ad-hoc, usually a few times per week when actively iterating. ~50 uses/year for a regular Claude Code user; lower if you have the names memorized. `--detect` mode used more sparingly — when first opening an unfamiliar repo or after `cd`'ing into a different consumer repo.

## Failure modes

- **No skills directory.** If neither `~/.claude/skills/` nor `.claude/skills/` exists, print "no mikko-* skills installed yet" and a hint to run `./install.sh --list` in a checked-out `claude-skills` clone. Exit cleanly.
- **YAML frontmatter parse failure.** Don't fail the whole run — fall back to dirname + "(no description)" and add a one-line note.
- **Symlinked skills.** When a skill is installed via `claude-skills/install.sh`, the directory is a symlink. `Glob` and `Read` follow symlinks transparently; nothing special needed.
- **Non-mikko-* skills in the same directory.** The glob filter excludes them. If the user wants to see Anthropic-shipped skills too, that's `/help` territory, not this skill.
- **`--barney` on a skill without the field.** Falls back to the truncated `description` with an `(no barney)` annotation. The annotation is the design: it makes the gap visible without breaking the listing, nudging the human (or the next SKILL.md author) to add the field at next edit. Don't infer or invent a barney line — that defeats the point of having an explicit field.
- **`--detect` in a directory with no config files.** A plain `/tmp/scratch/` with one `.py` file and nothing else returns the "Unknown / mixed / no clear signal" row from the matrix. The recommendation is `audit` only. This is correct behavior, not a bug — the detector is honest about what it can and can't infer.
- **`--detect` in a polyglot monorepo.** A repo with both a Python backend AND a React frontend gets recommendations for both stacks. The output prints two grouped sections rather than collapsing into a single "polyglot" verdict — concrete is more useful than abstract here.
- **New-skills footer only fires when invoked from inside the `claude-skills` source repo** (or a subdirectory). From a consumer repo (e.g. one of your other projects), the source-probe misses and the footer skips silently — by design, since the skill doesn't track external paths. **The moment you most want the reminder is exactly when you're not in the source repo**, so the practical workflow is: run `/mikko-help` from your `claude-skills` checkout periodically (e.g. after a `git pull`) to see what's new. From everywhere else, the listing still works — just no new-skills footer.

## Limitations

- **Description truncation loses detail.** Full descriptions can be hundreds of characters with multiple invocation triggers. The table view shows only the first ~120 chars. For the full description, open the SKILL.md directly (path is available in the table if rendered with file links).
- **Local-only view.** This skill only sees what's installed on the current machine. Cross-repo / cross-machine inventory is the `/skill-registry` job.
- **No token economics.** This is a name + description list, not a usage report. For tokens-per-use math, run `/mikko-skill-usage` then read the resulting JSON.
- **`--detect` is a heuristic, not a guarantee.** The decision matrix is opinionated — it picks the audits Mikko reaches for first on each codebase shape. Your priorities may differ. The recommendation is a "here's where I'd start" hallway sign, not a rule.
- **`--detect` doesn't dispatch audits.** It only suggests. The human still invokes each suggested audit by name. This is by design — skills are recipes, not orchestrators. A future "/mikko-audit-suite" skill could automate the dispatch loop, but that's a separate decision worth making explicitly rather than smuggling it into `mikko-help`.

## Why this skill exists

The `/mikko<Tab>` shortcut from Claude Code's built-in slash-completion already gives names. The gap that `mikko-help` fills is when you need **descriptions** to choose between two skills with similar names — or when you've installed a new skill and forgotten what it does without re-reading the SKILL.md.

For a portfolio audience: the skill exists as a discoverability anchor. A recruiter looking at `claude-skills/` sees that the `mikko-*` prefix has both a tab-complete-friendly grouping AND a built-in "what's in this namespace" command — that's a tiny but real signal of "the author thought about UX, not just function."

## Freshness check

Staleness checks run by `/mikko-skills-freshness` on any change to this skill — they assert the skill's load-bearing pieces still ship / stay documented. See that skill for the check vocabulary.

```toml
[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "^## Flags"

[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "`--detect`"
```
