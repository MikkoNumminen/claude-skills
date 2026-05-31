"""Tests for skills-quality.

Run from the skill root:
    python -m unittest discover -s tests

Stdlib only. Python 3.11+.
"""

from __future__ import annotations

import importlib.util
import json
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


# ---------- ruleset hash tests ----------


class RulesetHashTests(unittest.TestCase):
    def test_hash_is_stable_within_run(self) -> None:
        self.assertEqual(rules.compute_ruleset_hash(), rules.compute_ruleset_hash())

    def test_hash_is_hex_sha256(self) -> None:
        h = rules.compute_ruleset_hash()
        self.assertEqual(len(h), 64)
        int(h, 16)  # raises ValueError if not hex


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


if __name__ == "__main__":
    unittest.main()
