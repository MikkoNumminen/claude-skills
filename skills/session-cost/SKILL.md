---
name: session-cost
description: Measure the token cost of one Claude Code session — main thread plus every sub-agent it dispatched. Slices a single session BY WHO-SPENT-IT; companion to `/mikko-skill-usage`, which slices the whole portfolio BY SKILL. Use for "what did this conversation cost so far?", "how much did that feature take?", or "which sub-agent was most expensive?". Reads the local `~/.claude/projects/<dir>/<session>.jsonl` transcripts and their `subagents/agent-*.jsonl` sidechains.
barney: Counts what one Claude Code conversation cost in tokens — main thread plus every sub-agent it spawned. Pair with /mikko-skill-usage when you want both axes.
---

# Session cost

Token-accounting for one Claude Code session. Walks the session's main JSONL plus every sub-agent JSONL the harness dropped under `<session>/subagents/`, sums the per-message `usage` numbers with the same convention `mikko-skill-usage` uses (input + output + cache-creation; cache-read excluded), dedupes by `requestId`, and prints either a JSON report or a human summary.

The slice is different from `mikko-skill-usage`:

| Skill | Slices by | Window | Output |
| --- | --- | --- | --- |
| `mikko-skill-usage` | Skill name (one row per skill) | Last N days across the whole portfolio | Aggregate per-skill cost / cadence |
| `session-cost` | Who spent it (main thread + per sub-agent) | One single session | What that one session cost end-to-end |

Use this when you want to retro a PR or a complex feature: "I spent this morning on the X task — what did it cost? Which sub-agent dispatch ate the most?"

## When to use

- "What did this conversation cost so far?"
- "How much did running that complex feature take?"
- "Which of my parallel sub-agents was the most expensive?"
- "Compare the cost of two PRs I just shipped"
- Cost retro on a multi-hour pairing session

NOT for:

- **Real-time monitoring.** The JSONL is flushed at message end, sometimes later. Run the skill after a noticeable pause for accurate-feeling numbers.
- **Cross-session aggregates.** That's `mikko-skill-usage`.
- **Pricing dollars.** This counts tokens. Multiply by the model's per-token rate yourself if you want a dollar figure.

## Procedure

### 1. Run the scanner

From inside any repo that has a Claude Code session history. The installer prefixes the skill name with `mikko-`, so the slash command is `/mikko-session-cost` and the installed scanner path is `~/.claude/skills/mikko-session-cost/scan.mjs`. To call it directly from the library checkout instead, use the library-relative path:

```bash
node skills/session-cost/scan.mjs
```

Args:

- `--session <id>` — explicit session ID (UUID-shaped, the bit before `.jsonl` in the transcript filename). Default: most-recently-modified session in the cwd-mapped project directory.
- `--project-dir <path>` — override the auto-resolved `~/.claude/projects/<cwd-encoded>/` path. Useful when you're measuring a session from a different repo than the one your cwd is in.
- `--projects-dir <path>` — override the default `~/.claude/projects/` root (useful for testing against a captured sample).
- `--format json` — emit the full structured report instead of the human summary. Pipe into `jq` for further slicing.

