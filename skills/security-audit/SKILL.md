---
name: security-audit
description: Orchestrates the multi-phase security audit + remediation. Phase 0 sets up agents; Phase 1 maps the full attack surface (entry points, auth, authz, input, secrets, data exposure, deps, transport, client, ops); Phase 2 turns findings into a prioritized remediation plan; Phase 3 fixes one finding at a time with regression tests (crit/high sequential, low/med parallelizable in worktrees); Phase 4 writes AI-first security documentation (SECURITY.md, threat model, invariants, code-level markers, lint rules); Phase 5 verifies. Each phase produces an artifact under docs/security/ and STOPS at a gate for user approval. Never auto-advances. Critical findings surface immediately.
barney: Walks your attack surface (auth, input, secrets, deps, etc.), finds security holes, then helps fix them one at a time with regression tests. Pauses for your approval between phases — never autopilots.
---

# When to use

- The user types `/security-audit` to start, resume, or scope a security pass.
- The user asks "audit the codebase for security" or "do a vuln review".
- The user references `docs/security/_progress.md` and asks to continue.
- A specific surface is in scope (e.g. "audit just the API routes") — still use this skill, narrow Phase 1's scope explicitly in the dispatch prompt.

This skill is **the orchestrator**. It does NOT do the agents' work itself — it dispatches the right specialized agent for each phase, gates on artifacts, and waits for explicit user approval before advancing.

# Adjacent skills

- `/audit` — modular-architecture refactor. Orthogonal axis. A finding from this skill that says "auth is checked in 47 different places" might trigger a follow-up `/audit` pass to consolidate.
- Project-local skills — if the host repo defines companion audit skills (e.g. a data-pipeline audit or a migration workflow skill), run them BEFORE Phase 3 touches the files they own. Check the local `.claude/skills/` directory at Phase 0.
- `/security-review` — Claude Code built-in. Per-branch / per-PR scope. Use it for incremental PR-level checks; use `/security-audit` for whole-codebase passes. They do not overlap and do not replace each other.

# The phases

Each phase produces exactly one artifact and STOPS. Do not start the next phase without the user typing "approved" (or equivalent).

| Phase | Agent | Artifact | Gate |
|-------|-------|----------|------|
| 0a — Skill reconciliation | (orchestrator) | `docs/security/00-skill-reconciliation.md` | User confirms reconciliation summary |
| 0b — Agent setup | (orchestrator) | `docs/security/00-agent-setup.md` | User confirms agents are correctly defined |
| 1 — Attack-surface map | `security-auditor` | `docs/security/01-attack-surface.md` | User confirms the map is complete |
| 2 — Findings + plan | `security-auditor` | `docs/security/02-findings-and-plan.md` | User approves remediation order; for crit/high, each fix approach individually before Phase 3 touches it |
| 3 — Remediation (per finding) | `security-fixer` × N | per-finding commits + `docs/security/02-findings-and-plan.md` updates (mark fixed, link commit) | User approves at module-list end (low/med may batch) |
| 4 — AI-first documentation | `security-doc-writer` | `SECURITY.md` (root) + `docs/security/threat-model.md` + `docs/security/invariants.md` + per-module SECURITY notes + `docs/security/03-documentation-summary.md` | User approves |
| 5 — Verification | `security-auditor` | `docs/security/05-final-report.md` | Audit complete |

Continuous logs (no gate, agent appends as it works):
- `docs/security/04-other-findings.md` — non-security issues spotted by `security-fixer` and explicitly out of scope. Surfaced for the user to triage later.
- `docs/security/_progress.md` — checkpoint for resume across sessions.

# Severity definitions (used in Phase 2)

- **Critical**: unauthenticated remote exploit; account takeover; mass data exposure; secrets leaked publicly.
- **High**: authenticated exploit with significant impact; IDOR; privilege escalation; stored XSS; SQLi behind auth.
- **Medium**: weak crypto with mitigations; missing rate limit; info disclosure of non-secrets; CSRF on state-changing routes.
- **Low**: missing security headers without exploit path; verbose errors; outdated deps without known exploits.
- **Informational**: hardening; defense-in-depth that's currently absent.

# Orchestration rules

