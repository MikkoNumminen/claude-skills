# claude-skills

> A library of reusable [Claude Code](https://www.anthropic.com/claude-code) skills — small markdown files that teach Claude how to do specific jobs across any codebase. Drop a skill into a Claude Code skills directory, and from then on the recipe is part of Claude's vocabulary.

This repo started life as `claude-audit-skill` housing a single audit skill. It now hosts a small family of skills — read-only audits, a handful of cross-cutting measurement / freshness tools, and a few personal-namespace helpers.

## What's in here

| Skill                                                                       | What it does                                                                                                                                                                                                                                  | Status    |
| --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| [`audit`](skills/audit/SKILL.md)                                            | Multi-phase robustness audit. Five parallel sub-agents review the codebase across resource lifecycle, data integrity, concurrency, error paths, and external boundaries. Produces `docs/audits/audit-YYYY-MM-DD.md` with severity-ranked bugs. | shipped   |
| [`ai-codegen-smell-audit`](skills/ai-codegen-smell-audit/SKILL.md)          | Read-only audit for ten specific failure modes that LLM-generated code produces at higher rates than careful human authors (defensive guards on impossible cases, swallowed errors, single-use helpers, mirror tests, generic names in domain code, etc). Each check has a concrete smell example and a concrete legitimate counter-example so the auditor can tell signal from noise. Universal across codebases. | shipped   |
| [`react-anti-patterns-audit`](skills/react-anti-patterns-audit/SKILL.md)    | Read-only audit for six concrete React anti-patterns (key=index in lists, useEffect for derived state, dep-array lies, state mutation instead of replace, missing effect cleanup, multiple sources of truth). Each check has a smell example and a legitimate counter-example. Runs a pre-flight fit check first and aborts cleanly if the codebase isn't React. | shipped   |
| [`security-audit`](skills/security-audit/SKILL.md)                          | Multi-phase security audit + remediation. Attack-surface mapping → prioritized remediation plan → fixed one finding at a time with regression tests → AI-first security docs (SECURITY.md, threat model, lint rules). Each phase produces an artifact under `docs/security/` and STOPS at a gate for user approval. Critical findings surface immediately. | shipped   |
| [`readme-drift-sync`](skills/readme-drift-sync/SKILL.md)                    | Detects drift between what the repo actually contains and what `README.md` claims (file structure, dependencies, skills, features, status), then rewrites only the drifted sections in the README's existing voice. **Write-with-approval**: emits a working-tree edit to `README.md` plus a drift report under `docs/audits/`, then STOPS. Does NOT commit or push. Voice-preserving — extracts a voice profile first and refuses to rewrite sections it can't match. | shipped   |
| [`skill-usage`](skills/skill-usage/SKILL.md)                                | Measure actual Claude Code skill usage from local transcript JSONL files. Counts invocations and sums tokens per skill across all sessions in `~/.claude/projects/`. Emits a dated JSON that the portfolio's `/skill-registry` consumes as a receipt source. | shipped   |
| [`session-cost`](skills/session-cost/SKILL.md)                              | Measure the token cost of one Claude Code session — main thread plus every sub-agent it dispatched. Same accounting convention as `skill-usage` (input + output + cache-creation; cache-read excluded; deduped by `requestId`), different slice: by who-spent-it within one conversation, instead of by skill name across the portfolio. Use it to retro a PR or a complex feature. Pure JSONL parser, zero model-token cost. | shipped   |
| [`skill-calibration`](skills/skill-calibration/SKILL.md)                    | A/B-test a skill against an unstructured baseline to measure actual token savings. Dispatches two Sonnet sub-agents per skill in sandboxed worktrees — arm A solves the task cold without reading SKILL.md, arm B follows the skill. Token counts come from the harness's per-sub-agent `usage.total_tokens` (same convention as `skill-usage`). Handles one skill or a whole repo in parallel. Emits a dated JSON + markdown report + portrait-A4 PDF. Reference implementation: May-2026 Spacepotatis calibration of 13 skills measured ~22% net savings vs the 67% the heuristic implies. | shipped   |
| [`skills-freshness`](skills/skills-freshness/SKILL.md)                      | sha256-based staleness audit for installed skills, project + global scopes. Only new / changed / removed skills are surfaced; unchanged skills never enter LLM context. Skills can opt in to declared TOML checks under `# Freshness check`; otherwise the LLM does a generic frontmatter + description + broken-ref pass. Pure stdlib, stdlib-only tests. | shipped   |
| [`mikko-help`](skills/mikko-help/SKILL.md)                                  | Personal helper: lists every installed `mikko-*` skill with its one-line description, and flags new skills in the source repo that haven't been installed yet. Solves "I know I have a skill for this but can't remember which one." Useful as-is for anyone adopting the `mikko-` namespace; fork-friendly otherwise (search-and-replace the prefix to brand for yourself). | shipped   |
| [`mikko-install`](skills/mikko-install/SKILL.md)                            | Personal installer: wraps `install-mikko.sh` and `install.sh` behind a slash command so the install loop is reachable from inside any Claude Code session. Install all, install one, update after `git pull`, list what's new, or uninstall — without leaving the chat to find the repo and run bash. Bootstraps via `install-mikko.sh` once at machine setup, then steady-state from there. | shipped   |
| [`mikko-audit-suite`](skills/mikko-audit-suite/SKILL.md)                    | Personal orchestrator: detects the codebase shape (language, framework, security surface) and runs every relevant `mikko-*` audit skill in a sensible order, producing one index document that links to each audit's report. Confirms once with the human before dispatching. Expensive (sum of every dispatched audit, typically 100–500K tokens) — invoke before milestones, not daily. | shipped   |
| _planned: more audit variants (save-roundtrip-shape genericizer, copyright-scan generic version)_ | port from the consumer repos where they currently live, after a genericization pass to strip repo-specific data-shape knowledge.                                                                                                              | upcoming  |

Each skill has its own SKILL.md with the full recipe — when to invoke, what it reads, what it writes, what it explicitly refuses to do. Read the SKILL.md to learn what a skill does; read [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the `audit` skill's design rationale specifically.

## What a "skill" is

If you've used [Claude Code](https://www.anthropic.com/claude-code) you already know. If not: Claude Code is a command-line assistant that can read and edit your code. A *skill* is a markdown file under `.claude/skills/<name>/SKILL.md` that teaches Claude Code how to do one specific job — like a recipe card. When you describe the job, Claude recognises the recipe and follows it.

This library is a collection of recipes you can install into any project.

## Install

Two installers, for two different intents:

### `install.sh` — one skill at a time, original name, symlinked

Best when you want a specific skill in a specific project, and you'd like `git pull` updates here to propagate automatically.

```bash
# install one skill into your user-wide Claude Code config
# (available in every project on your machine)
./install.sh audit --target user
./install.sh skill-usage --target user

# install one skill into a specific project repo
./install.sh audit --target project --repo /path/to/your/repo

# list available skills
./install.sh --list
```

After install, the skill is available as `/audit` (or `/skill-usage`, etc.) inside any Claude Code session whose project sees that skills directory. The script is idempotent — re-running just updates the symlink. It refuses to overwrite a non-symlink directory.

### `install-mikko.sh` — every skill at once, namespaced under a prefix, copied

Best when you want the whole library grouped under one slash-tab namespace (`/mikko<Tab>` for me; replace with your own).

```bash
# install every skill under ~/.claude/skills/mikko-<name>/  (the default)
./install-mikko.sh

# use a different prefix for someone else's namespace
./install-mikko.sh --prefix bobs-

# preview without writing
./install-mikko.sh --dry-run
```

Each library skill is **copied** (not symlinked) to `~/.claude/skills/<prefix><skill-name>/`, and the `SKILL.md` frontmatter's `name:` field is rewritten in the copy so Claude Code's skill listing matches the directory name. Skills already starting with the prefix (e.g. `mikko-help`) aren't double-prefixed. Re-running replaces the prior copies cleanly.

After this, typing `/mikko<Tab>` (or `/bobs<Tab>`) from any Claude Code prompt lists just your namespace's skills — handy when you've installed enough that the unprefixed `/` + Tab menu mixes them with built-ins.

Trade-off vs `install.sh`: copies don't auto-update with `git pull` here. To refresh, re-run `install-mikko.sh` (it's idempotent).

## Why split skills across multiple repos?

Three audiences:

1. **Me (Mikko)** — I want to maintain one canonical version of each audit skill rather than copy-pasted forks in every consumer repo. Symlinks let me edit once, propagate everywhere.
2. **My portfolio (`mikkonumminen.dev`)** — the site's contact-page terminal renders a registry of all my skills. The registry skill walks consumer repos for installed copies; this library is the source of truth they install from.
3. **Anyone else** — clone, run `./install.sh <name> --target user`, and you have the skill. No npm, no global state, no surprises.

The trade-off vs vendoring (copy-into-each-repo) is that consumer repos depend on this one being checked out somewhere. That's acceptable for a personal toolbox; less so if you're shipping skills as a published artifact. If you want copies instead of symlinks, replace `ln -s` with `cp -R` in `install.sh` — the rest of the structure stays the same.

## Frontmatter convention: `name`, `description`, `barney`

Each SKILL.md's YAML frontmatter carries three fields:

- **`name`** — the slash-command identifier (e.g. `audit`, `react-anti-patterns-audit`). This is what Claude Code's harness matches against; `install-mikko.sh` rewrites it to the prefixed name in the consumer-side copy (`mikko-audit`, etc.).
- **`description`** — the contract: when to invoke, what gets read/written, trigger phrases, scope boundaries. Optimised for Claude Code's skill-matching layer, which compares natural-language requests against this field. Long, precise, full of "when X / not when Y" disambiguation. Reads like a contract.
- **`barney`** — *(optional)* a plain-English one-or-two-line description of what the skill does in everyday terms. Reads like a tour. Used by `/mikko-help --barney` for friendly listings. Skills without `barney` fall back to the truncated `description` in barney mode; the gap is surfaced with a `(no barney)` annotation, nudging authors to add the field.

Both `description` and `barney` are author-written and editorial — the `description` is optimised for accurate slash-command matching, the `barney` is optimised for human scannability. Keep them aligned but not identical: when the precise contract reads stiffly, the barney line is where you say it like a person would.

**Length guideline for `barney`:** target around 140 characters so the table layout in `/mikko-help --barney` stays clean on a typical terminal width. Longer lines are fine in the SKILL.md itself; `mikko-help` truncates with an ellipsis when rendering the table. For comparison, the longest barney line in this library today is ~190 chars (security-audit) — readable in full when wrapped, but cropped in the listing.

**Authoring guideline — when to write a `barney`:** Add one if the `description` is longer than ~3 sentences or reads as a contract rather than a tour. Short, friendly descriptions don't need a separate human-friendly version — a single field carrying both jobs is fine when it can manage that. Most skills with long descriptions (audits, orchestrators, anything contract-heavy like `mikko-help` itself) benefit from both fields.

## What's verifiable vs editorial

The audit skill produces real outputs (markdown reports, GitHub PRs) against real codebases. Its claims (severity counts, missed-pattern lists) are auditable from the resulting report. The `skill-usage` skill measures actual transcript data from Claude Code's local JSONL files — no synthetic estimates, no extrapolation. The `skills-freshness` skill computes sha256 over installed skill directories — the manifest is reproducible from the same inputs on the same machine; mismatch is signal.

What's **not** in this repo: a marketplace, a registry, or any kind of "ratings" claim. It's a small personal toolbox surfaced publicly because the recipes are reusable.

## Repo layout

```
.
├── README.md                      this file
├── LICENSE                        MIT
├── install.sh                     symlink installer for ONE skill at a time, original name
├── install-mikko.sh               copy-installer for ALL skills under a chosen prefix
├── docs/
│   ├── METHODOLOGY.md             the audit skill's design rationale
│   └── SKILLS.md                  per-skill token-economics catalog
└── skills/
    ├── audit/
    │   ├── SKILL.md               the meta-architecture audit recipe
    │   └── evals/                 sample inputs and gold outputs
    ├── ai-codegen-smell-audit/
    │   ├── SKILL.md               ten LLM-codegen patterns and their counter-examples
    │   └── evals/                 sample inputs and gold outputs
    ├── security-audit/
    │   └── SKILL.md               multi-phase security audit + remediation, gated per phase
    ├── skill-usage/
    │   ├── SKILL.md               the measurement recipe
    │   └── scan.mjs               companion script: scans ~/.claude/projects/*.jsonl
    ├── skills-freshness/
    │   ├── SKILL.md               sha256-based staleness audit
    │   ├── skills-freshness.py    companion script: change-detection + check runner
    │   └── tests/                 stdlib-only unittest suite
    └── mikko-help/
        └── SKILL.md               personal-namespace discoverability helper
```

## License

[MIT](LICENSE). Skills are markdown files; use them however you like.
