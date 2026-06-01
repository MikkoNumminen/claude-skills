---
name: react-anti-patterns-audit
description: Read-only audit for six concrete React anti-patterns that recur in component code (key=index in lists, useEffect for derived state, dep-array lies, state mutation instead of replace, missing effect cleanup, multiple sources of truth). Each check has a concrete smell example and a concrete legitimate counter-example so the auditor can tell signal from noise. **Runs a pre-flight check first** — if the target codebase isn't a React project, the skill aborts cleanly with a suggestion to use a different skill. Use whenever the user says "audit my React code", "review this for React anti-patterns", "check my hooks", "find re-render issues", or before merging a substantial component PR. NOT a witch hunt for "non-idiomatic React" — every finding must be a specific testable pattern with a concrete example.
barney: Checks your React code for six common gotchas (index-as-key, useEffect-for-derived-state, dep-array lies, leaky effect cleanup). Bails fast if it's not a React codebase.
---

# react-anti-patterns-audit

Reads a React codebase (or a specified directory / branch diff) looking for six specific anti-patterns that recur in component code. Reports findings in a markdown table under `docs/audits/`. **Does not modify code.** The human decides which findings are real.

## Why this skill exists separately from `audit` / `ai-codegen-smell-audit`

The general audits in this library catch language-agnostic concerns — robustness bugs (`audit`), LLM-codegen surface texture (`ai-codegen-smell-audit`). Neither flags React-specific shapes: a `key={index}` looks innocent to a generic auditor, but it's a re-render bug waiting for the list to reorder. `useEffect` chained for derived state passes every "is this code clean" check yet causes double renders.

This skill is the React-specific reviewer. The patterns it checks would be noise on a Python codebase, signal on a React one.

## Pre-flight check — IS THIS EVEN A REACT CODEBASE?

**Before doing anything else, the skill verifies the target codebase looks like React.** If it doesn't, it aborts cleanly with a one-line message and a pointer to a more appropriate skill, rather than wasting tokens on a fruitless audit.

Procedure (single main-thread pass, ~3K tokens total):

1. **`Read` the root `package.json`** (or top-most one found via `Glob`). Check `dependencies` + `devDependencies` for `react`.
2. **`Glob` for `.jsx` and `.tsx` files** under the target directory. Count the matches.
3. **Apply this decision matrix:**

| `react` in package.json? | `.jsx`/`.tsx` files found? | Verdict | Action |
| --- | --- | --- | --- |
| Yes (any version) | Many (≥10) | **Proceed** | Run the full audit |
| Yes | Few (1–9) | **Proceed with note** | Run the full audit; preface report with "small React surface — patterns may not surface at scale" |
| Yes | None | **Bail** | "package.json names react but no .jsx/.tsx files found — is the source tree elsewhere? Pass `--source <path>` to point at it" |
| No | Many | **Bail** | "found React-shaped files but no react dependency declared — confirm this is the right codebase" |
| No | None | **Bail** | "this does not look like a React codebase. Try `/mikko-audit` (universal robustness) or `/mikko-ai-codegen-smell-audit` (universal LLM-codegen smells) instead" |

The pre-flight runs synchronously and outputs one of:

- `pre-flight: React codebase confirmed (react in package.json, N .jsx/.tsx files). Proceeding with the full audit.`
- `pre-flight: aborting — <reason>. Suggested alternative: <skill-name>.`

If the pre-flight bails, **no audit runs and no report is written**. Recover by either pointing at the right source tree (`--source <path>`) or invoking the suggested alternative skill.

Why this matters: a 6-check React audit run on a Django codebase still produces a report. It's a useless report — none of the checks fire — but it consumed ~30K tokens to confirm "nothing here." The pre-flight short-circuits that for ~3K tokens.

## When to invoke

- "react audit", "react anti-patterns audit", "check my hooks", "find re-render issues", "audit this React PR"
- Before merging a substantial component PR (multiple files of new components or hook usage)
- On a codebase that's accumulated several AI-pair-programming sessions on the React layer and you want one pass that flags the patterns that drift in without a human catching them
- After running `audit` (robustness) and `ai-codegen-smell-audit` (LLM surface texture) — this is the *React-specific* layer

## When NOT to invoke

