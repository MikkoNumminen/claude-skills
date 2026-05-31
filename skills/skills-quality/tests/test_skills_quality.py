"""Tests for skills-quality.

Run from the skill root:
    python -m unittest discover -s tests

Stdlib only. Python 3.11+.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _SKILL_ROOT / "skills-quality.py"

# Load the hyphenated script as a module. The script's own preamble adds the
# shared-lib path; we just need to feed it the right __file__ so that path
# resolution works during import.
_spec = importlib.util.spec_from_file_location("skills_quality", _SCRIPT)
assert _spec is not None and _spec.loader is not None
skills_quality = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skills_quality)

# rules is already on sys.path from skills_quality's import preamble.
import rules  # noqa: E402


def _make_skill(
    scope_root: Path,
    name: str,
    body: str | None = None,
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Create a skill dir with a SKILL.md and optional sibling files."""
    skill_dir = scope_root / ".claude" / "skills" / name
    skill_dir.mkdir(parents=True)
    if body is None:
        body = (
            "---\n"
            f"name: {name}\n"
            "description: test skill\n"
            "---\n\n"
            "# When to use\n\nTest.\n"
        )
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    for fname, fbody in (extra_files or {}).items():
        (skill_dir / fname).write_text(fbody, encoding="utf-8")
    return skill_dir


# ---------- rule unit tests ----------


class RuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="quality-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _content(self, name: str, **kw) -> rules.SkillContent:
        skill = _make_skill(self.tmp, name, **kw)
        c = rules.build_content(skill)
        assert c is not None
        return c

    def test_missing_frontmatter_fires(self) -> None:
        c = self._content("bad", body="# No frontmatter at all\n")
        result = rules.rule_missing_frontmatter(c)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "high")

    def test_missing_frontmatter_field_fires(self) -> None:
        body = "---\nname: foo\n---\n\n# When to use\n\nTest.\n"
        c = self._content("foo", body=body)
        result = rules.rule_missing_frontmatter(c)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "high")
        self.assertIn("description", result[1])

    def test_missing_frontmatter_passes(self) -> None:
        c = self._content("good")
        self.assertIsNone(rules.rule_missing_frontmatter(c))

    def test_long_imperative_no_script_fires(self) -> None:
        loops = "\n".join(
            [f"- For each item {i}, do something." for i in range(10)]
        )
        body = f"---\nname: looper\ndescription: x\n---\n\n{loops}\n"
        c = self._content("looper", body=body)
        result = rules.rule_long_imperative_no_script(c)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "high")

    def test_long_imperative_passes_when_script_present(self) -> None:
        loops = "\n".join(
            [f"- For each item {i}, do something." for i in range(10)]
        )
        body = f"---\nname: looper\ndescription: x\n---\n\n{loops}\n"
        c = self._content(
            "looper", body=body, extra_files={"helper.py": "print('ok')\n"}
        )
        self.assertIsNone(rules.rule_long_imperative_no_script(c))

    def test_imperative_prose_no_script_medium_band(self) -> None:
        # 3 hits, no script -> medium
        loops = "- For each x\n- iterate over y\n- step through z\n"
        body = f"---\nname: m\ndescription: x\n---\n\n{loops}"
        c = self._content("m", body=body)
        result = rules.rule_imperative_prose_no_script(c)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "medium")

    def test_very_long_skill_fires(self) -> None:
        long_body = (
            "---\nname: l\ndescription: x\n---\n\n"
            + ("filler\n" * (rules.VERY_LONG_LINES + 10))
        )
        c = self._content("l", body=long_body)
        result = rules.rule_very_long_skill(c)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "medium")

    def test_code_block_count_ignores_example_loops(self) -> None:
        # Loop prose inside fenced code must not trigger the count.
        body = (
            "---\nname: ex\ndescription: x\n---\n\n"
            "Normal prose.\n\n"
            "```python\nfor each in items:\n    iterate(each)\n    iterate(each)\n```\n"
        )
        c = self._content("ex", body=body)
        self.assertEqual(c.loop_prose_count, 0)

    def test_tilde_fences_also_stripped(self) -> None:
        # Regression: CommonMark allows ~~~ fences. They must be stripped too.
        body = (
            "---\nname: tilde\ndescription: x\n---\n\n"
            "Normal prose.\n\n"
            "~~~python\nfor each in items:\n    iterate(each)\n~~~\n"
        )
        c = self._content("tilde", body=body)
        self.assertEqual(c.loop_prose_count, 0)

    def test_extended_loop_patterns_caught(self) -> None:
        # Regression: the expanded catalog captures more LLM-as-loop shapes.
        body = (
            "---\nname: extended\ndescription: x\n---\n\n"
            "First, process each entry. Then handle each result. "
            "Review each finding. Check each path. Examine each module. "
            "Repeat one by one, in turn.\n"
        )
        c = self._content("extended", body=body)
        # 6 patterns above; the rule should fire HIGH (>= LOOP_PROSE_HIGH_THRESHOLD).
        self.assertGreaterEqual(c.loop_prose_count, rules.LOOP_PROSE_HIGH_THRESHOLD)

    def test_frontmatter_value_does_not_bleed_into_next_key(self) -> None:
        # Regression: original regex `(.*?)$` was loose enough that multi-line
        # values could bleed. Empty value lines no longer match as fields.
        body = "---\nname:\ndescription: real desc\n---\n\nbody\n"
        c = self._content("empty_name", body=body)
        # 'name' has no value -> NOT extracted as a field. missing_frontmatter fires.
        self.assertNotIn("name", c.frontmatter)
        self.assertEqual(c.frontmatter.get("description"), "real desc")

    def test_excessive_code_blocks_fires(self) -> None:
        many_fences = "\n\n".join(
            f"```python\nx = {i}\n```" for i in range(rules.CODE_BLOCK_HIGH_THRESHOLD + 5)
        )
        body = f"---\nname: cb\ndescription: x\n---\n\n{many_fences}\n"
        c = self._content("cb", body=body)
        result = rules.rule_excessive_code_blocks(c)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "medium")

    # ---- cost-trap rules (added 2026-05-31) ----

    def test_unlimited_read_fires_on_plain_imperative(self) -> None:
        body = (
            "---\nname: x\ndescription: y\n---\n\n"
            "# Workflow\n\n## Step 1\n\nRead each SKILL.md and check the frontmatter.\n"
        )
        c = self._content("ur", body=body)
        result = rules.rule_unlimited_read_in_procedure(c)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "medium")

    def test_unlimited_read_passes_with_limit_guard_nearby(self) -> None:
        body = (
            "---\nname: x\ndescription: y\n---\n\n"
            "# Workflow\n\nRead each SKILL.md with `limit=80` to skim only the frontmatter.\n"
        )
        c = self._content("ur2", body=body)
        self.assertIsNone(rules.rule_unlimited_read_in_procedure(c))

    def test_unlimited_read_passes_with_skim_guard(self) -> None:
        body = (
            "---\nname: x\ndescription: y\n---\n\n"
            "Read each flagged SKILL.md — a 10-second skim is enough.\n"
        )
        c = self._content("ur3", body=body)
        self.assertIsNone(rules.rule_unlimited_read_in_procedure(c))

    def test_uncapped_followup_fires(self) -> None:
        body = (
            "---\nname: x\ndescription: y\n---\n\n"
            "# Workflow\n\nVerify each referenced path exists on disk.\n"
        )
        c = self._content("uc", body=body)
        result = rules.rule_uncapped_followup(c)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "medium")

    def test_uncapped_followup_passes_with_max_guard(self) -> None:
        body = (
            "---\nname: x\ndescription: y\n---\n\n"
            "Verify each referenced path exists — at most 3 traces total, "
            "don't chase into source repos.\n"
        )
        c = self._content("uc2", body=body)
        self.assertIsNone(rules.rule_uncapped_followup(c))

    def test_uncapped_followup_passes_with_one_per_finding(self) -> None:
        body = (
            "---\nname: x\ndescription: y\n---\n\n"
            "Check each cited file — one ls per finding, no spelunking.\n"
        )
        c = self._content("uc3", body=body)
        self.assertIsNone(rules.rule_uncapped_followup(c))

    def test_batch_invitation_fires(self) -> None:
        body = (
            "---\nname: x\ndescription: y\n---\n\n"
            "# Workflow\n\nRead the flagged files in parallel.\n"
        )
        c = self._content("bi", body=body)
        result = rules.rule_batch_invitation(c)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "medium")

    def test_batch_invitation_passes_with_single_batch_guard(self) -> None:
        body = (
            "---\nname: x\ndescription: y\n---\n\n"
            "Read the flagged files in parallel — in a single batch, don't stage.\n"
        )
        c = self._content("bi2", body=body)
        self.assertIsNone(rules.rule_batch_invitation(c))

    def test_cost_trap_rules_dont_flag_skills_quality_own_skillmd(self) -> None:
        # Regression guard: the very SKILL.md that documents these rules
        # must itself be clean by them, or the next ruleset bump flags
        # skills-quality as a cost-trap offender (false positive on its
        # own docs).
        own = _SKILL_ROOT / "SKILL.md"
        if not own.exists():
            self.skipTest("SKILL.md not present in test layout")
        body = own.read_text(encoding="utf-8")
        skill_dir = _make_skill(self.tmp, "sq", body=body)
        c = rules.build_content(skill_dir)
        assert c is not None
        self.assertIsNone(rules.rule_unlimited_read_in_procedure(c))
        self.assertIsNone(rules.rule_uncapped_followup(c))
        self.assertIsNone(rules.rule_batch_invitation(c))

    def test_cost_trap_rules_dont_flag_skills_freshness_skillmd(self) -> None:
        # Symmetric regression guard for skills-freshness/SKILL.md, which
        # this same PR tightened with the guard wording. A future re-word
        # that drops `limit=80` or "max 3 traces total" must surface here.
        sf = _SKILL_ROOT.parent / "skills-freshness" / "SKILL.md"
        if not sf.exists():
            self.skipTest("skills-freshness/SKILL.md not present in test layout")
        body = sf.read_text(encoding="utf-8")
        skill_dir = _make_skill(self.tmp, "sf", body=body)
        c = rules.build_content(skill_dir)
        assert c is not None
        self.assertIsNone(rules.rule_unlimited_read_in_procedure(c))
        self.assertIsNone(rules.rule_uncapped_followup(c))
        self.assertIsNone(rules.rule_batch_invitation(c))

    def test_uncapped_followup_passes_with_smart_apostrophe_guard(self) -> None:
        # Regression: autocorrect / paste-in text commonly produces the
        # right-single-quote (U+2019) instead of straight ASCII. The
        # CAP_GUARD_RE char class must accept both. Earlier code review
        # caught a version where the class was three copies of straight
        # ASCII — silently dropping smart-quote text on the floor.
        #
        # The body deliberately contains ONLY the smart-quote-guard ("don’t
        # chase") — no `stop after N` / `at most N` / `one ls per` co-guard
        # — so this test fails the moment the smart-quote alternation
        # regresses. A prior draft stacked a second guard alongside the
        # smart-quote one and silently passed via the unrelated alternative.
        body = (
            "---\nname: x\ndescription: y\n---\n\n"
            "Verify each cited path — don’t chase into source repos.\n"
        )
        c = self._content("uc_smart", body=body)
        self.assertIsNone(rules.rule_uncapped_followup(c))

    def test_batch_invitation_passes_with_smart_apostrophe_guard(self) -> None:
        # Same regression for BATCH_GUARD_RE's don['’]t alternation. As
        # above, body uses ONLY the smart-quote guard — no `single batch`
        # / `one batch` / `all at once` co-guard — so the test exercises
        # the smart-quote path and only the smart-quote path.
        body = (
            "---\nname: x\ndescription: y\n---\n\n"
            "Read the flagged files in parallel — don’t stage.\n"
        )
        c = self._content("bi_smart", body=body)
        self.assertIsNone(rules.rule_batch_invitation(c))

    def test_guard_before_imperative_is_invisible_forward_window(self) -> None:
        # Pins the documented forward-only window behavior in
        # _matches_without_nearby_guard. A caveat written BEFORE the
        # imperative must NOT satisfy the guard — only guidance inline
        # or downstream counts. If someone changes the helper to look
        # bidirectionally, this test will break — and that's the point:
        # the breakage is a forcing function for an explicit decision,
        # not an accident to silently fix.
        body = (
            "---\nname: x\ndescription: y\n---\n\n"
            "Use limit=80 when needed. Read each SKILL.md and check the "
            "frontmatter.\n"
        )
        # 'limit=80' lands BEFORE 'read each SKILL.md', so the guard
        # check inside the forward window finds no LIMIT_GUARD hit — rule
        # must fire.
        c = self._content("fw_before", body=body)
        result = rules.rule_unlimited_read_in_procedure(c)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "medium")


