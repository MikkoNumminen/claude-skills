---
name: mikko-audit-suite
description: Run every `mikko-*` audit skill that's relevant to the current codebase, in a sensible order, and produce one index document linking to each audit's report. Detects the codebase shape (language, framework, security surface), maps to the suggested audit list (same logic as `/mikko-help --detect`), confirms once with the human, then runs each audit sequentially. Use whenever the user says "run all audits", "full audit", "audit everything", "what's wrong with this codebase", or before a major release. Expensive — total tokens are the sum of every dispatched audit (typically ~100-500K). The orchestrator itself is cheap; the dispatched audits are what cost.
barney: Runs every audit that fits this codebase, then writes one summary doc linking to all the reports. Expensive — confirm before running. Use for milestones, not daily.
---

# mikko-audit-suite

The "do them all" orchestrator. Where `/mikko-help --detect` *suggests* which audits to run, this skill *runs* them — sequentially, with one human confirmation up front, and emits an index document that links to every individual report.

This is the heavier of two patterns floated in [PR #3's review](https://github.com/MikkoNumminen/claude-skills/pull/3). The lighter "/mikko-help --detect" (PR #4) is a hallway sign; this is the tour guide that walks the route.

## When to use

- "/mikko-audit-suite", "run all audits", "full audit", "audit everything"
- Before a major release — one pass that exercises every relevant audit
- After a long pair-programming session that's touched architecture, security, and React layers — the suite cross-cuts all of them
- When you've forgotten what audits exist and just want the right ones run (mikko-help would tell you what to do; this just does it)

## When NOT to use

- **Not** as a daily ritual. Each suite run is expensive (~100-500K tokens depending on how many audits fire). Burn rate compounds. Use individual audits for incremental work; reserve the suite for milestones.
- **Not** during initial code generation. Same reasoning as the underlying audits — chasing your own tail.
- **Not** as a substitute for thinking. The suite tells you which patterns are present; it doesn't tell you which findings are urgent. That's still the human's call.
- **Not** in CI without budgeting. A `mikko-audit-suite` run on a 50K-LOC codebase can use 300K+ tokens. Build economics matter.

## Pre-flight check — IS ANY AUDIT RELEVANT?

Before invoking anything, the suite verifies that **at least one audit's pre-flight will pass**. If the codebase shape doesn't trigger any audit's recommendation, the suite bails with a one-line message rather than running every audit just to have them all report "nothing found."

This is the same decision-matrix logic [`/mikko-help --detect`](../mikko-help/SKILL.md) uses; the table is reproduced below. The matrix is intentionally duplicated rather than imported — if it diverges, both consumers see the same drift signal in their next runs.

### Decision matrix — what triggers each audit

| Detected shape | Audits the suite will invoke (in order) |
| --- | --- |
| React (any flavor) | `react-anti-patterns-audit` → `ai-codegen-smell-audit` → `audit` |
| React Native | `react-anti-patterns-audit --force` → `ai-codegen-smell-audit` → `audit` |
| TypeScript without React | `audit` → `ai-codegen-smell-audit` |
| Python | `audit` → `ai-codegen-smell-audit` |
| Rust / Go | `audit` → `ai-codegen-smell-audit` |
| Plain JS (no TS, no framework) | `audit` → `ai-codegen-smell-audit` |
| Unknown / mixed / no clear signal | `audit` |
| Any of the above + security-sensitive deps detected (`express`, `pg`, `jsonwebtoken`, etc.) | (above list) + `security-audit` appended |

The detector reads up to 5 root config files (`package.json`, `tsconfig.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, framework configs) and counts file-extension density. Does NOT walk the source tree — that's each individual audit's own job.

### Bail conditions

Each abort produces a one-line error message and a clean exit (no index written):

- **No source code detected** (empty directory, docs-only) → `"no source code to audit; the suite has nothing to run."`
- **All recommended audits would be skipped** per the matrix → `"no audits applicable to this codebase shape; the suite has nothing to run."`
- **Required audits not installed** under `~/.claude/skills/mikko-*/` → `"missing audit skill(s): mikko-X, mikko-Y. Install via ./install-mikko.sh from claude-skills first, or pass --partial to run only the audits that ARE installed."` (the `--partial` flag is documented in the "Flags" section below.)

## Procedure

### 1. Pre-flight detection

Same as `/mikko-help --detect`'s detection pass:

- `Read` root `package.json` if present
- `Read` `tsconfig.json` (existence only)
- `Read` `pyproject.toml` / `requirements.txt` / `setup.py` / `Cargo.toml` / `go.mod` if present
- `Glob` `*.{tsx,jsx,py,rs,go,vue,svelte}` for file-extension density

Map detected signals to the recommendation list. If empty, bail per the conditions above.

### 2. Verify audit skills are installed

For each audit in the recommendation list, `Glob` `~/.claude/skills/mikko-<name>/SKILL.md`. If any are missing, print the missing list and either:

- (a) Bail with the missing-skill error message (default behavior)
- (b) Continue with whatever subset IS installed (only if `--partial` was passed)

### 3. Confirm with the human

Skills can't open interactive prompts mid-run. The convention is: **print the plan, end the assistant turn, wait for the user's next chat message.** Parse that next message: if it contains `yes`, `y`, or `confirm` (case-insensitive), the suite proceeds. Anything else (silence, `no`, a follow-up question) aborts cleanly with no audits dispatched.

Estimated token costs are sourced at runtime via this three-step fallback chain:

1. **`docs/SKILLS.md`** in this repo (the per-skill catalog row) — preferred when present, because it's the canonical token-economics source the registry also reads.
2. **Per-skill SKILL.md `## Token expectations` section** — fall back when `docs/SKILLS.md` doesn't have the row (e.g. for a skill not yet added to the catalog) or the file itself isn't found.
3. **`?K (estimate unknown)`** — last-resort placeholder when neither source is parseable. The audit still gets dispatched; the confirmation just can't promise a number. Mark the row in the index later with the same `?K` if no measured number lands.

Mark all numbers clearly as **estimated** — they drift as audits mature, and `/mikko-skill-usage`-measured values supersede them once available:

```
mikko-audit-suite — about to run:

  /mikko-react-anti-patterns-audit  (~?K, estimated at runtime)
  /mikko-ai-codegen-smell-audit     (~?K, estimated at runtime)
  /mikko-audit                       (main + 5 parallel Sonnet sub-agents — ~?K, estimated at runtime)
  /mikko-security-audit              (main + per-phase Sonnet, gated — phases 0+1 only before approval)

estimated total: ~?K tokens, ~30-60min wall-clock (the magnitudes above are illustrative placeholders — the runtime procedure computes the actual per-audit estimates; these literals are not measured. security-audit is phased and pauses for approval; see "phase-gated audits" below.)

reply 'yes' to proceed, anything else aborts.
```

Once confirmed, the suite runs through without further prompts. Individual audits may still have their own gates — see the next section for how the orchestrator handles them.

### Handling phase-gated audits (behavior during step 4)

`security-audit` (and any future skill with its own phase gates) pauses for human approval between phases. **The suite does NOT block indefinitely waiting** — that would be a UX trap (the orchestrator could be blocked for hours / days). Instead:

- When a dispatched audit hits a gate it can't auto-clear, the orchestrator marks that audit's row in the index as `⏸ gated`, writes the **partial** index immediately (covering all already-completed audits), and exits with a one-line note: `security-audit is at its phase gate; partial index written. Resume security-audit independently when you're ready.`
- The human then either runs `/mikko-security-audit` directly to finish the phased run, or re-invokes `/mikko-audit-suite` later — audits whose today-dated report already exists are marked `🔁 reused` and skipped (see step 4's "Idempotent re-runs" paragraph for the lookup logic).
- The index can be updated by hand after the gated audit finishes, or it stays partial — both are acceptable. The suite does not auto-watch for completion.

### 4. Run the audits, in order

For each audit in the list, invoke it by name. The slash-command invocation triggers the skill the same way a direct user invocation would. Wait for each audit's report path to be written before starting the next — sequential, not parallel, because:

- Audits write to the same `docs/audits/` directory; sequential avoids file-write races
- Sequential progress is easier to follow in the chat (the human sees one audit's findings settle before the next starts)
- Parallel sub-agents within each audit (e.g. `audit`'s 5 phase-2 reviewers) still parallelise their internal work

If an audit fails (pre-flight bail, malformed config, crash), log the failure inline and continue with the next audit. The suite produces a partial index. Don't abort the whole suite for one audit's failure.

**Flag pass-through.** The `--source <path>` flag (when present on the suite invocation) is forwarded to each dispatched audit **only if that audit documents support for it**. Today, `react-anti-patterns-audit` is the only audit that explicitly accepts `--source`; the universal audits (`audit`, `ai-codegen-smell-audit`, `security-audit`) don't and would either error or silently ignore the flag. The orchestrator skips the pass-through for audits without documented support. This is a known limitation; standardising `--source` across every audit skill is tracked as portability work for the next audit-skill iteration.

**Idempotent re-runs.** Before invoking each audit, check whether `docs/audits/<canonical-name>-{today}.md` already exists (from a prior partial run today — e.g. after a phase-gate pause, a Ctrl-C, or a transient failure). If so, **don't re-invoke**; mark that audit's row in the index as `🔁 reused`, link to the existing report, and move on to the next audit. This makes the suite safely re-runnable: a human can resume after security-audit's phase gate without paying to re-run the audits that already wrote today's report. The lookup is by report filename, not contents — if the human wants a fresh re-run, delete the existing dated report first (or just wait until tomorrow's `{date}`).

### 5. Write the index

After all audits complete, fail, or hit an unblockable gate, write `docs/audits/audit-suite-YYYY-MM-DD.md` linking to each individual report. **The index is always written, even when every audit failed or got skipped** — the partial index is still useful evidence of what was attempted and which audit's failure mode to investigate next.

**Extracting per-audit findings counts.** Each row's "Findings" column should be a single integer when possible. After each audit completes, the orchestrator `Read`s the first ~20 lines of its report and looks for:

- A `## Summary` table with one column being a `Findings` count (used by `react-anti-patterns-audit`), OR
- A `## Aggregate` / `## Severity rollup` table with severity buckets that sum to the total (used by `audit`), OR
- A `Total: N findings` / `N findings` line near the top.

If none of these are parseable, mark the row's count as `—` (em-dash) and let the linked report itself be the source of truth. The orchestrator never invents a number it can't anchor in the report.

**Status icons in the index** (the "Status" column vocabulary):

| Icon | Status | Meaning |
| --- | --- | --- |
| `✅ ok` | completed | audit finished cleanly; report written; findings count parseable |
| `⏸ gated` | paused | audit started but is waiting on a human approval (e.g. security-audit phase gate); resume independently |
| `❌ failed` | failed | audit crashed mid-run or hit a fatal pre-flight bail; see linked report (if any) for the failure reason |
| `🚫 cancelled` | cancelled | human cancelled mid-run (Ctrl-C / session abort); audits already in-flight may have completed before the cancel signal landed |
| `🔁 reused` | reused | today-dated report already existed; not re-invoked; report link points at the prior run |
| `❓ not installed` | skipped | `--partial` was passed and this audit's `~/.claude/skills/mikko-<name>/SKILL.md` is missing; nothing was run |

Index format:

````markdown
# Audit suite — {YYYY-MM-DD}

**Scope:** {project root or --source path}
**Detected shape:** {one-line detection summary}
**Audits run:** {N of M}

## Reports

| Audit | Status | Report | Findings |
| --- | --- | --- | ---: |
| react-anti-patterns-audit | ✅ ok | [docs/audits/react-anti-patterns-2026-05-20.md](./react-anti-patterns-2026-05-20.md) | 3 |
| ai-codegen-smell-audit | ✅ ok | [docs/audits/ai-smell-2026-05-20.md](./ai-smell-2026-05-20.md) | 7 |
| audit | ✅ ok | [docs/audits/audit-2026-05-20.md](./audit-2026-05-20.md) | 12 (severity-tallied below) |
| security-audit | ⏸ gated | [docs/security/](../security/) | (phase 1 complete, awaiting human approval for phase 2) |

## Severity rollup (from `audit`)

| Severity | Count |
| --- | ---: |
| critical | 0 |
| high | 2 |
| medium | 6 |
| low | 4 |

## What this is and isn't

This index aggregates **report paths and counts** — it doesn't synthesise findings across audits. Each report stands on its own; the suite's value is having them all run in one go, not having them collapsed into one mega-report.

If you want a flat list of every finding across every audit, that's a future `audit-flatten` skill (not currently tracked as an issue — open one when the need is concrete).
````

### 6. Done

Print the index path and a one-line summary:

```
Wrote docs/audits/audit-suite-2026-05-20.md — 4 audits dispatched, 3 completed, 1 gated. Total findings: 22.
```

The human reviews the index and decides which audit's findings to dig into first.

## Flags

- `--partial` — bypass the "all audits must be installed" check. Run only the audits that ARE installed; note any missing ones in the index with a `❓ not installed` status row. Useful when you know some skills aren't installed and don't care.
- `--source <path>` — pass this flag to every dispatched audit **that documents support for it**. Today that's only `react-anti-patterns-audit`; passing `--source` for a suite run that includes other audits will limit React-specific scope but leave the universals running on the full project root. See step 4 ("Flag pass-through") for the rationale.
- `--skip <library-canonical-name>` — exclude a specific audit even if the matrix would recommend it. Use the library-canonical name (`security-audit`, `audit`, `ai-codegen-smell-audit`, `react-anti-patterns-audit`), NOT the prefixed install name. Repeatable: `--skip security-audit --skip ai-codegen-smell-audit`. The orchestrator translates between canonical names (the matrix's vocabulary) and installed names (`~/.claude/skills/mikko-<name>/`) internally.

## Token expectations

The orchestrator itself is cheap (~10K tokens for detection + dispatch + index assembly). The dispatched audits dominate. Rough numbers for the four currently-shipped audits combined:

- `react-anti-patterns-audit`: ~20-25K (when it fires)
- `ai-codegen-smell-audit`: ~10K (single-pass review)
- `audit`: ~25K main + ~80K × 5 parallel Sonnet sub-agents = ~425K full
- `security-audit`: ~5K main + per-phase Sonnet sub-agents, but gated — typically only phase 0+1 run before approval, ~50-100K

Total per suite invocation:

- React stack with security: ~500K-600K tokens
- Plain Python with no React / security: ~100-150K tokens
- Polyglot monorepo: depends on what fires; can exceed 800K

Cadence: 1-2× per month per actively-iterating repo; less often on stable codebases. ~12-24 uses/year.

This is the most expensive skill in the catalog. The pre-flight + confirmation gates are deliberately heavy because the cost matters.

## Failure modes

- **One audit crashes mid-suite.** The suite logs the failure, marks the audit's row in the index as `❌ failed`, and continues with the next. Index is partial; no rerun is triggered automatically.
- **All audits skipped.** If every audit in the matrix says "skip" for this codebase shape, the suite bails before invoking any. No index is written; the user sees the "nothing applicable" message.
- **Security-audit's phase gate.** `security-audit` is multi-phase and waits for human approval between phases. The suite does NOT block indefinitely — when the gate hits, the orchestrator writes the partial index covering everything completed so far, marks `security-audit` as `⏸ gated`, and exits. The human finishes the phased audit independently (run `/mikko-security-audit` directly to resume). See section 3a above for the full rationale.
- **`docs/audits/` doesn't exist.** Each audit creates its own subdirectory if needed; the suite then writes its index to `docs/audits/audit-suite-{date}.md` (creating `docs/audits/` if necessary, `mkdir -p`-equivalent).
- **Cancelled mid-suite.** Behavior here depends on Claude Code's harness, not on the skill itself. If the human Ctrl-Cs (or the session aborts) after the confirmation prompt, in-flight tool calls *may* complete and write their report, or *may* be terminated before doing so — the SKILL.md author can't guarantee either. The suite is honest about this: any audit it has evidence of completing (a report file exists, `Read`-able) appears with its normal status (`✅ ok`, `❌ failed`, etc.); any audit it dispatched but has no evidence completed gets `🚫 cancelled` and a "(report write status unknown)" suffix. Confirm by opening the report path directly to see what landed.

## Limitations

- **No flattening across reports.** The index links to each audit's report but doesn't merge findings into one mega-list. That's a separate concern.
- **Sequential only.** Parallel dispatch would cut wall-clock time but introduces race conditions on shared file output. v1 is sequential; revisit if the wall-clock pain is real.
- **No caching.** If you re-run the suite an hour later on an unchanged codebase, every audit re-runs from scratch. There's no smart "skip the audits whose source files haven't changed" logic. Add if needed.
- **Matrix is duplicated from `/mikko-help --detect`.** If the matrix changes, both `mikko-help` and `mikko-audit-suite` need updating. **Acceptable for two consumers; refactor into `docs/DETECTION.md` (shared doc) the moment a third consumer adopts it** — the cost of the duplication grows linearly with consumer count, the cost of the refactor doesn't, so the break-even is at consumer #3. Tracked here so the next person porting the matrix knows to do the extract instead of triple-duplicating.

## What this skill does NOT do

- **Does not modify code.** Like the underlying audits, the suite is read-only. The reports it produces are markdown for human review.
- **Does not aggregate findings.** Each report is independent; the index is a table of contents, not a synthesis.
- **Does not learn from history.** Each run reads the codebase fresh; no caching of prior audit outputs.
- **Does not measure quality of fixes.** Re-running the suite after fixing findings shows fewer hits; the suite doesn't track delta or congratulate you.

## Why this skill exists

Three reasons:

1. **Discoverability without dispatch overhead.** Before this skill, "run every relevant audit" meant six manual slash-commands and remembering the order. The suite collapses that to one.
2. **The pre-flight is the right pattern.** Each audit has its own pre-flight; the suite's pre-flight is "is any audit relevant at all?" — the same pattern, one level up.
3. **Portfolio-grade evidence.** A clean `audit-suite-YYYY-MM-DD.md` showing "4 audits, 22 findings, severity-tallied" is the receipt a recruiter (or future-you) can point at when asked "what's your code-quality discipline?" The audits already produced reports; the suite makes them visible as a coordinated artifact rather than scattered docs.

## What's verifiable vs editorial

| Claim | Source of truth | Verifiable? |
| --- | --- | --- |
| Codebase shape detected correctly | Root config files + file extensions | ✅ Yes (the pre-flight) |
| Each audit's findings | The audit's own report | ✅ Yes (every finding cites file:line) |
| Total token cost of the suite run | Sum of each audit's estimate | 🟡 Approximate (`/mikko-skill-usage` would replace with measured) |
| The matrix is the right matrix | Editorial — Mikko's preferences | 🔴 Editorial |
| Which audits the recruiter would care about | Out of scope; the suite runs them all | — |

The suite's primary claim is mechanical: "I ran these audits in this order and they wrote these reports." That's auditable from the index file alone. The harder claim — "these are the right audits to run on this codebase" — is the matrix's job, and the matrix is editorial. The honesty is naming that clearly rather than dressing it up as automatic.

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
pattern = "--partial"
```
