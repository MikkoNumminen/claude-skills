---
name: skill-calibration
description: A/B-test a Claude Code skill against an unstructured baseline to measure the actual token savings it provides. Runs one Sonnet sub-agent per arm per skill — arm A solves the task cold without reading SKILL.md, arm B reads SKILL.md and follows the procedure exactly. Both arms operate in fresh sandboxed worktrees so they don't collide. Token usage comes from the harness's per-sub-agent `usage.total_tokens` (same accounting convention as `/mikko-skill-usage`). Can measure a single skill, several specific skills, or every skill in a repo in one parallel batch. Emits a JSON measurement file plus a markdown report plus a portrait-A4 PDF. Replaces the editorial "saved" guesses in skills-registry PDFs with real numbers. Use whenever the user says "calibrate this skill", "measure tokens saved", "A/B-test the skill", "how much does X actually save", or before any public claim about a skill's savings.
barney: A/B-tests a skill (or many concurrently) — solves the same task twice, once cold and once with the skill, then reports who used more tokens. Real measurement, not the 3× heuristic.
---

# Skill calibration

The portfolio's skills-registry PDF models token savings as ~2× cost-per-use × annual uses (i.e. assumes the no-skill alternative would cost 3× a focused skill run). That 3× is a guess. This skill replaces the guess with measurement.

For each skill in scope, the runner gives two parallel Sonnet sub-agents the same task — one cold, one following the SKILL.md — in isolated worktrees, then aggregates the harness's per-sub-agent token usage (mechanics in the Procedure below).

A May-2026 calibration of all 13 Spacepotatis skills measured a **~22% net savings rate**, vs the ~67% the heuristic implies. Two of 13 skills cost MORE per use (security-audit, equipment — both encode rigor rather than scout-savings). That run is the reference implementation this skill formalizes.

## When to invoke

- "/mikko-skill-calibration <skill>" — calibrate one skill
- "/mikko-skill-calibration --repo <name>" — every non-redirect skill in one repo
- "/mikko-skill-calibration --skills foo,bar,baz" — explicit list
- "calibrate the new-mission skill" / "A/B-test equipment" / "measure how much save-roundtrip-audit saves"
- Before any public claim about token savings on a specific skill
- Quarterly drift-check: the heuristic-vs-measured gap closes over time as skills mature, so re-calibrate at intervals

## When NOT to invoke

- **Not for tight feedback loops.** A single A/B costs ~150K tokens; batch of 13 cost ~2M. One-shot calibration, not a routine check.
- **Not for measuring orchestrator skills that need user gates.** Skills that explicitly STOP at gates (multi-phase audits, security-audit, modular-architecture-audit) can only be measured for Phase 1; downstream phases need human-in-the-loop approval that a sub-agent can't satisfy.
- **Not for skills whose tasks aren't self-bounded.** "Audit everything for X" works because the scope is the codebase; "fix the bug in PR #143" doesn't, because the answer depends on the PR's actual content. If the task isn't reproducible from the SKILL.md, this skill can't honestly calibrate it.
- **Not for benchmarking.** N = 1 per skill — trust direction + rough magnitude, not the absolute number (see Limitations).

## Procedure

The work is mostly sub-agent dispatch (main-thread) plus output file writes. No companion script — the skill body IS the procedure.

### 1. Resolve scope

Parse args. The full surface, in one place:

