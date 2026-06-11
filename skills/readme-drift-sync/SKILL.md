---
name: readme-drift-sync
description: Detect drift between what the repo actually contains and what `README.md` claims, then rewrite ONLY the drifted sections in the README's existing voice. Five drift axes (file structure, dependencies, skills, features, status). Voice-preserving — the skill extracts a voice profile from the existing README first and any rewrite must read as if the original author wrote it. **Write-with-approval**: emits a working-tree edit to `README.md` plus a drift report and a voice-profile cache, then STOPS. Does NOT commit, does NOT push, does NOT regenerate the README from scratch. Use whenever the user says "sync the README", "update the README", "check README drift", "has the README fallen out of date", or after a release-cut before the next push. NOT for initial README creation, full rewrites, CONTRIBUTING/CHANGELOG edits, or general code edits where the README isn't in scope.
barney: Checks whether the README still matches the repo, and rewrites only the parts that drifted — keeping the original author's voice. You review the diff and commit.
---

# readme-drift-sync

**Modifies `README.md` in the working tree** (does NOT commit, does NOT push). The human reviews the diff and commits.

## Why this skill exists separately

A free-form "update the README" prompt produces a regression to generic AI prose: hero rewrites the tagline, bulletizes prose paragraphs, swaps the original author's idioms for template phrasing. The output looks plausible and *reads wrong* to anyone who knew the original. The drift gets fixed; the voice gets killed.

This skill is the antidote — every change must be traceable to a concrete drift finding, AND every rewrite must pass the test "could this paragraph appear in the existing README without anyone noticing it was edited?" If it can't pass that test after two revisions, the section is left alone and flagged for manual rewrite.

## When to invoke

- "update the README", "sync the README", "check README drift", "has the README fallen out of date"
- "the README mentions X but we removed it last sprint", "are we still claiming Y in the README"
- After a `release-cut` skill ran, before the next push — version bumps and new features tend to land before the README catches up
- After adding a new skill under `skills/*/` or `.claude/skills/*/` to a repo whose README enumerates its skills
- Before merging a PR that changes `package.json` / `requirements.txt` / `Cargo.toml` / etc.
- On a quarterly sweep across a portfolio of repos to catch silent drift

## When NOT to invoke

- **Not** during initial README creation. There's no baseline voice to preserve and nothing to compare against. Write the first version by hand; this skill is the *maintenance* tool.
- **Not** for a full rewrite. If the user wants to restructure the README, change the tagline, or move from prose to bullets (or vice versa), that's a different task — invoke this skill only when the *content* drifted, not the *form*.
- **Not** for `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`, `docs/**`, or any other markdown file. The skill targets `README.md` only. A future `docs-drift-sync` could generalise.
- **Not** for adding new sections that document existing-but-undocumented features unless the README explicitly claims completeness ("All flags:", "Full reference:"). For deliberate new-section authoring, the human writes the first draft; this skill is for keeping *existing* sections honest, not for ghostwriting fresh ones.
- **Not** during unrelated code edits where the README isn't in scope. The harness will tempt to load the skill when "README" appears anywhere in the conversation — bail if the user is asking about something else and only mentioned the README in passing.
- **Not** as a translation tool. Multilingual READMEs (FI/SV/EN side-by-side) are out of scope — handle only the language Claude is invoked in, flag the others.

## What this skill does NOT do

The hard boundaries (no regenerate, no commit/push, no other files, no invented voice, no auto-resolving the unverifiable) are stated authoritatively in "When NOT to invoke", "Calibration rules", and "Things NOT to do". One distinction worth pinning here:

- **Does not change tagline, hero text, or asset-bearing sections** (badges, screenshots, logos) unless they make a factual claim that is now wrong. A tagline like "the friendliest audit skill" is voice, not fact — leave it. A tagline like "audits 12 languages" when the repo audits 5 is fact — flag and rewrite.

## The drift checklist

Five axes, priority order. Each has a `Pattern`, a `How to detect`, a `Severity default`, and a `Suggested edit pattern`. The severity defaults can be upgraded or downgraded per finding when context warrants.

### 1. file-structure-drift

- **Pattern.** Directories, scripts, entry points, config files mentioned in the README that no longer exist (stale claim) OR that exist in the repo but aren't mentioned where the README's structure tour would list them (missing addition).
- **How to detect.**
  1. Extract every relative-path-looking string from the README (regex: `[a-zA-Z0-9_./-]+\.(md|sh|py|js|ts|json|toml|yaml|yml)` plus directory references like `src/`, `docs/`).
  2. For each, check existence with `Glob`. Stale = mentioned but missing.
  3. Run `ls` on the project root and on directories the README does enumerate (e.g. "## Project layout" sections). Missing addition = exists but not in the enumeration.
