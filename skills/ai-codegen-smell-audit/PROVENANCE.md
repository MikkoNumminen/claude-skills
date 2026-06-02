# ai-codegen-smell-audit — provenance

## Provenance: original calibration against AudiobookMaker (2026-05-17)

The skill was authored inside [AudiobookMaker](https://github.com/MikkoNumminen/AudiobookMaker)
and the first calibration ran against its `src/` tree on 2026-05-17. The
table below is the empirical evidence the skill carried with it when it
was promoted to the `claude-skills` library — concrete file:line citations
showing which of the ten checks fired (or didn't) on a real codebase that
had already been human-reviewed.

Citations were verified by spot-reading each cited line in the AudiobookMaker
working tree on 2026-05-17, not by grep alone — any "GROUNDED" row below
names a specific line the original auditor could open and see the pattern.

This is provenance, not a claim that any of the ten checks are inherently
grounded in AudiobookMaker. A fresh calibration run against any codebase
will produce a different shape. The value of keeping this table in the
library SKILL.md is showing readers what a real run looks like before they
invoke it on their own code.

| Check | Verdict on this repo | Concrete hit (when grounded) |
|---|---|---|
| defensive-checks-for-impossible-cases | **NO HITS** | No function-parameter type guard that contradicts its annotation found in a sampled sweep — kept because the check is grounded in generated code generally and will fire on fresh AI diffs |
| stylistic-drift-within-file | **GROUNDED (fixed in PR #67)** | `src/cleanup.py:106` used `os.path.getsize(os.path.join(...))` while the rest of the same file built paths via `Path()`; rewritten to `(Path(root) / f).stat().st_size` and confirmed in the 2026-05-17-v2 second-run audit |
| paraphrase-comments | **NO HITS** | None found — codebase has been human-reviewed |
| single-use-helpers | **MIXED** | No clean false-positive, no clean true-positive in samples — needs full call-graph analysis to confirm either way |
| generic-names-in-domain-context | **GROUNDED (fixed in PR #67)** | `src/auto_updater.py:253` had `data = json.loads(...)` for a GitHub release response — subsequent code read `data.get("tag_name")`, `data.get("assets", [])`. Renamed to `release_data` across the six reads in `check_for_update`; confirmed in the 2026-05-17-v2 second-run audit |
| swallowed-errors | **PATTERN WIDESPREAD, SAMPLED CALIBRATION-IMMUNE** | `except Exception: pass` and `except Exception: return <default>` shapes appear at ~40 sites across ~20 files in `src/` (desktop GUI + optional-import + subprocess teardown make these common). Three sampled and confirmed calibration-immune: `src/engine_registry.py:36-37` (optional-import swallow, preceded by an explicit comment block); `src/engine_installer.py:795-796` (best-effort subprocess kill cleanup, inside an outer error handler); `src/app_config.py:29-30` (locale fallback, rationale in the function docstring). Bare `except:` (no exception type) is genuinely absent. A full enumeration was NOT done — the sample is illustrative, not exhaustive, and some unsampled sites may lack a rationale comment. The first-pass calibration claimed "NO HITS" outright — that was wrong on the literal pattern; this entry was rewritten 2026-05-19 after a post-merge skeptical review surfaced the misclaim, and tightened further the same day after a second adversarial pass revealed the original correction undercounted by ~10x |
| mirror-tests | **NO HITS** | Sampled `test_tts_normalizer_fi.py`, `test_tts_audio.py`, `test_cleanup.py`, `test_tts_chunking.py` — all assert real behaviour |
| phantom-todos | **NO HITS** | Zero `# TODO` / `# FIXME` in `src/` |
| duplicated-helpers | **UNCLEAR** | `tts_normalizer_fi.py` has many similar regex builders, but they are intentionally distinct passes — would need cross-module similarity analysis to confirm |
| over-typed-primitives | **NO HITS** | No `Literal` / `NewType` / `TypedDict` overuse — codebase uses plain dataclasses |

**Calibration verdict.** Only 2 of the 10 checks turn up verified
hits in `src/` today (stylistic-drift, generic-names). The other 8
either find nothing here (the codebase has been hand-reviewed) or
are mixed/unclear pending finer analysis. The "NO HITS" checks stay
in the skill because they are grounded against LLM-codegen
*generally* — they target patterns documented in independent reviews
of generated code and will fire on a fresh AI diff that has not
been hand-reviewed. This skill is most useful on those diffs, not on
a codebase that has already had careful human review.

**Honest caveat.** A more aggressive calibration sweep — full
call-graph analysis for single-use-helpers, structural similarity
analysis across modules for duplicated-helpers, function-signature
parsing for defensive-checks — would likely surface more grounded
hits. The 2/10 number is a floor, not a ceiling.

**Second-run verification (2026-05-17, post-PR #67).** A second
audit ran the same 4-parallel-sub-agent pattern against `src/` after
both first-run findings were fixed. Both citations now point at
clean code (`(Path(root) / f).stat().st_size` and `release_data =
json.loads(...)` respectively). The second-run sweep reported zero
new findings on the other nine checks. Two later skeptical
re-reviews on 2026-05-19 surfaced additional misses that neither
self-review caught: the `swallowed-errors` calibration row was wrong
on the literal pattern (now corrected, see table above), and the
first correction undercounted the affected sites ~10x. Honest
summary: the self-review loop did NOT catch its own blind spots —
**external skeptical re-review** is what surfaced both misclaims.
That review pattern (re-audit after merge by a different agent) is
now part of the AI-first cadence documented in
`docs/AI_FIRST_GUIDE.md` (AudiobookMaker — not present in this
library). This is
one repo over a few days; the calibration table is one data point,
not validated empirics. Full second-run report at
`docs/audits/ai-smell-2026-05-17-v2.md` (AudiobookMaker — not present
in this library).

**One pattern observed in `src/` that is NOT in the ten checks** —
a candidate for a future check once it shows up across multiple
repos: `src/voice_pack/expression.py:72-78` has a `frozen=True`
dataclass whose `__post_init__` uses `object.__setattr__` to clamp
values rather than validate or raise. Signal of "I wanted validation
but did not want to write a custom `__init__`." A future check
`post-init-mutation-workaround` could target this, but a single
observation in a single repo is not enough evidence to promote it.
The "Patterns observed but not in the checklist" section in the
report exists exactly so future runs accumulate that evidence
before the skill grows.