- **Not** on a non-React codebase. The pre-flight will catch this — but don't burn the cycles. If you're not in a React repo, use a different skill.
- **Not** as a substitute for `audit`. This skill finds React-specific shape issues, not generic robustness bugs. Run both if you want both.
- **Not** during initial code generation. Same reason as `ai-codegen-smell-audit`: the model would chase its own tail.
- **Not** as a style linter. Quote style, import order, naming conventions — that's ESLint's job.
- **Not** as a "is this code idiomatic" judgement call. Idiomatic React shifts every few years; this skill checks **shapes** (concrete code patterns with verifiable consequences), not vibes.

## What this skill does NOT do

- **Does not detect "non-idiomatic React"** in a tribal sense. Findings are about concrete shapes, not idiom preferences.
- **Does not modify code.** Output is a markdown report. The human picks fixes.
- **Does not flag patterns with a documented reason.** A `// Stable for the lifetime of this component — see docs/decisions/0007-react-state-policy.md` comment immunises the line.
- **Does not audit non-React code in the same repo.** A Next.js project's API routes (server-side) get skipped; the audit targets components and hooks only.

## The six checks

Each check has the same structure: **smell example** (what the pattern looks like when it's wrong) and **legitimate example** (what the same shape looks like when it's fine). If a finding can't meet that bar — concrete shape, concrete counter-example — it doesn't appear in the report.

### 1. `key-as-index-in-lists`

**Smell** — `<Item />` is keyed by its array index in a list that can reorder, delete, or insert. React's reconciler uses `key` to match elements across renders; index-based keys cause state to "stick" to the wrong item when the list shape changes.

```jsx
{items.map((item, i) => <Item key={i} data={item} />)}  // ⚠️ wrong if items[] can reorder
```

**Legitimate** — the list is append-only and items don't carry component-local state.

```jsx
{constantStaticHeaders.map((h, i) => <Header key={i} {...h} />)}  // ✓ never reorders, no internal state
```

Note: this case is genuinely rare in production. Most data has a more meaningful key candidate (`item.id`, `item.slug`, a hash of stable fields) — when in doubt, prefer those over the index. The check defers to the human if the list source can be statically proven append-only.

**Report shape**: file:line + the offending JSX node + the list source.

### 2. `useEffect-for-derived-state`

**Smell** — a piece of state is set inside a `useEffect` that has another state value (or a prop) as its dependency. The "derived" state recomputes on every change of the source; could be a plain `const x = compute(prop)` instead.

```jsx
const [fullName, setFullName] = useState('');
useEffect(() => { setFullName(`${first} ${last}`); }, [first, last]);  // ⚠️ double render
```

**Legitimate** — same as a `const`, no state needed.

```jsx
const fullName = `${first} ${last}`;  // ✓ derived in render, no useEffect, no extra render
```

**Also legitimate** — when the "derivation" genuinely requires a side effect (debounce, async fetch, subscription). Then `useEffect` is the right tool because the derived value can't be a pure render-time computation:

```jsx
useEffect(() => {
  const handle = setTimeout(() => setDebouncedQuery(query), 300);
  return () => clearTimeout(handle);
}, [query]);  // ✓ async derivation; useEffect is correct here
```

**Report shape**: file:line of the `useEffect` + the state it sets + the equivalent derived expression.

### 3. `dep-array-lies`

**Smell** — a hook's dependency array omits a referenced value, or includes one it doesn't actually use. The first case causes stale closures (the effect captures an old value and never refreshes); the second causes spurious re-runs.

```jsx
useEffect(() => { console.log(count); }, []);  // ⚠️ closes over count but won't update
```

**Legitimate** — the dep array truthfully enumerates every value the effect closes over.

```jsx
useEffect(() => { document.title = title; }, [title]);  // ✓ title is the actual dependency
```

**Report shape**: file:line of the hook + the missing or extraneous identifier. `react-hooks/exhaustive-deps` ESLint rule catches most of these — this check confirms it's enabled and reports cases where it's disabled with a comment but the omission is real.

### 4. `state-mutation-instead-of-replace`

**Smell** — state is updated by mutating the existing object or array (`state.foo = bar; setState(state)`) rather than producing a new reference. React's `useState` compares by reference; a mutated-then-set state is reference-equal to the previous value, so the update is silently dropped (or only fires when a sibling change triggers a re-render).

```jsx
items.push(newItem); setItems(items);  // ⚠️ same reference, no re-render
```

**Legitimate** — a new reference is produced.

```jsx
setItems([...items, newItem]);  // ✓ new array reference
```

**Report shape**: file:line of the mutation + the state setter call. Distinguishes from local-scope mutation (which is fine).

### 5. `effect-cleanup-missing`