The default project-dir resolution maps the current cwd to its harness-encoded directory under `~/.claude/projects/`. If the auto-resolve misses (it's lenient but not perfect on Windows path edge cases), pass `--project-dir` explicitly.

### 2. Read the summary

The human summary has three sections:

```
=== Session 47fcb7d8… ===
Project: C:/Users/.../d--koodaamista-mikkonumminen-dev

Main thread:  830,258 tokens (157 assistant messages; 25,636,161 served from cache)
  input:        331
  output:       142,769
  cache create: 687,158

Sub-agents:   352,937 tokens (13 agents, 56 assistant messages; 888,273 served from cache)
  input:        82
  output:       23,367
  cache create: 329,488

TOTAL counted: 1,183,195 tokens

=== Per sub-agent (sorted by cost) ===
ae0ad8e7dd4e  total=  41,897  msgs=  2  — Layout / arm's-length test
a20c28dc91d7  total=  38,620  msgs=  7  — Skill registry: AudiobookMaker
... etc
```

The "served from cache" number is informational — it's not counted, but a huge gap between "cache create" and "served from cache" tells you the session leaned heavily on prompt caching (good) vs paid for every prompt fresh (bad).

Per-sub-agent rows pick up the description from each agent's `.meta.json` sidecar, so you can tell which dispatch was which without having to remember agent IDs.

### 3. Done

Report the total + the most expensive sub-agent if any. No file is written by default; if you want to keep a snapshot, redirect `--format json` output to a file yourself.

## Output schema (`--format json`)

```ts
{
  session: string,            // session UUID
  project_dir: string,        // resolved project directory
  generated_at: string,       // ISO 8601 UTC
  main: {                     // main thread totals
    in: number,
    out: number,
    cacheCreate: number,
    cacheRead: number,        // informational, NOT counted
    msgs: number,
    total: number,            // = in + out + cacheCreate
    skipped: number           // malformed JSONL lines
  },
  sub_agents: [{
    agentId: string,
    description: string|null, // from agent-<id>.meta.json when present
    in, out, cacheCreate, cacheRead, msgs, total, skipped
  }],
  sub_agent_totals: { same shape as main, no skipped },
  total_counted: number       // = main.total + sub_agent_totals.total
}
```

### Token accounting convention

Per-invocation tokens sum these `usage` fields across all assistant messages:

- `input_tokens` — fresh input to the API
- `output_tokens` — model output
- `cache_creation_input_tokens` — input that becomes cache (paid once when written)

NOT summed:

- `cache_read_input_tokens` — input served from cache (already paid for upstream; ~10× cheaper per token but not free; counting it would double-bill multi-turn runs)

Matches `mikko-skill-usage`'s convention exactly. If a portfolio total from `mikko-skill-usage` and a sum of `session-cost` numbers ever disagree by more than rounding, one of them has a bug.

### Sub-agent accounting

Sub-agent JSONL files live under `<session-id>/subagents/agent-<id>.jsonl` (with a sibling `.meta.json` carrying the description). The scanner walks them after the main JSONL and dedupes by `requestId`; if the harness ever logged a parent-thread assistant message and a sub-agent's first message with the same `requestId`, only one would count. Empirically the IDs don't collide, but the dedupe is defensive.

## Token expectations

This is a pure JSONL parser. No model calls. No network. Cost: zero model tokens. Wall-clock: under a second for sessions under ~5MB of transcript.

## Failure modes

- **`~/.claude/projects/<cwd-encoded>/` not found.** The cwd → directory resolution missed. Pass `--project-dir` explicitly.
- **No `.jsonl` files in the project dir.** Either Claude Code has never run on this repo, or you're looking at the wrong project dir.
- **Malformed JSONL line.** The scanner skips it, counts the skip, and continues. The summary doesn't surface the skip count today; pass `--format json` and read `main.skipped` if you want to know.
- **Session still being written.** Run after the next message lands or after a pause; the last line of a being-written JSONL may be partial.
- **Sub-agent `.meta.json` missing.** The agent description shows as null. Doesn't affect token counts.

## Limitations

- **No outcome quality.** Same caveat as `mikko-skill-usage`: this counts tokens, not value. A 200K-token sub-agent that produced exactly the right answer is the same number as a 200K-token sub-agent that produced garbage.
- **No counterfactual.** The "what would this have cost without parallel sub-agents?" question is unknowable — the scanner only sees what happened.
- **No dollar figure.** Counted tokens × per-token rate (model-dependent) is left to the reader. Different sub-agents may use different models (Sonnet vs Opus); the `.meta.json` sidecar records this if you want to break out cost by model in a future revision.

## Freshness check

Staleness checks run by `/mikko-skills-freshness` on any change to this skill — they assert the skill's load-bearing pieces still ship / stay documented. See that skill for the check vocabulary.

```toml
[[check]]
kind = "path_exists"
path = "scan.mjs"

[[check]]
kind = "command_exists"
command = "node"
```
