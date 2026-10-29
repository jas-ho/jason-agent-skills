"""Offline regressions; all staging and commits are confined to temporary repos."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("safe_commit.sh")


class SafeCommitTests(unittest.TestCase):
    def setUp(self):
        scratch = SCRIPT.parents[2] / "tmp"
        scratch.mkdir(exist_ok=True)
        # Retain isolated fixtures in ignored scratch, as other repo tests do.
        self.root = Path(tempfile.mkdtemp(prefix="safe-commit-", dir=scratch))
        self.env = dict(
            os.environ,
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_ATTR_NOSYSTEM="1",
            TEST_GIT=os.environ.get("TEST_GIT") or shutil.which("git"),
        )
        self.git("init", "--template=", "-q")
        self.git("config", "user.email", "fixture@example.org")
        self.git("config", "user.name", "Fixture")
        for name in ("example.sh", "example.py", "example.md", "other.txt"):
            (self.root / name).write_text("original\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture baseline")
        self.tools = self.root / "tools"
        self.tools.mkdir()
        for tool in ("wc", "tr", "grep"):
            (self.tools / tool).symlink_to(shutil.which(tool))

    def git(self, *args):
        return subprocess.check_output(
            [self.env["TEST_GIT"], *args], cwd=self.root, env=self.env, text=True
        )

    def run_check(self, formatters=True):
        # Load the actual functions, replacing only the entrypoint and external tools.
        source = SCRIPT.read_text().rsplit('main "$@"', 1)[0]
        source += "\ncheck_tools() { :; }\n"
        source += 'git() { command "$TEST_GIT" "$@"; }\n'
        source += 'curl() { echo "unexpected network" >&2; exit 99; }\n'
        if formatters:
            source += """
shfmt() { echo formatted >> "$2"; }
uv() { return 0; }
markdownlint() { return 0; }
prettier() { return 0; }
shellcheck() { echo "checked: $1"; }
"""
        return subprocess.run(
            [shutil.which("bash"), "-c", source + "\nmain\n"],
            cwd=self.root,
            env=dict(self.env, PATH=str(self.tools)),
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )

    def test_partial_staging_rejected_before_any_formatter(self):
        for suffix in ("sh", "py", "md"):
            for formatters in (False, True):
                with self.subTest(suffix=suffix, formatters=formatters):
                    self.git("reset", "--hard", "HEAD")
                    first = self.root / "a.sh"
                    first.write_text("staged first\n")
                    path = self.root / f"example.{suffix}"
                    path.write_text("staged\n")
                    self.git("add", "a.sh", path.name)
                    path.write_text("staged\nunstaged\n")
                    before = self.git("diff", "--cached")
                    result = self.run_check(formatters)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn("unstaged", result.stdout + result.stderr)
                    self.assertEqual(self.git("diff", "--cached"), before)
                    self.assertEqual(path.read_text(), "staged\nunstaged\n")
                    self.assertEqual(first.read_text(), "staged first\n")

    def test_fully_staged_file_still_gets_formatted(self):
        (self.root / "example.sh").write_text("staged\n")
        self.git("add", "example.sh")
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("show", ":example.sh"), "staged\nformatted\n")

    def test_rename_only_is_validated(self):
        self.git("mv", "example.sh", "renamed.sh")
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("checked: " + str(self.root / "renamed.sh"), result.stdout)

    def test_mixed_rename_keeps_safety_checks(self):
        self.git("mv", "example.sh", "config.local.sh")
        (self.root / "other.txt").write_text("changed\n")
        self.git("add", "other.txt")
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("LOCAL FILES DETECTED", result.stdout)
        self.assertIn("checked: " + str(self.root / "config.local.sh"), result.stdout)

    def test_sensitive_rename_is_reported(self):
        self.git("mv", "other.txt", "credentials.txt")
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SENSITIVE FILES DETECTED", result.stdout)

    def test_deletion_only_is_allowed(self):
        (self.root / "example.sh").unlink()
        self.git("add", "-u")
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("=== Validating:", result.stdout)
        self.assertIn("Files staged: 1", result.stdout)

    def test_empty_index_is_rejected(self):
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No staged changes", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