- **Severity default.** Stale claim: **major** (the README is actively wrong). Missing addition: **minor** (only a problem if the README claims completeness; "see also" links don't need to be exhaustive).
- **Suggested edit pattern.** Stale: replace the path with the current equivalent if there is one, or delete the sentence and any surrounding context that referred to it. Missing: add a single line under the relevant section using the same bullet shape and tone as adjacent entries.

### 2. dependency-drift

- **Pattern.** Stack claims in the README that don't match the actual `package.json` / `requirements.txt` / `Cargo.toml` / `go.mod` / `pyproject.toml`.
- **How to detect.**
  1. Find the manifest file (one of: `package.json`, `requirements.txt`, `pyproject.toml`, `Cargo.toml`, `go.mod`). If none, this axis is N/A — skip.
  2. Parse it (or `Read` it directly for simple formats) and extract the top-level dependency names.
  3. Find README sentences that name dependencies — typically in sections titled "Stack", "Built with", "Dependencies", "Requirements". Use `Grep` with the dependency names as queries.
  4. Compare. README claims dep X but X isn't in manifest = stale. Manifest has dep Y but README doesn't mention it AND the README enumerates the stack = missing.
- **Severity default.** Stale: **major**. Missing: **minor** (only major if the README's "Stack" section is presented as exhaustive).
- **Suggested edit pattern.** Stale: replace the dep name with the actual current dep, or delete it. Missing: append to the existing list using the same formatting (commas, bullets, or whatever the README uses).

### 3. skill-drift

- **Pattern.** Skill directories exist that aren't in the README's skill list, or vice versa. Specific to repos whose README enumerates the skills they ship.
- **How to detect.**
  1. `Glob` BOTH `skills/*/SKILL.md` (the layout this library uses at repo root) AND `.claude/skills/*/SKILL.md` (the Claude Code default for consumer repos). Deduplicate by basename — a skill can only live in one of the two locations in a given repo, but check both because conventions vary. Read each match's frontmatter `name` field (use `limit=5` — only the first few lines are needed, no deep read).
  2. `Grep` the README for those names. If the README has a section like "## Skills", "## What's in here", or "## What's in this repo" enumerating skills, compare the README's list against the directory listing.
  3. If the README has no skill-list section at all, this axis is **N/A** — don't invent one.
- **Severity default.** Stale (README names a skill that no longer exists): **major**. Missing (skill exists but unlisted): **minor**.
- **Suggested edit pattern.** Stale: remove the bullet/row, plus any prose that referred to it. Missing: add a row using the same shape (table row, bullet, code block) as adjacent skills. Use the skill's `description` from its frontmatter, summarised to one sentence in the README's voice.

### 4. feature-drift

- **Pattern.** CLI flags, API endpoints, environment variables, major modules, or commands documented in the README that no longer match the code. Or the inverse: new ones that exist but aren't documented.
- **How to detect.**
  1. Extract CLI invocations from the README — anything in a code block that looks like `<binary> <subcommand> --<flag>` or `<bash>`-fenced code with `$` prefix.
  2. For each flag, `Grep` the source for the flag string (literal match). If not found, the README documents a removed flag = stale.
  3. For env vars: `Grep` for `process.env.X` / `os.environ["X"]` / `${X}` patterns in source; compare against README mentions.
  4. For endpoints: harder to fully verify without runtime — match `app.get('/foo')` / `router.post('/bar')` patterns and check README mentions.
  5. Missing-addition checks for this axis are noisy (most repos have many internal flags not worth documenting). Only flag missing additions if the README explicitly claims completeness ("All flags:" or "Full API reference:").
- **Severity default.** Stale flag/endpoint/env var: **major** (users will try it and fail). Missing addition: **minor**, often **skip** unless completeness is claimed.
- **Suggested edit pattern.** Stale: replace with the current equivalent, or delete the example. Missing: add to the relevant table/list using the README's existing format.

### 5. status-drift

- **Pattern.** Quantitative or status claims that can be re-verified: "100% test coverage", "X tests passing", "CI green", "version 1.2.3", "supports Node 18+", "0 dependencies", performance numbers, deployment counts.
- **How to detect.**
  1. Version: parse `package.json` `version` field (or equivalent) and compare to any version mention in the README, including badges.
  2. Test counts: run `pytest --collect-only -q | tail -1` or `npm test -- --listTests | wc -l` if tests exist. Compare against README claims. **Only run** if the README makes a specific count claim — don't run tests speculatively.
  3. CI status: check `.github/workflows/*.yml` exists. The README's "CI green" badge is auto-updating; only flag if the badge URL is broken or points to a deleted repo.
  4. Dependency counts: `cat package.json | jq '.dependencies | length'` etc. — verify before flagging.
  5. Performance/deployment claims ("deployed to 6000 customers", "10x faster than X"): **unverifiable** — list them in the drift report under "unverifiable claims" but do not auto-rewrite.
- **Severity default.** Stale verifiable claim: **major**. Stale unverifiable claim: **flagged for human**, severity not assigned.
- **Suggested edit pattern.** Replace the number/claim with the verified current value. For badges with dynamic URLs, prefer fixing the badge target over editing prose. For unverifiable claims, the report flags them with the suggested action "verify externally and update by hand".

## Voice profile extraction (the critical part)

Before rewriting a single sentence, the skill reads the existing `README.md` in full and extracts a voice profile. The profile is saved to `docs/audits/readme-drift-scratch.md` and referenced during every rewrite. **No rewrite happens before the voice profile is written and visible in the skill's working context.**

The fields the profile must enumerate are defined in [`voice-profile-template.md`](voice-profile-template.md) in this skill's directory. Summary:

- **Tone register** — formal, casual, sardonic, earnest, technical, etc.
- **Humor style** — present or absent; if present, what kind (self-deprecating, ironic, deadpan, exuberant)
- **Pronoun choice** — `I`, `we`, `you`, impersonal, or some mix
- **Sentence rhythm** — short and punchy, long and clausal, mixed
- **Vocabulary tells** — concrete word choices the author favors ("ship" vs "release", "auth" vs "authentication", "kit" vs "library")
- **Structural patterns** — bullets vs prose, header style (questions vs statements), code-block introductions
- **Reference style** — barney (assume nothing), educational, ironic understatement, humor-forward, etc.

Each field gets at least one **quoted example** from the README. The quote is the proof — without it, the profile is a guess.

### Hard rule on voice match

After drafting a rewrite for any section, the skill applies this test:

> Could this paragraph appear in the existing README without anyone noticing it was edited?

If the answer is "yes" — proceed. If "no" — revise once. If the revision still fails — revise a second time. If the second revision still fails — **leave the section alone, do not edit it in the working-tree README, and flag it in the drift report** under "drift detected but voice match uncertain — recommend manual rewrite."

This rule is blocking. A drifted section left untouched with a flag is a better outcome than a fixed section in the wrong voice — the first is honest about what the skill can do, the second silently corrupts the artifact the skill was meant to protect.

### Voice profile cache

The voice profile is written to `docs/audits/readme-drift-scratch.md` and **kept across runs**. On the second invocation of the skill, the previous profile is read first; if the README's first ~500 characters haven't changed since the profile was last written (verify with a quick `Read` of the README's head), the cached profile is reused and the extraction step is skipped. Saves ~5K tokens on repeat runs.

Invalidate the cache by deleting the scratch file by hand if the README has been substantially rewritten and the cached profile no longer applies.

## Output format

Three artifacts per run:

### 1. `docs/audits/readme-drift-<YYYY-MM-DD>.md` — drift findings report

Markdown with this exact structure:

````markdown
# README drift report — <YYYY-MM-DD>

## Summary
- README audited: `README.md` (at commit `<git rev-parse HEAD>`)
- Total drifts: N (stale: N, missing: N, unverifiable: N)
- Rewrites applied: N
- Rewrites skipped (voice match failed): N
- Voice profile: `docs/audits/readme-drift-scratch.md` (cached: yes/no)

## Findings

### Stale claims (rewritten)

| Axis | README claim | Reality | Section rewritten | Voice-match attempts |
| --- | --- | --- | --- | --- |
| file-structure | `docs/old-name.md` | file missing | "Where to go from here" | 1 |

### Missing additions (added)

| Axis | Added | Section | Voice-match attempts |
| --- | --- | --- | --- |
| skill | `mikko-foo` | "Skills" table | 1 |

### Skipped (voice match failed twice)

| Axis | Drift | Section | Reason |
| --- | --- | --- | --- |
| feature | new `--bar` flag undocumented | "Using it" | rewrite read as generic — manual edit recommended |

### Unverifiable claims (flagged, not touched)

| Claim | Why unverifiable | Suggested action |
| --- | --- | --- |
| "deployed to 6000 customers" | runtime / external metric | verify externally, update by hand |
````

### 2. `docs/audits/readme-drift-scratch.md` — voice profile cache

Format defined in [`voice-profile-template.md`](voice-profile-template.md). Persists across runs.

### 3. `README.md` — edited in working tree

`Edit` calls on `README.md` for every rewrite that passed the voice-match test. Sections that failed the test are not touched.

### Chat summary (≤4 lines)

Print to chat after the run completes:

```
Found N drifts (X stale, Y missing, Z unverifiable). Rewrote sections [list].
Skipped W (voice match failed). Voice profile cached at <path>.
Review with: git diff README.md
Commit when ready.
```

## Calibration rules

These rules are blocking — apply them before recording any drift finding.

- **Aspirational sections are immune.** "Coming soon", "Planned for v2", "Roadmap" sections describe the future; "drift" between aspiration and current reality is the *point*. Do not flag.
- **Quotes, testimonials, and borrowed text are immune.** A blockquote attributed to a third party, a code-block license preamble, or quoted user feedback never gets rewritten even if it contains a stale fact. Flag in the report; do not edit.
- **Dated claims keep the date.** "As of 2025-Q1, the engine supports five languages" is correct *as of that date*. Do not silently update the number — that erases the timestamp's meaning. Instead, flag with the suggested action "consider adding a follow-up paragraph with current numbers, or replace the dated claim if the timestamp is no longer load-bearing."
- **Voice match failed twice = leave it alone.** See the hard rule above. Flag, don't fix.
- **Trust the manifest, not the README.** When `package.json` and the README disagree on the dependency list, the manifest wins (it's the runtime source of truth). Same for `version`, supported Node version, etc.
- **House conventions documented elsewhere win over implied conventions.** If `docs/STYLE.md` or `CONTRIBUTING.md` documents a voice guideline (e.g. "use 'we' throughout", "no emoji"), that overrides whatever the README appears to do. Read those before extracting the voice profile.
- **Skip the badges row** unless a badge URL is broken. Badges are markup, not prose.

## Procedure

1. **Pre-flight.**
   - If the user's request is *vague* ("the README needs work", "fix the README", "clean up the README"), bail before doing anything and ask: "drift-sync runs five specific checks — file structure, dependencies, skills list, features (CLI flags / env vars / endpoints), and status claims (versions, test counts). Want me to run all five, or did you mean something else (restructure / tone change / new section)?" Wait for the answer. Don't extract a voice profile or run drift checks until the scope is confirmed.
   - `Read` `README.md`. If it doesn't exist, bail with "no README.md to sync — this skill is for maintaining an existing README, not creating one. Write the first version by hand."
   - If the file is under ~30 lines, warn: "short README — voice extraction may be unreliable; proceed with caution."

2. **Extract voice profile** (or load cache if valid). See "Voice profile extraction" section. Write to `docs/audits/readme-drift-scratch.md`. **Create `docs/audits/` if it doesn't exist.**

3. **Run drift checks 1–5** in priority order. For each finding, record: axis, location in README (line range), nature (stale / missing / unverifiable), evidence (file path that's missing, manifest dep that's unclaimed, etc.).

4. **Apply calibration rules.** Filter the findings list against the immunity rules above. Aspirational, quoted, and dated claims drop out of the rewrite queue (still appear in the report).

5. **Per remaining finding, attempt a rewrite.** Apply the voice profile. Test against the hard rule. Up to two revisions. If still failing, move the finding to the "Skipped" bucket and do not edit.

6. **Write the drift report.** `docs/audits/readme-drift-<YYYY-MM-DD>.md`. If a file for the same date already exists, suffix with `-v2`, `-v3`, etc. — never overwrite.

7. **Apply the rewrites to `README.md`.** Use `Edit` calls — one per section. Do not use `Write` (that would rewrite the whole file and risks unintended edits elsewhere).

8. **Print the chat summary** and stop. Do not commit. Do not run `git diff`. The human takes it from here.

## Token expectations

For a typical README (~200 lines, ~6K characters) on a small-to-medium repo:

- Pre-flight + voice extraction: ~5–8K tokens (one full Read + structured note-taking)
- Five drift checks: ~10–15K tokens (file enumeration, manifest parse, grep passes)
- Rewrites with voice match: ~3–5K tokens per rewritten section × N sections
- Report + edits + summary: ~3K tokens output
- **Total: ~30–50K tokens per run** for ~5 rewrites; lower if drift is sparse.

Repeat runs with cached voice profile: subtract ~5K tokens.

Cadence: per-release-cut, or quarterly sweep. ~10–20 invocations/year on an actively-iterating repo; lower if releases are infrequent.

## Failure modes of this skill

Honest list — the auditor should know these going in:

- **Under-detects in sparse READMEs.** A README that says little ("This is a Python script.") has little to drift against. The skill will find few findings; that doesn't mean the README is in good shape — it means the skill can't tell. Flag in the report: "low-content README; drift detection limited to dependency manifest and file structure."
- **Over-fits voice on short READMEs.** A 20-line README isn't enough sample to extract a reliable voice profile. The skill will detect "earnest, third person, short sentences" and ascribe it as intentional voice when it might just be brevity. Expect more "voice match failed" outcomes on small READMEs.
- **Cannot verify runtime/external claims.** "Used by 200 teams", "5x faster than X", "deployed in production at Y" — none of these are visible to the skill. Flagged as unverifiable; not auto-rewritten.
- **Multilingual READMEs.** A FI / SV / EN side-by-side README only gets audited in the language Claude is invoked in. The other languages are flagged at the top of the drift report with: "untouched — non-EN sections were not audited; rerun with the appropriate language to sync them."
- **Voice profile drift between runs.** If the README is heavily rewritten between two invocations and the cache isn't invalidated by hand, the second run uses a stale profile and the rewrites will read wrong. Mitigated by the "first ~500 chars unchanged" cache check, but a major mid-file rewrite can fool that heuristic.
- **The "voice match" test is itself heuristic.** A rewrite that passes the test still might read subtly off to the original author. The skill biases toward conservatism — when in doubt, leave it alone and flag — but the human is the final judge.
- **Single-repo scope only.** This skill audits one repo's README at a time. Cross-repo / portfolio-wide README audits (the "walk every sibling repo, sync data, open a PR per repo" pattern) are a different shape and out of scope here — invoke separately if you have such a tool.

## What's verifiable vs editorial

| Claim | Source of truth | Verifiable? |
| --- | --- | --- |
| README mentions file X | `README.md` itself + `Glob` | ✅ Yes |
| File X exists | `Glob` / `Read` | ✅ Yes |
| Manifest dep list matches README claim | `package.json` etc. | ✅ Yes |
| Version number matches | `package.json` version field | ✅ Yes |
| Voice profile matches the rewrite | Heuristic (the hard-rule test) | 🟡 Heuristic |
| Severity of a finding | The skill's default + calibration rules | 🟡 Heuristic (overridable per finding) |
| README claims "deployed to N customers" is accurate | External system | ❌ No (flagged unverifiable) |

The drift report's claims about *what changed in the repo* are auditable: every finding cites a file path, a manifest field, or a grep result. The claims about *voice match* are heuristic — the rewrite either reads right or it doesn't, and the skill's "hard rule" is a guard against the most obvious failures, not a proof of voice fidelity.

## Content calibration

See [content-calibration.md](content-calibration.md) for the 2026-05-20 mental dry-run and associated design notes.

## Trigger calibration

Ten predicted-vs-intended firings live in [`trigger-calibration.md`](trigger-calibration.md) in this skill's directory. The current description routes correctly on 9/10; one ambiguous case ("the README needs work") is flagged as an intentional bail-to-clarification rather than auto-firing. See that file for the full table.

## Things NOT to do

- **Never regenerate the README from scratch.** Even if all five drift checks fire, edit section-by-section. The hero/tagline/structural backbone is voice, not fact.
- **Never commit or push.** This skill stops at the working-tree edit. The human commits.
- **Never modify `CONTRIBUTING.md`, `CHANGELOG.md`, or any other markdown.** Out of scope.
- **Never silently update a dated claim** (see calibration rules).
- **Never invent a voice the README didn't have.** If the existing README is dry and impersonal, the rewrites stay dry and impersonal. Don't "improve" the prose.
- **Never proceed without the voice profile.** If extraction fails (empty README, unreadable content), bail. No profile, no rewrites.
- **Never rewrite a section that failed the voice-match test twice** (see the hard rule). Flag for manual rewrite.

## Freshness check

Staleness checks run by `/mikko-skills-freshness` on any change to this skill — they assert the skill's load-bearing pieces still ship / stay documented. See that skill for the check vocabulary.

```toml
[[check]]
kind = "path_exists"
path = "trigger-calibration.md"

[[check]]
kind = "path_exists"
path = "voice-profile-template.md"

[[check]]
kind = "no_broken_md_links"

[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "## The drift checklist"
```
