"""Tests for skills_listing (shared by mikko-help and mikko-skills).

Run from the skill root:
    python -m unittest discover -s tests

Stdlib only, no third-party deps. Compatible with Python 3.11+.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# skills_listing lives in ../_lib/ in the source repo and as a sibling of this
# skill after install. Add both candidate locations to the path.
_HERE = Path(__file__).resolve()
for _cand in (_HERE.parents[1], _HERE.parents[2] / "_lib"):
    if (_cand / "skills_listing.py").is_file():
        sys.path.insert(0, str(_cand))
        break

import skills_listing as sl  # noqa: E402


def _make_skill(skills_root: Path, name: str, description: str = "Does a thing.",
                barney: str | None = None) -> None:
    d = skills_root / name
    d.mkdir(parents=True, exist_ok=True)
    fm = [f"name: {name}", f"description: {description}"]
    if barney is not None:
        fm.append(f"barney: {barney}")
    (d / "SKILL.md").write_text("---\n" + "\n".join(fm) + "\n---\n\n# body\n")


class FrontmatterTests(unittest.TestCase):
    def test_parses_three_fields(self):
        fm = sl.parse_frontmatter("---\nname: foo\ndescription: A b.\nbarney: hi\n---\nbody")
        self.assertEqual(fm, {"name": "foo", "description": "A b.", "barney": "hi"})

    def test_no_frontmatter_returns_empty(self):
        self.assertEqual(sl.parse_frontmatter("# just a heading\n"), {})

    def test_ignores_indented_block_scalar_lines(self):
        # An indented line belongs to a previous key's block and must not be
        # mistaken for a field.
        fm = sl.parse_frontmatter("---\nname: foo\ndescription: x\n  not_a_field: y\n---\n")
        self.assertNotIn("not_a_field", fm)
        self.assertEqual(fm["name"], "foo")


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.cwd = self.root / "proj"
        (self.home / ".claude" / "skills").mkdir(parents=True)
        (self.cwd / ".claude" / "skills").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_mikko_prefixed_and_sorted(self):
        root = self.home / ".claude" / "skills"
        _make_skill(root, "mikko-zed")
        _make_skill(root, "mikko-alpha")
        _make_skill(root, "other-skill")  # no mikko- prefix → excluded
        names = [s.name for s in sl.discover_skills(self.cwd, self.home)]
        self.assertEqual(names, ["mikko-alpha", "mikko-zed"])

    def test_project_local_overrides_user_wide(self):
        _make_skill(self.home / ".claude" / "skills", "mikko-dup", description="user copy")
        _make_skill(self.cwd / ".claude" / "skills", "mikko-dup", description="project copy")
        skills = sl.discover_skills(self.cwd, self.home)
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].scope, "project")
        self.assertIn("(project)", sl.render_table(skills))


class RenderTests(unittest.TestCase):
    def _skills(self):
        return [
            sl.Skill("mikko-audit", "Find bugs in the code.", "Looks for bugs.", "user"),
            sl.Skill("mikko-help", "List skills.", None, "user"),
        ]

    def test_table_default_uses_description(self):
        out = sl.render_table(self._skills())
        self.assertIn("mikko-audit", out)
        self.assertIn("Find bugs in the code.", out)

    def test_table_barney_falls_back_when_missing(self):
        out = sl.render_table(self._skills(), barney=True)
        self.assertIn("Looks for bugs.", out)
        self.assertIn("(no barney)", out)  # mikko-help has no barney field

    def test_barney_list_layout(self):
        out = sl.render_barney_list(self._skills())
        self.assertIn("mikko-audit", out)
        self.assertIn("    Looks for bugs.", out)  # indented barney line

    def test_empty_message(self):
        self.assertIn("no mikko-* skills installed", sl.render_table([]))
        self.assertIn("no mikko-* skills installed", sl.render_barney_list([]))


class DetectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _pkg(self, deps: dict, dev: dict | None = None):
        import json
        (self.cwd / "package.json").write_text(
            json.dumps({"dependencies": deps, "devDependencies": dev or {}}))

    def test_react_app_recommends_react_audit_first(self):
        self._pkg({"react": "18", "react-dom": "18"})
        shape = sl.fingerprint(self.cwd)
        self.assertTrue(shape["react"])
        recs = [a for a, _ in sl.recommend_audits(shape)]
        self.assertEqual(recs[0], "react-anti-patterns-audit")

    def test_security_deps_lift_security_audit(self):
        self._pkg({"express": "4", "pg": "8"})
        shape = sl.fingerprint(self.cwd)
        self.assertTrue(shape["security_sensitive"])
        recs = [a for a, _ in sl.recommend_audits(shape)]
        self.assertIn("security-audit", recs)

    def test_plain_python_is_universal_only(self):
        (self.cwd / "requirements.txt").write_text("requests\n")
        shape = sl.fingerprint(self.cwd)
        self.assertIn("Python", shape["languages"])
        recs = [a for a, _ in sl.recommend_audits(shape)]
        self.assertEqual(recs, ["audit", "ai-codegen-smell-audit"])


if __name__ == "__main__":
    unittest.main()