**Scope flags (pick one — they're mutually exclusive):**

| Flag | Effect |
| --- | --- |
| `--skill <name>` (or `<name>` as first positional) | Single skill. |
| `--skills foo,bar,baz` | Explicit comma-separated list. |
| `--repo <name>` | Every non-redirect skill in one repo (consumer-layout or library-layout, auto-detected). |
| `--portfolio` | Every non-redirect skill across `D:/koodaamista/*/.claude/skills/*/SKILL.md` (every consumer repo) + `D:/koodaamista/claude-skills/skills/*/SKILL.md` (the library). Heaviest mode — multiplies sub-agent count by repo-count. Confirm with the user once before dispatching; this routinely costs 3–10M tokens. |

**Task flags (optional):**

| Flag | Effect |
| --- | --- |
| `--task <text>` | Override the auto-synthesized task for a single-skill run. Has no effect on multi-skill modes. |
| `--tasks-file <path>` | JSON `{ "skill-name": "task description" }`. Skills whose names aren't in the file fall back to auto-synthesis. |

**Output flags (optional):**

| Flag | Effect |
| --- | --- |
| `--output-dir <path>` | Where the JSON, MD, PDF land. Default: `<cwd>/.claude/agent-verdicts/` (for JSON) + `<cwd>/docs/audits/` (for MD/PDF). |
| `--no-pdf` | Skip step 8. |
| `--no-registry-update` | Skip the step-9 prompt (always skip the registry-overrides write). |
| `--keep-worktrees` | Skip the step-10 cleanup prompt (leave the worktrees in place). |

**Scope resolution rules**

For `--repo`, resolve the repo path by trying:
1. `D:/koodaamista/<name>/.claude/skills/*/SKILL.md` (consumer layout)
2. `D:/koodaamista/<name>/skills/*/SKILL.md` (library layout)
3. Bail if neither matches.

For `--portfolio`, enumerate both globs above with `*` in the repo position and dedupe by `(repo, skill-name)`. Library skills installed into consumer repos via the `mikko-` prefix get merged into their canonical library row (same rule `apply-measurement-overlay.mjs` uses in the mikkonumminen.dev repo).

Skip skills whose YAML frontmatter `description` is a redirect stub (matches the same heuristic `/skill-registry` uses: contains "superseded" / "redirect" / "renamed" / "moved to" / "see also").

### 1.5 Confirm scope before a large run

With scope resolved and N known — and **before** generating tasks or creating worktrees (steps 2–3) — if the run resolves to **more than 6 skills** (more than ~12 sub-agents, since each skill is two arms), STOP and confirm with the user first, the same gate `--portfolio` already carries. Print the resolved skill list and the cost estimate, then wait:

```
about to calibrate N skills = 2×N sub-agents, ~140K × N ≈ <total> tokens.
reply 'yes' to proceed.
```

A single `--repo <name>` on a 14-skill repo is 28 sub-agents (~2M tokens) — large enough that it must never fire silently. `--skills foo,bar,baz` with ≤6 skills runs without a gate. Gating here, not at dispatch, means a "no" doesn't leave 2N worktrees to clean up.

### 2. Generate a calibration task per skill

For each in-scope skill, write a representative task description. This is the prompt both arms receive verbatim. The task must be:

- Small enough to fit in one sub-agent run (~5 minutes of tool use)
- Self-bounded (everything needed is in the repo or the prompt; no external lookups)
- Representative of what the skill exists to do (not a corner case)

Default source: the skill's `## When to use` examples plus the SKILL.md description's example invocations. When the user passes a task override (see `--task` / `--tasks-file` in step 1's args table), that takes precedence — useful for re-running a calibration with identical prompts. When in doubt about task shape, mirror the May-2026 Spacepotatis calibration — [the report on GitHub](https://github.com/MikkoNumminen/mikkonumminen.dev/blob/master/docs/audits/spacepotatis-skills-calibration-2026-05-22.md) carries 13 worked examples and is fetchable on demand if you don't have a `mikkonumminen.dev` checkout locally.

### 3. Set up worktrees

For each in-scope skill, create TWO worktrees in the target repo:

- `<target-repo>/.claude/worktrees/calib-A-<skill>/` branched from master/main
- `<target-repo>/.claude/worktrees/calib-B-<skill>/` branched from master/main

Branch name pattern: `calib/<skill>-A` and `calib/<skill>-B`. Both branches throwaway — they only exist to give git worktree something to point at.

If a worktree already exists at that path (from a prior calibration), bail and ask the user to clean up first. Do not silently overwrite.

### 4. Dispatch sub-agents in parallel

In a single batch (one message), dispatch 2 × N Sonnet sub-agents — one per arm per skill. Use `subagent_type: "general-purpose"`, `model: "sonnet"`, `run_in_background: true` so the main thread isn't blocked.

**Arm A prompt template** (substitute `<WORKTREE>`, `<TASK>`):

```
You're the BASELINE arm of a skill-calibration A/B test. No skill awareness — solve the task cold.

**Worktree:** <WORKTREE>
**Repo:** <REPO> (one-line description of the repo's purpose).

**Task:** <TASK>

**Constraints:**
- DO NOT read `.claude/skills/` or any `SKILL.md`. You're the no-skill arm.
- Scout the codebase, find similar existing code, mirror its structure.
- Actually write all the required files (Edit/Write tools).
- DO NOT commit. DO NOT push.
- Final message: ONE LINE listing files created/modified. No prose.
```

**Arm B prompt template** (substitute `<WORKTREE>`, `<TASK>`, `<SKILL>`):

```
You're the SKILL arm of a skill-calibration A/B test. Follow the skill exactly.

**Worktree:** <WORKTREE>
**Repo:** <REPO>.

**Task:** <TASK>

**Constraints:**
- Read `<WORKTREE>/.claude/skills/<SKILL>/SKILL.md` first. Follow its procedure exactly.
- Actually write all the files the skill prescribes.
- DO NOT commit. DO NOT push.
- Final message: ONE LINE listing files created/modified. No prose.
```

For library-layout repos (`claude-skills`), substitute `skills/<SKILL>/SKILL.md` instead of `.claude/skills/<SKILL>/SKILL.md`.

The harness queues `run_in_background: true` sub-agents — depending on its concurrency limit, all 2N may not run truly concurrently, but they will all complete without blocking the main thread.

### 5. Capture token usage

Each sub-agent's task-notification payload includes `usage.total_tokens`. Record those. Per skill: `arm_A_tokens` and `arm_B_tokens`. Derived: `saved = arm_A_tokens − arm_B_tokens` and `pct_saved = round(saved / arm_A_tokens × 100)`.

A negative `saved` means the skill cost more than the baseline — that's a real measurement, not a bug. Skills that encode RIGOR (full-CRUD scaffolding, multi-phase audits with prescribed surface-walks) commonly produce negative or near-zero savings; their value is completeness, not compression.

Also record any anomalies surfaced by the sub-agent in its final message:
- "blocked by classifier" → record `partial: true`
- "wrote outside the worktree" → record `wrote_outside_wt: true`
- explicit refusal / abort → record the reason verbatim

### 6. Persist measurements

Write a dated JSON file at:

```
<cwd>/.claude/agent-verdicts/SKILL-CALIBRATION-<YYYY-MM-DD>.json
```

Schema:

```ts
{
  generated_at: string,       // ISO 8601 UTC
  target_repo: string,        // e.g. "Spacepotatis"
  base_commit: string,        // the SHA both worktrees branched from
  skills: [{
    name: string,
    task: string,             // the calibration prompt both arms received
    arm_A_tokens: number,
    arm_B_tokens: number,
    saved: number,            // = A - B (may be negative)
    pct_saved: number,        // = round(saved / A * 100)
    partial?: true,           // arm-B blocked mid-work
    wrote_outside_wt?: true,  // arm-B mis-routed file writes
    notes?: string            // free-form per-skill anomaly notes
  }],
  aggregate: {
    arm_A_total: number,
    arm_B_total: number,
    saved_total: number,
    pct_saved: number,        // net rate across all skills
    skills_measured: number,
    skills_saving: number,    // count where saved > 0
    skills_costing: number    // count where saved < 0
  }
}
```

This JSON is the source of truth. The MD and PDF are derived from it.

### 7. Render the markdown report

Write a markdown report to:

```
<cwd>/docs/audits/skill-calibration-<YYYY-MM-DD>.md
```

Use the May-2026 Spacepotatis calibration report as the template — [view it on GitHub](https://github.com/MikkoNumminen/mikkonumminen.dev/blob/master/docs/audits/spacepotatis-skills-calibration-2026-05-22.md). Required sections:

- tl;dr with aggregate numbers
- Methodology (3-4 short paragraphs: arms, worktrees, accounting, N=1)
- Per-skill table (sorted by arm-A tokens descending, so the heaviest tasks lead)
- "What the data shows" — group skills into buckets (scout-savers, rigor-encoders, thin-gain, quality-trade-off-flags)
- Implications for the registry PDF (three options: lower multiplier / per-skill overrides / drop the savings column)
- Honest caveats (N=1, sub-agent ≠ main-thread, outcome equivalence, anomalies)
- Experiment cost in tokens

Voice rules from the Spacepotatis report apply: name the limitation in the same sentence as the number; no defensive hedging; if a row had an anomaly, surface it inline, not as a footnote.

### 8. Render the PDF

Render a concise companion PDF via the `md-to-pdf` skill (or directly via `scripts/build-pdf.mjs` if the cwd repo has it; mikkonumminen.dev does, the library doesn't).

Portrait A4, ~2 pages, one-sentence subhead under the title, methodology in 3 paragraphs, results table, 4-paragraph interpretation, "What to do with this" section with the three options summarized.

Output:

```
<cwd>/docs/audits/skill-calibration-<YYYY-MM-DD>.pdf
```

If neither `md-to-pdf` nor `build-pdf.mjs` is available in the cwd, skip the PDF step with a one-line note and proceed.

### 9. Offer to feed measurements into the registry data

OPTIONAL — ask the user once before doing this. If yes:

For each measured skill, write `tokens_saved_per_use: <measured-saved-per-use>` into the matching receipt in `<cwd>/public/data/skills-registry.json`. The `apply-measurement-overlay.mjs` script in mikkonumminen.dev preserves this field through future overlay runs, so the registry PDF picks up the measured savings on its next build.

This only applies when the cwd is mikkonumminen.dev (or a fork with the same `public/data/skills-registry.json` layout). For other cwds, skip and tell the user where the measurements would be applied.

After the write, suggest `/skill-localUpdate` to regenerate the registry PDF with the measured numbers. Do NOT auto-run it.

### 10. Offer to clean up worktrees

ASK BEFORE DELETING. Cleanup means:

```
git -C <target-repo> worktree remove .claude/worktrees/calib-A-<skill> --force
git -C <target-repo> worktree remove .claude/worktrees/calib-B-<skill> --force
git -C <target-repo> branch -D calib/<skill>-A calib/<skill>-B
```

The `--force` is needed because the worktrees have uncommitted changes (the work products of the A/B run). Both `--force` and `branch -D` are destructive; explicit user confirmation required.

If the user declines, leave them in place and report the paths so they can be inspected.

### 11. Done

Report the file paths and a one-line summary:

```
Calibrated N skills. Aggregate: A=<arm_A_total> → B=<arm_B_total>, saved <saved_total> (~<pct>%).
M of N saved tokens. <count_costing> cost more per use.
Report: <md path>
PDF:    <pdf path>
Data:   <json path>
```

## Token expectations

Per-skill A/B: typically 100K–200K tokens (50K–100K per arm, depending on task complexity). The May-2026 Spacepotatis pass measured an average of 70K per arm-A and 67K per arm-B across 13 skills (~140K per A/B pair).

For N skills: ~140K × N tokens for the sub-agent dispatches, plus ~30K main-thread orchestration (synthesizing tasks, aggregating results, writing the report). The PDF render is pure Node (Chrome's --print-to-pdf), zero model tokens.

Wall-clock: ~5-10 minutes for the parallel sub-agent dispatch (limited by the slowest agent), plus ~30s for the report + PDF render.

Cadence: per-skill ad-hoc when a skill matures enough to be measured. Per-repo or portfolio-wide rarely (it's expensive).

## Failure modes

- **Sub-agent gets blocked by the auto-mode classifier mid-work.** The token count up to the block is still real, but the work isn't complete. Recorded as `partial: true` in the JSON; the row is footnoted in the report but the number is still presented.
- **Sub-agent writes outside its worktree.** The harness sometimes routes file writes to a parent directory if the agent constructs a relative path against the wrong base. Token count is valid; the stray file needs manual cleanup. Recorded as `wrote_outside_wt: true`.
- **The task isn't reproducible.** Some skills' "task" depends on context that's not in the SKILL.md (e.g., "fix bug X"). Calibrating these requires explicit `--task` overrides; without them, the auto-synthesized task may produce arms that are doing different work, which makes the comparison meaningless. Surface a warning when the synthesized task references symbols not found in the repo.
- **Worktree creation fails.** Usually because a prior calibration left the worktree behind. Bail with the offending path and ask the user to clean up first.
- **Sub-agent dispatch concurrency limit.** The harness queues sub-agents above its concurrency cap. The skill still works — wall-clock just stretches. Recorded in the report's "Experiment cost" section.

## Limitations

- **N = 1 per skill.** Single data point. A re-run produces a different absolute number for both arms. Trust direction + magnitude, not precision.
- **Sub-agent execution is not identical to main-thread execution.** Sub-agents have their own context-loading characteristics. The numbers are roughly representative of what a user would experience invoking the skill in a fresh session, but not exactly so.
- **Outcome equivalence not verified.** Both arms produce "something" but this skill doesn't check that the two outputs solve the same problem at the same quality level. Token savings can hide a quality regression (the May-2026 ai-codegen-smell-audit pass saved 48% in arm B but found 1 finding vs arm A's 11 — the savings partly reflected stricter discrimination).
- **Selection bias on tasks.** Auto-synthesized tasks lean toward what the SKILL.md highlights as common use; rare edge-case invocations aren't measured. Override via `--tasks-file` if you want a specific shape.
- **Outcome quality.** Same caveat as `/mikko-skill-usage` and `/mikko-session-cost`: this counts tokens, not value. A 200K-token sub-agent that produced exactly the right answer counts the same as a 200K-token sub-agent that produced garbage.
- **No counterfactual at the SKILL.md level.** This skill measures "did the procedure save tokens vs cold scout". It doesn't measure "is the procedure WELL-DESIGNED" — a sloppy SKILL.md that gives bad guidance will still drive a sub-agent through a procedure, possibly cheaper than scouting cold, without that meaning the skill is good.

## Freshness check

Staleness checks run by `/mikko-skills-freshness` on any change to this skill — they assert the skill's load-bearing pieces still ship / stay documented. See that skill for the check vocabulary.

```toml
[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "--portfolio"

[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "arm B"
```