# ---------- ruleset hash tests ----------


class RulesetHashTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="quality-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_hash_is_stable_within_run(self) -> None:
        self.assertEqual(rules.compute_ruleset_hash(), rules.compute_ruleset_hash())

    def test_hash_is_hex_sha256(self) -> None:
        h = rules.compute_ruleset_hash()
        self.assertEqual(len(h), 64)
        int(h, 16)  # raises ValueError if not hex

    def test_hash_changes_when_rules_file_changes(self) -> None:
        # End-to-end pin: a real edit to a rules file produces a different
        # hash. Complements test_ruleset_change_re_surfaces_unchanged_skill,
        # which uses a synthetic hash and so doesn't exercise the function.
        p1 = self.tmp / "rules_a.py"
        p2 = self.tmp / "rules_b.py"
        p1.write_text("# version 1\nRULES = []\n", encoding="utf-8")
        p2.write_text("# version 2\nRULES = []\n", encoding="utf-8")
        self.assertNotEqual(
            rules.compute_ruleset_hash(p1),
            rules.compute_ruleset_hash(p2),
        )
        # And same content -> same hash.
        p2.write_text("# version 1\nRULES = []\n", encoding="utf-8")
        self.assertEqual(
            rules.compute_ruleset_hash(p1),
            rules.compute_ruleset_hash(p2),
        )