**Smell** — a `useEffect` sets up a subscription, timer, or event listener and doesn't return a cleanup function. The resource leaks across re-renders; on unmount, the listener fires on a torn-down component.

```jsx
useEffect(() => { window.addEventListener('resize', handler); }, []);  // ⚠️ never removed
```

**Legitimate** — when the effect *does* acquire a resource, the cleanup matches it:

```jsx
useEffect(() => {
  window.addEventListener('resize', handler);
  return () => window.removeEventListener('resize', handler);  // ✓
}, []);
```

**Also legitimate** — when the effect *doesn't* acquire a resource at all (assigning to `document.title`, syncing local state, logging), no cleanup is needed and the check ignores it:

```jsx
useEffect(() => { document.title = `Inbox (${unread})`; }, [unread]);  // ✓ no listener / timer / subscription to clean up
```

**Report shape**: file:line + the resource being acquired (listener / timer / subscription) + the missing cleanup pattern.

### 6. `multiple-sources-of-truth`

**Smell** — state is initialised from a prop in a `useState(prop)` call and never resynced when the prop changes. The component now has two sources of truth: the parent's prop and the local state, which diverge once the user interacts.

```jsx
const [email, setEmail] = useState(props.email);  // ⚠️ ignores prop changes after mount
```

**Legitimate** — the prop is genuinely an "initial value" (e.g. an autofocused form field where downstream changes should be controlled locally).

```jsx
const [email, setEmail] = useState(props.initialEmail);  // ✓ prop name says "initial"
```

**Report shape**: file:line of the `useState(prop)` + a check for whether the prop name signals "initial" / "default" / "seed" (heuristic; the human decides).

**Caveat**: the prop-name heuristic is brittle — many real codebases pass `props.email` and *do* mean "seed value" without the `initial*` prefix. Expect false positives; the human reviewer is the final judge. The check's value is surfacing the pattern for review, not auto-flagging bugs.

## Flags

- `--source <path>` — audit only the given directory (default: project root). Useful for monorepos: `--source packages/web` audits one package at a time.
- `--force` — bypass the pre-flight bail. Records the override in the report header so the reader knows the audit ran without confirmation that the target is actually React. Use only when the pre-flight gives a known-wrong negative (React via CDN, workspace-package React types, etc.).

## Procedure

1. **Pre-flight.** See the section above. Bail if not React (unless `--force`).
2. **Confirm scope.** If `--source <path>` was passed, audit only that directory. Otherwise audit the whole codebase under the project root.
3. **For each check, scan the codebase.** Use `Glob` to enumerate `.jsx` / `.tsx` files, then `Read` (or grep with `Grep`) for the pattern. Six checks; each is a single pass. Sequential is fine — total tokens are manageable.
4. **Aggregate findings.** For each match, capture: check name, file:line, the smelly snippet (3-5 lines for context), and a one-line note on why it matches the smell shape.
5. **Apply immunity comments.** A `// audit:react:ignore <check-name> — <reason>` comment on the offending line excludes it from the report. This is the explicit-trust-boundary opt-out.
6. **Write the report.** Markdown table under `docs/audits/react-anti-patterns-YYYY-MM-DD.md`. **Create the `docs/audits/` directory if it doesn't already exist** (`mkdir -p`-equivalent — most projects don't have one). Severity is implicit (every finding is the same shape — concrete, fixable, file:line citable). Group by check; within each check, group by file.
7. **Print the report path** and a one-line summary: `Wrote react-anti-patterns-YYYY-MM-DD.md — N findings across M files (checks: <comma-separated list of checks that fired>).`

## Output schema

The outer fence below is 4 backticks so the inner 3-backtick code blocks render correctly on GitHub.

````markdown
# React anti-patterns audit — {YYYY-MM-DD}

**Scope:** {project root or --source path}
**Pre-flight:** {pre-flight one-liner}

## Summary

| Check | Findings |
| --- | ---: |
| key-as-index-in-lists | 3 |
| useEffect-for-derived-state | 1 |
| dep-array-lies | 0 |
| state-mutation-instead-of-replace | 0 |
| effect-cleanup-missing | 2 |
| multiple-sources-of-truth | 0 |
| **Total** | **6** |

## Findings

### key-as-index-in-lists

#### src/components/ItemList.tsx:42

```tsx
{items.map((item, i) => <Item key={i} data={item} />)}
```

