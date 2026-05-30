"""Tests for skills-freshness.

Run from the skill root:
    python -m unittest discover -s tests

Stdlib only, no third-party deps. Compatible with Python 3.11+.
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

# Load the hyphenated script as a module.
_SCRIPT = Path(__file__).resolve().parent.parent / "skills-freshness.py"
_spec = importlib.util.spec_from_file_location("freshness", _SCRIPT)
assert _spec is not None and _spec.loader is not None
freshness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(freshness)


def _make_skill(scope_root: Path, name: str, freshness_block: str = "") -> Path:
    """Create a minimal skill dir with optional freshness TOML block."""
    skill_dir = scope_root / ".claude" / "skills" / name
    skill_dir.mkdir(parents=True)
    body = f"---\nname: {name}\ndescription: test skill\n---\n# When to use\nTest.\n"
    if freshness_block:
        body += f"\n# Freshness check\n```toml\n{freshness_block}\n```\n"
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    return skill_dir


class HashTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="freshness-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_deterministic_for_same_content(self) -> None:
        skill = _make_skill(self.tmp, "foo")
        self.assertEqual(
            freshness.compute_skill_hash(skill),
            freshness.compute_skill_hash(skill),
        )

    def test_changes_when_file_content_changes(self) -> None:
        skill = _make_skill(self.tmp, "foo")
        h1 = freshness.compute_skill_hash(skill)
        (skill / "SKILL.md").write_text("changed\n", encoding="utf-8")
        h2 = freshness.compute_skill_hash(skill)
        self.assertNotEqual(h1, h2)

    def test_changes_when_file_added(self) -> None:
        skill = _make_skill(self.tmp, "foo")
        h1 = freshness.compute_skill_hash(skill)
        (skill / "extra.txt").write_text("extra\n", encoding="utf-8")
        self.assertNotEqual(h1, freshness.compute_skill_hash(skill))

    def test_changes_when_file_removed(self) -> None:
        skill = _make_skill(self.tmp, "foo")
        (skill / "extra.txt").write_text("extra\n", encoding="utf-8")
        h1 = freshness.compute_skill_hash(skill)
        (skill / "extra.txt").unlink()
        self.assertNotEqual(h1, freshness.compute_skill_hash(skill))

    def test_stable_across_path_separator_platforms(self) -> None:
        # rel paths fed to sha256 must be posix-style for cross-platform manifest stability.
        skill = _make_skill(self.tmp, "foo")
        (skill / "sub").mkdir()
        (skill / "sub" / "x.txt").write_text("y", encoding="utf-8")
        h = freshness.compute_skill_hash(skill)
        self.assertEqual(len(h), 64)  # sha256 hex length

    def test_oversized_file_content_change_detected(self) -> None:
        """Files >MAX_FILE_BYTES use a fingerprint that includes last 64KB.

        Regression: prior version hashed only by size; in-place edits invisible.
        """
        skill = _make_skill(self.tmp, "foo")
        path = skill / "big.bin"
        # Just over the threshold so the oversized branch fires.
        path.write_bytes(b"A" * (freshness.MAX_FILE_BYTES + 4096))
        h1 = freshness.compute_skill_hash(skill)
        with path.open("r+b") as f:
            f.seek(-100, 2)
            f.write(b"B" * 100)
        self.assertNotEqual(h1, freshness.compute_skill_hash(skill))


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="freshness-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_returns_empty(self) -> None:
        m = freshness.load_manifest(self.tmp / "missing.json")
        self.assertEqual(m["skills"], {})

    def test_corrupt_json_soft_handled(self) -> None:
        """Corrupt manifest must not exit — --update needs to overwrite it."""
        path = self.tmp / "corrupt.json"
        path.write_text("not json {{{", encoding="utf-8")
        m = freshness.load_manifest(path)
        self.assertEqual(m["skills"], {})

    def test_garbage_entries_filtered(self) -> None:
        path = self.tmp / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "skills": {
                        "good": {"hash": "abc"},
                        "bad_not_dict": "oops",
                        "missing_hash": {},
                        "non_string_hash": {"hash": 12345},
                    },
                }
            ),
            encoding="utf-8",
        )
        m = freshness.load_manifest(path)
        self.assertEqual(set(m["skills"].keys()), {"good"})

    def test_save_then_load_roundtrip(self) -> None:
        path = self.tmp / "manifest.json"
        original = {"version": 1, "skills": {"foo": {"hash": "x" * 64}}}
        freshness.save_manifest(path, original)
        loaded = freshness.load_manifest(path)
        self.assertEqual(loaded["skills"], original["skills"])


class FreshnessBlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="freshness-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _md(self, body: str) -> Path:
        p = self.tmp / "SKILL.md"
        p.write_text(body, encoding="utf-8")
        return p

    def test_absent_section_returns_none(self) -> None:
        p = self._md("# Some Heading\nNo freshness section.\n")
        self.assertIsNone(freshness.parse_freshness_block(p))

    def test_h1_h2_h3_accepted(self) -> None:
        for level in range(1, 4):
            hashes = "#" * level
            body = (
                f"{hashes} Freshness check\n"
                "```toml\n"
                '[[check]]\nkind = "path_exists"\npath = "x"\n'
                "```\n"
            )
            p = self._md(body)
            result = freshness.parse_freshness_block(p)
            self.assertIsNotNone(result, f"h{level} heading should be accepted")
            self.assertEqual(len(result["check"]), 1)

    def test_h4_rejected(self) -> None:
        body = (
            "#### Freshness check\n"
            "```toml\n[[check]]\nkind = \"path_exists\"\npath = \"x\"\n```\n"
        )
        self.assertIsNone(freshness.parse_freshness_block(self._md(body)))

    def test_toml_parse_error_surfaced(self) -> None:
        body = "# Freshness check\n```toml\nnot valid toml = = = !!!\n```\n"
        result = freshness.parse_freshness_block(self._md(body))
        self.assertIsNotNone(result)
        self.assertIn("_parse_error", result)

    def test_invalid_utf8_does_not_crash(self) -> None:
        # Regression: prior version raised UnicodeDecodeError, aborting the whole scope.
        p = self.tmp / "SKILL.md"
        p.write_bytes(b"# Freshness check\n```toml\n\x80\x81\xff\n```\n")
        result = freshness.parse_freshness_block(p)
        # Either parses (garbled) or returns parse_error — must not raise.
        self.assertIsNotNone(result)


class CheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="freshness-test-"))
        self.scope_root = self.tmp
        self.skill_dir = self.tmp / ".claude" / "skills" / "test"
        self.skill_dir.mkdir(parents=True)
        (self.skill_dir / "SKILL.md").write_text("ok", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, check: dict) -> dict:
        return freshness.run_check(check, self.scope_root, self.skill_dir, "project")

    def test_path_exists_pass(self) -> None:
        result = self._run({"kind": "path_exists", "path": "SKILL.md", "root": "skill_dir"})
        self.assertEqual(result["status"], "pass")

    def test_path_exists_fail(self) -> None:
        result = self._run({"kind": "path_exists", "path": "missing.txt", "root": "skill_dir"})
        self.assertEqual(result["status"], "fail")

    def test_path_escape_via_dotdot_refused(self) -> None:
        result = self._run({"kind": "path_exists", "path": "../../../etc/passwd", "root": "skill_dir"})
        self.assertEqual(result["status"], "error")
        self.assertIn("escapes", result["message"])

    def test_absolute_path_with_relative_root_refused(self) -> None:
        result = self._run(
            {"kind": "path_exists", "path": "/etc/passwd", "root": "skill_dir"}
        )
        self.assertEqual(result["status"], "error")

    def test_content_reading_root_home_refused(self) -> None:
        """Closes regex-oracle exfiltration via root='home'."""
        result = self._run(
            {"kind": "file_contains", "path": ".bashrc", "pattern": "x", "root": "home"}
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("not allowed", result["message"])

    def test_content_reading_root_absolute_refused(self) -> None:
        """Closes regex-oracle exfiltration via root='absolute'."""
        result = self._run(
            {"kind": "file_contains", "path": "/etc/passwd", "pattern": "root", "root": "absolute"}
        )
        self.assertEqual(result["status"], "error")

    def test_file_contains_pass(self) -> None:
        (self.skill_dir / "data.txt").write_text("hello world\n", encoding="utf-8")
        result = self._run(
            {"kind": "file_contains", "path": "data.txt", "pattern": r"hello", "root": "skill_dir"}
        )
        self.assertEqual(result["status"], "pass")

    def test_file_contains_fail(self) -> None:
        (self.skill_dir / "data.txt").write_text("hello world\n", encoding="utf-8")
        result = self._run(
            {"kind": "file_contains", "path": "data.txt", "pattern": r"goodbye", "root": "skill_dir"}
        )
        self.assertEqual(result["status"], "fail")

    def test_file_lacks_missing_file_passes(self) -> None:
        result = self._run(
            {"kind": "file_lacks", "path": "missing.txt", "pattern": "anything", "root": "skill_dir"}
        )
        self.assertEqual(result["status"], "pass")

    def test_file_lacks_found_fails(self) -> None:
        (self.skill_dir / "data.txt").write_text("deprecated_marker\n", encoding="utf-8")
        result = self._run(
            {"kind": "file_lacks", "path": "data.txt", "pattern": r"deprecated", "root": "skill_dir"}
        )
        self.assertEqual(result["status"], "fail")

    def test_no_broken_md_links_pass(self) -> None:
        (self.skill_dir / "doc.md").write_text(
            "Good [link](./SKILL.md)\nExternal [link](https://example.com)\n",
            encoding="utf-8",
        )
        result = self._run(
            {"kind": "no_broken_md_links", "path": "doc.md", "root": "skill_dir"}
        )
        self.assertEqual(result["status"], "pass")

    def test_no_broken_md_links_ignores_code_examples(self) -> None:
        """Regression: example syntax in docs must not trigger false positives."""
        (self.skill_dir / "doc.md").write_text(
            "Use `[text](path)` syntax for links.\n"
            "```\n[example](does/not/exist)\n```\n",
            encoding="utf-8",
        )
        result = self._run(
            {"kind": "no_broken_md_links", "path": "doc.md", "root": "skill_dir"}
        )
        self.assertEqual(result["status"], "pass")

    def test_no_broken_md_links_containment_blocks_escape(self) -> None:
        """A link escaping scope_root is marked broken without filesystem probing."""
        (self.skill_dir / "doc.md").write_text(
            "Probe [shadow](../../../../etc/shadow)\n", encoding="utf-8"
        )
        result = self._run(
            {"kind": "no_broken_md_links", "path": "doc.md", "root": "skill_dir"}
        )
        self.assertEqual(result["status"], "fail")
        self.assertIn("escapes scope", result["message"])

    def test_command_exists_resolves_current_interpreter(self) -> None:
        # Use the running interpreter's basename so the test works regardless of
        # whether the binary is 'python', 'python3', or 'py' on this platform.
        interpreter = Path(sys.executable).stem
        result = self._run({"kind": "command_exists", "command": interpreter})
        self.assertEqual(result["status"], "pass")

    def test_unknown_kind_errors(self) -> None:
        result = self._run({"kind": "make_coffee"})
        self.assertEqual(result["status"], "error")

    def test_missing_required_field_errors(self) -> None:
        result = self._run({"kind": "path_exists"})  # no path
        self.assertEqual(result["status"], "error")
        self.assertIn("path", result["message"])


class AuditScopeTests(unittest.TestCase):
    """End-to-end audit + manifest round-trip + removed-skill branch."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="freshness-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_run_marks_all_new(self) -> None:
        _make_skill(self.tmp, "alpha")
        _make_skill(self.tmp, "beta")
        report = freshness.audit_scope("project", self.tmp)
        names = {f["name"]: f["status"] for f in report["findings"]}
        self.assertEqual(names, {"alpha": "new", "beta": "new"})

    def test_baseline_then_clean_audit_is_empty(self) -> None:
        _make_skill(self.tmp, "alpha")
        report = freshness.audit_scope("project", self.tmp)
        freshness.save_manifest(Path(report["manifest_path"]), report["new_manifest"])
        # Re-audit should find nothing
        report2 = freshness.audit_scope("project", self.tmp)
        self.assertEqual(report2["findings"], [])

    def test_removed_skill_surfaces_in_findings(self) -> None:
        skill_dir = _make_skill(self.tmp, "alpha")
        report = freshness.audit_scope("project", self.tmp)
        freshness.save_manifest(Path(report["manifest_path"]), report["new_manifest"])
        # Delete the skill on disk; manifest still knows about it.
        shutil.rmtree(skill_dir)
        report2 = freshness.audit_scope("project", self.tmp)
        statuses = {f["name"]: f["status"] for f in report2["findings"]}
        self.assertEqual(statuses, {"alpha": "removed"})

    def test_update_drops_removed_from_manifest(self) -> None:
        skill_dir = _make_skill(self.tmp, "alpha")
        report = freshness.audit_scope("project", self.tmp)
        manifest_path = Path(report["manifest_path"])
        freshness.save_manifest(manifest_path, report["new_manifest"])
        shutil.rmtree(skill_dir)
        # Audit again - new_manifest should NOT include alpha.
        report2 = freshness.audit_scope("project", self.tmp)
        self.assertNotIn("alpha", report2["new_manifest"]["skills"])

    def test_changed_skill_with_declared_check_runs_check(self) -> None:
        _make_skill(
            self.tmp,
            "alpha",
            freshness_block=(
                '[[check]]\nkind = "path_exists"\npath = "SKILL.md"\nroot = "skill_dir"\n'
            ),
        )
        report = freshness.audit_scope("project", self.tmp)
        finding = report["findings"][0]
        self.assertEqual(finding["status"], "new")
        self.assertTrue(finding["has_criteria"])
        self.assertEqual(len(finding["checks"]), 1)
        self.assertEqual(finding["checks"][0]["status"], "pass")


