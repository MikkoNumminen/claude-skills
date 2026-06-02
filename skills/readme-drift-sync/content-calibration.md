# readme-drift-sync — content calibration

## Content calibration (against this repo's README, 2026-05-20)

Mental run-through of the five checks against `claude-skills/README.md` at the point this skill landed (multi-skill library layout under `skills/<name>/`):

| Check | Verdict | Notes |
| --- | --- | --- |
| file-structure-drift | **NO HITS (verified)** | Paths referenced in the README (`skills/<name>/SKILL.md` per row, `docs/METHODOLOGY.md`, `install.sh`, `install-mikko.sh`, `LICENSE`) all exist. |
| dependency-drift | **N/A** | No `package.json` / `requirements.txt` / equivalent. The README claims no runtime stack — the skills are markdown recipes, not Node packages. |
| skill-drift | **GROUNDED — 2 missing additions, fixed in this PR** | `Glob` `skills/*/SKILL.md` returns 8 directories: `audit`, `ai-codegen-smell-audit`, `mikko-audit-suite`, `mikko-help`, `react-anti-patterns-audit`, `readme-drift-sync`, `security-audit`, `skill-usage`. At first calibration the README's "What's in here" table listed 6 of them; `mikko-audit-suite` and `react-anti-patterns-audit` were missing. **Fixed in this PR**: two rows added to the table during this commit, matching the format and tone of the other rows. After this PR, the table enumerates all 8 shipped skills. |
| feature-drift | **NO HITS (verified)** | README documents `./install.sh <name> --target user`, `./install.sh <name> --target project --repo <path>`, `./install.sh --list`, `./install-mikko.sh [--prefix X] [--dry-run]`. `Grep` against the two scripts confirms each flag exists. |
| status-drift | **NO HITS** | No specific count claims, no version badge, no test-coverage claim in the current README to verify against. |

**Calibration verdict.** 2 real drifts found, both minor missing-additions. This is the kind of finding the skill is meant to surface: the README quietly fell behind as PRs #3 (`react-anti-patterns-audit`) and #5 (`mikko-audit-suite`) shipped without updating the table. **Fixed in this PR** — the two rows are now in the table. The skill walks the talk on its first calibration run against its own repo.

**Calibration notes for the design:**
- The skill-drift glob now correctly covers `skills/*/` AND `.claude/skills/*/`. The first calibration of this skill (drafted on an abandoned branch) hardcoded the `.claude/skills/` path and would have returned N/A on this repo — a false negative that the recursive-irony review caught.
- The feature-drift check works well on a repo where the CLI surface is small and grep-able (install.sh + install-mikko.sh). On larger CLIs, the report should explicitly say "feature-drift skipped — too many flags/endpoints to enumerate without runtime instrumentation; flag CLI-surface drift by hand."
- Re-run this calibration whenever a PR touches either `skills/` or the README. Stale calibration is the same disease the skill is meant to cure.