1. **One phase per turn.** Never run Phase 1 and Phase 2 in the same dispatch.
2. **Re-read the prior artifact before dispatch.** If Phase 2's plan is the input to Phase 3, the Phase 3 dispatch reads it and quotes the relevant finding spec into the agent's prompt — do NOT make the agent search for it.
3. **One finding per `security-fixer` invocation** for critical/high. Low/medium independent fixes may run in parallel via `isolation: "worktree"` if they touch disjoint files. If two findings touch the same file, serialize them.
4. **Gate explicitly.** After every phase, present the artifact's path and a short summary, and ask the user "Phase N complete — review and reply 'approved' to continue, or 'redo' with changes." Do not advance on a non-explicit nod.
5. **Behavior preservation outside security fixes is non-negotiable.** Each Phase 3 commit is the security fix and the regression test. Nothing else.
6. **Persistence-layer fixes get extra scrutiny.** Any fix touching the data-persistence layer (ORM, DB client, schema validation, save/load paths) must be reviewed at Opus level. If a project-local pipeline-audit skill exists, run it before the fix commits.
7. **Schema-touching fixes must follow the project's migration workflow.** If the repo has a migration convention (files under db/migrations/, a project-local migration skill, or a documented migration script), a fix is not done until the migration is applied to prod. Check CLAUDE.md or the project README for the procedure.
8. **Auth/crypto/secrets fixes always escalate to Opus.** Even if the change looks small. The orchestrator (this skill) reviews each such fix before merging the next.
9. **Surface critical findings immediately.** If Phase 1 or Phase 2 uncovers a critical issue (live secret leak, unauthenticated RCE, mass-exposure path), STOP and tell the user before continuing the artifact. Don't wait for the gate.
10. **Checkpointing.** If a phase grows too large for one session, the agent appends to `docs/security/_progress.md` with what's done and what's next, and the orchestrator (this skill) resumes from there next session.
11. **No exploit details in commit messages or public changelogs.** Exploit details stay in `docs/security/`. Commit messages describe the fix.
12. **`Co-Authored-By` trailer is forbidden** per repo convention (see `MEMORY.md`).

# Resume protocol

When the user invokes `/security-audit` and `docs/security/_progress.md` already exists:

1. Read `_progress.md`.
2. Identify the next pending phase (or the next pending finding within Phase 3).
3. Re-state the user-facing summary: "We're on Phase X. Last completed: <Y>. Next dispatch: <Z>."
4. Wait for "go" before dispatching.

# Anti-patterns

- **Don't auto-advance.** Even if a phase looks complete and tests pass, never start the next phase without explicit user OK.
- **Don't merge phases.** Phase 1's "no proposals, just inventory" rule is load-bearing — proposals from a still-incomplete map tend to lock in the wrong shape.
- **Don't dispatch a generalist agent.** Use the named agent for each phase. The whole reason these agents exist is single-responsibility scoping.
- **Don't let the fixer expand scope.** A Phase 3 fix that "while I'm here" refactors unrelated code is rejected. Refactors go through `/audit`. Non-security bugs go to `docs/security/04-other-findings.md`.
- **Don't commit on the agent's behalf without explicit user OK.** Default is staged-clean and hand back unless the orchestrator's prompt explicitly authorized auto-commit.
- **Don't weaken project-defined security invariants** to 'fix' a security finding. If the host repo documents security invariants (in CLAUDE.md, a local SECURITY.md, or inline comments) and a Phase 3 fix would relax them, surface this to the user and get explicit sign-off before proceeding.

## Token expectations

Author estimate (not measured — run `/mikko-skill-usage` after a few
invocations for receipts). The orchestrator itself is cheap (~5-10K
per phase dispatch); the per-phase agents dominate, and the cost
depends heavily on how many findings Phase 1 turns up.

- Phase 0 (setup): ~5-10K total
- Phase 1 (attack-surface map, security-auditor agent): ~50-100K
- Phase 2 (findings + plan): ~30-60K
- Phase 3 (per-finding fixes × N): ~30-80K **per finding**; a typical
  audit lands 5-15 findings, so ~150-1000K aggregated across the phase
- Phase 4 (documentation pass): ~40-80K
- Phase 5 (verification): ~30-50K

**Total per full audit: ~300K-1.2M tokens depending on findings count.**
A scoped audit ("just the API routes") cuts Phase 1-2 by 2-3× but
Phase 3 per-finding cost is unchanged.

Cadence: 1-2× per year per repo for a full audit; quarterly for
scoped passes on actively-iterating security-sensitive surfaces.
~2-6 uses/year per repo.

## Freshness check

Staleness checks run by `/mikko-skills-freshness` on any change to this skill — they assert the skill's load-bearing pieces still ship / stay documented. See that skill for the check vocabulary.

```toml
[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "Phase \\| Agent \\| Artifact \\| Gate"

[[check]]
kind = "file_contains"
path = "SKILL.md"
pattern = "Never auto-advances"
```