# ---------- audit_scope integration tests ----------


class AuditScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="quality-test-"))
        self.ruleset_hash = rules.compute_ruleset_hash()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_run_clean_skill_surfaces_as_changed(self) -> None:
        _make_skill(self.tmp, "alpha")  # frontmatter present, no smells
        report = skills_quality.audit_scope("project", self.tmp, self.ruleset_hash)
        self.assertEqual(len(report["findings"]), 1)
        f = report["findings"][0]
        self.assertEqual(f["status"], "changed")  # new => "changed" before baseline
        self.assertEqual(f["pre_findings"], [])
        self.assertTrue(f["needs_llm_review"])  # changed => LLM review

    def test_baseline_then_clean_audit_skips(self) -> None:
        _make_skill(self.tmp, "alpha")
        report = skills_quality.audit_scope("project", self.tmp, self.ruleset_hash)
        skills_quality.save_manifest(
            Path(report["manifest_path"]), report["new_manifest"]
        )
        report2 = skills_quality.audit_scope("project", self.tmp, self.ruleset_hash)
        self.assertEqual(report2["findings"], [])

    def test_ruleset_change_re_surfaces_unchanged_skill(self) -> None:
        """The whole point: a ruleset change must re-enter every skill."""
        _make_skill(self.tmp, "alpha")
        report = skills_quality.audit_scope("project", self.tmp, self.ruleset_hash)
        skills_quality.save_manifest(
            Path(report["manifest_path"]), report["new_manifest"]
        )
        # Simulate a ruleset edit by passing a different hash.
        different_hash = "f" * 64
        report2 = skills_quality.audit_scope("project", self.tmp, different_hash)
        self.assertEqual(len(report2["findings"]), 1)
        self.assertEqual(report2["findings"][0]["status"], "changed")

    def test_flagged_skill_surfaces_high(self) -> None:
        body = "# Missing frontmatter entirely\n"
        _make_skill(self.tmp, "no_fm", body=body)
        report = skills_quality.audit_scope("project", self.tmp, self.ruleset_hash)
        self.assertEqual(len(report["findings"]), 1)
        f = report["findings"][0]
        self.assertEqual(f["status"], "flagged")
        self.assertTrue(any(pf["severity"] == "high" for pf in f["pre_findings"]))
        self.assertTrue(f["needs_llm_review"])

    def test_flagged_then_fixed_surfaces_as_changed(self) -> None:
        """User fixed a flagged skill; new hash + clean pre-pass => 'changed'.

        (The earlier 'now-clean' branch was unreachable under deterministic
        rules and got removed; this test pins the actual flagged->fixed path.)
        """
        body = "# No frontmatter\n"
        skill = _make_skill(self.tmp, "fixme", body=body)
        report = skills_quality.audit_scope("project", self.tmp, self.ruleset_hash)
        skills_quality.save_manifest(
            Path(report["manifest_path"]), report["new_manifest"]
        )
        (skill / "SKILL.md").write_text(
            "---\nname: fixme\ndescription: now ok\n---\n\nFixed.\n",
            encoding="utf-8",
        )
        report2 = skills_quality.audit_scope("project", self.tmp, self.ruleset_hash)
        self.assertEqual(len(report2["findings"]), 1)
        self.assertEqual(report2["findings"][0]["status"], "changed")
        self.assertEqual(report2["findings"][0]["pre_findings"], [])

    def test_removed_skill_surfaces(self) -> None:
        skill = _make_skill(self.tmp, "doomed")
        report = skills_quality.audit_scope("project", self.tmp, self.ruleset_hash)
        skills_quality.save_manifest(
            Path(report["manifest_path"]), report["new_manifest"]
        )
        shutil.rmtree(skill)
        report2 = skills_quality.audit_scope("project", self.tmp, self.ruleset_hash)
        statuses = {f["name"]: f["status"] for f in report2["findings"]}
        self.assertEqual(statuses, {"doomed": "removed"})