The `items[]` list is rebuilt from the `useQuery` result on line 38; ordering can change between fetches. Switch to `key={item.id}` if items have a stable id, or `key={\`${item.foo}-${item.bar}\`}` if not.

...(further findings per check)...
````

## Token expectations

For a small-to-medium React codebase (~30 component files, ~3K LOC):

- Pre-flight: ~3K tokens (Read package.json + Glob counts)
- 6 checks × 1 pass each: ~10–15K tokens input (file Reads) + ~5K output (the report)
- Total: ~20–25K tokens, ~30s wall-clock

_These figures are editorial estimates, not measured — once `/mikko-skill-usage` has receipts for this skill, the measured numbers supersede them._

For a large React monorepo (~200 component files): consider running per-package with `--source packages/<name>` rather than the whole tree at once. The aggregation isn't smart enough yet to dedupe across packages.

Cadence: per-PR for substantial component changes, ~30 invocations/year on an actively-iterating React project.

## Failure modes

- **Pre-flight bails on a real React codebase.** The decision matrix is conservative — `react` in `package.json` AND `.jsx`/`.tsx` files is required for "Proceed". A project using React via CDN (no package.json) or transpiled to plain `.js` files would bail. Override by passing `--force` (the skill records the override in the report header).
- **TypeScript without React types.** `.tsx` files exist but the React types are loaded via a workspace package that doesn't appear in this repo's `package.json`. Same workaround: `--force`.
- **Class components.** The skill's six checks are hooks-shaped. Class-component patterns (componentDidMount-without-componentWillUnmount, this.state mutation) are NOT covered. Adding them would double the SKILL.md length and most modern React doesn't use classes. If you have a class-heavy codebase, run `mikko-audit` instead — it catches the underlying robustness shapes.
- **Server Components / Next.js app router.** The checks assume client components. A Server Component with `useEffect` is itself a bug (RSCs can't use effects), but caught by the framework's compiler, not this skill. The audit will skip server-only files if it can identify them via `"use client"` or `"use server"` directives.
- **React Native.** RN projects pass the pre-flight (they have `react` in `package.json` and `.jsx`/`.tsx` files), and five of the six checks are framework-agnostic and apply directly (`key-as-index-in-lists`, `useEffect-for-derived-state`, `dep-array-lies`, `state-mutation-instead-of-replace`, `multiple-sources-of-truth`). The sixth — `effect-cleanup-missing` — uses web-shaped examples; RN listeners use different APIs (`Dimensions.addEventListener`, `Keyboard.addListener`, `BackHandler.addEventListener`) that this check's grep patterns won't match in v1. Either run `--force` and accept some missed RN listeners, or wait for a future `react-native-anti-patterns-audit` that ports the examples.

## Limitations

This skill is **first iteration**. Patterns left out for v1 — each is worth its own future check:

- **`over-memoization`** — `useMemo` / `useCallback` applied where the wrapped value is already stable. Common smell; needs careful analysis to avoid false positives (memoization that's correct but looks unnecessary).
- **`prop-drilling-vs-context-misuse`** — judgement call (the boundary between healthy prop-passing and context is subjective).
- **`render-prop-vs-children-confusion`** — common in older React but waning; defer.
- **`hooks-in-conditional-or-loop`** — already caught by `react-hooks/rules-of-hooks` ESLint rule; this skill assumes you have that enabled and would just duplicate the lint output.

The skill's value is concentrated on the six checks it does have. Adding patterns is straightforward (each is ~20 lines of SKILL.md); future iterations grow the catalog as concrete examples emerge.

## What's verifiable vs editorial

| Claim | Source of truth | Verifiable? |
| --- | --- | --- |
| Is this a React codebase? | `package.json` + file extensions | ✅ Yes (the pre-flight) |
| Does pattern X appear at file:line Y? | The source file itself | ✅ Yes |
| Is pattern X actually a bug here? | Human judgement | 🟡 Heuristic (counter-example tells you when it isn't) |
| Severity / urgency of fixing | Out of scope — the report doesn't claim severity | — |

The report's claims are auditable: every finding cites file:line and shows the offending snippet. A human can open the file and judge whether it matches the smell shape or the counter-example. The skill never says "this is a bug, fix it" — it says "this matches a documented smell shape; you decide."

## Freshness check

Staleness checks run by `/mikko-skills-freshness` on any change to this skill — they assert the skill's load-bearing pieces still ship / stay documented. See that skill for the check vocabulary.

```toml
[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "key-as-index-in-lists"

[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "pre-flight"
```