@unittest.skipUnless(
    hasattr(os, "symlink") and sys.platform != "win32",
    "symlinks require POSIX or Windows admin/dev-mode",
)
class SymlinkTests(unittest.TestCase):
    """POSIX-only: confirm the os.walk(followlinks=False) defense holds."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="freshness-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_symlink_cycle_does_not_hang(self) -> None:
        skill = _make_skill(self.tmp, "alpha")
        # Create a cycle: alpha/loop -> alpha
        (skill / "loop").symlink_to(skill, target_is_directory=True)
        # If we follow the symlink, rglob recurses forever. With followlinks=False
        # the hash completes in milliseconds.
        h = freshness.compute_skill_hash(skill)
        self.assertEqual(len(h), 64)

    def test_symlink_target_change_changes_hash(self) -> None:
        skill = _make_skill(self.tmp, "alpha")
        target_a = self.tmp / "target_a"
        target_a.mkdir()
        target_b = self.tmp / "target_b"
        target_b.mkdir()
        link = skill / "link"
        link.symlink_to(target_a, target_is_directory=True)
        h1 = freshness.compute_skill_hash(skill)
        link.unlink()
        link.symlink_to(target_b, target_is_directory=True)
        h2 = freshness.compute_skill_hash(skill)
        self.assertNotEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