# ---------- manifest schema tests ----------


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="quality-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_corrupt_manifest_soft_handled(self) -> None:
        path = self.tmp / "broken.json"
        path.write_text("not json {{{", encoding="utf-8")
        m = skills_quality.load_manifest(path)
        self.assertEqual(m["skills"], {})

    def test_entry_missing_ruleset_hash_filtered(self) -> None:
        path = self.tmp / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "ruleset_hash": "abc",
                    "skills": {
                        "good": {
                            "skill_hash": "x",
                            "ruleset_hash_at_review": "abc",
                            "pre_pass": "clean",
                        },
                        "missing_ruleset": {"skill_hash": "y"},
                        "missing_skill_hash": {"ruleset_hash_at_review": "abc"},
                    },
                }
            ),
            encoding="utf-8",
        )
        m = skills_quality.load_manifest(path)
        self.assertEqual(set(m["skills"].keys()), {"good"})


@unittest.skipUnless(
    hasattr(os, "symlink") and sys.platform != "win32",
    "symlinks require POSIX or Windows admin/dev-mode",
)
class SymlinkDefenseTests(unittest.TestCase):
    """POSIX-only: rules.build_content must not follow symlinked dirs.

    Mirrors the equivalent SymlinkTests in skills-freshness — the script's
    has_companion_script logic uses os.walk(followlinks=False), and a
    symlink to a tree containing a .py file must not flip has_script to
    True.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="quality-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_symlinked_dir_with_script_does_not_set_has_script(self) -> None:
        # External tree containing a .py file - if the walk followed
        # symlinked dirs, has_script would flip True.
        external = self.tmp / "external"
        external.mkdir()
        (external / "intruder.py").write_text("# imported from outside\n", encoding="utf-8")

        skill = _make_skill(self.tmp, "no_real_script")
        (skill / "link_to_external").symlink_to(external, target_is_directory=True)

        c = rules.build_content(skill)
        assert c is not None
        self.assertFalse(c.has_script if hasattr(c, "has_script") else c.has_companion_script)

    def test_symlinked_dir_cycle_does_not_hang(self) -> None:
        skill = _make_skill(self.tmp, "cyclic")
        (skill / "loop").symlink_to(skill, target_is_directory=True)
        c = rules.build_content(skill)
        assert c is not None
        # If followlinks were True this would infinite-loop or raise.
        self.assertFalse(c.has_companion_script)


class LibDiscoveryTests(unittest.TestCase):
    """Verify the script's preamble can locate skills_audit_lib via either
    candidate (sibling install vs source-tree layout) by physically setting
    up each layout in a tempdir and importing the script in a subprocess.

    Subprocess isolation matters: the test process already has the lib
    imported and the path on sys.path from skills-quality's own preamble.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="quality-test-"))
        # Source files we'll vendor into each layout.
        self.lib_src = _SKILL_ROOT.parent / "_lib" / "skills_audit_lib.py"
        self.rules_src = _SKILL_ROOT / "rules.py"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_script(self, script_path: Path) -> tuple[int, str, str]:
        import subprocess

        proc = subprocess.run(
            [sys.executable, str(script_path), "--scope", "global", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def test_sibling_lib_layout_imports(self) -> None:
        # install-mikko.sh (copy) layout: lib + rules + script all flat siblings.
        flat = self.tmp / "mikko-skills-quality"
        flat.mkdir()
        shutil.copy(self.lib_src, flat / "skills_audit_lib.py")
        shutil.copy(self.rules_src, flat / "rules.py")
        shutil.copy(_SCRIPT, flat / "skills-quality.py")
        rc, _out, err = self._run_script(flat / "skills-quality.py")
        self.assertNotIn("ImportError", err, msg=err)
        # rc may be 0 or 1 depending on global skill state; both indicate the
        # script ran past its imports.
        self.assertIn(rc, (0, 1), msg=f"rc={rc} stderr={err}")

    def test_parent_lib_layout_imports(self) -> None:
        # install.sh (symlink) / source-repo layout: lib at ../_lib/ relative
        # to the script.
        skill_dir = self.tmp / "skills" / "skills-quality"
        lib_dir = self.tmp / "skills" / "_lib"
        skill_dir.mkdir(parents=True)
        lib_dir.mkdir(parents=True)
        shutil.copy(self.lib_src, lib_dir / "skills_audit_lib.py")
        shutil.copy(self.rules_src, skill_dir / "rules.py")
        shutil.copy(_SCRIPT, skill_dir / "skills-quality.py")
        rc, _out, err = self._run_script(skill_dir / "skills-quality.py")
        self.assertNotIn("ImportError", err, msg=err)
        self.assertIn(rc, (0, 1), msg=f"rc={rc} stderr={err}")


if __name__ == "__main__":
    unittest.main()
