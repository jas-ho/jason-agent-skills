"""Exercise launch constructors with fake harness functions, never real sessions."""

import importlib.util
import json
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "spawn_tmux_agents.py"
spec = importlib.util.spec_from_file_location("spawn_tmux_agents", MODULE)
assert spec is not None and spec.loader is not None
spawn = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(spawn)
SID = "01a094a5-618a-7000-a76d-5e509ca828b2"


class CommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Retained in the repo's ignored scratch area for inspection.
        scratch = MODULE.parents[3] / "tmp"
        scratch.mkdir(exist_ok=True)
        cls.work = Path(tempfile.mkdtemp(prefix="spawn-constructor-", dir=scratch))
        cls.capture = cls.work / "capture.py"
        cls.capture.write_text("import json,sys\nprint(json.dumps(sys.argv[1:]))\n")
        cls.prompt = cls.work / "prompt ' spaced.txt"
        cls.message = (
            'literal $(touch never-created) `echo no` "quotes"\nsecond line $HOME'
        )
        cls.prompt.write_text(cls.message)

    def captured(self, agent, branch=False, resume=None, model=None):
        command = spawn.build_command(agent, branch, resume, model, str(self.prompt))
        fake = f'{agent}() {{ python3 {shlex.quote(str(self.capture))} "$@"; }}\ntrash() {{ :; }}\n'
        result = subprocess.run(
            ["bash", "-c", fake + command],
            cwd=self.work,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.work / "never-created").exists())
        return json.loads(result.stdout)

    def test_fresh_preserves_literal_prompt(self):
        for agent in ("claude", "codex", "omp"):
            with self.subTest(agent=agent):
                self.assertEqual(self.captured(agent), ["--", self.message])

    def test_flag_shaped_prompt_remains_positional(self):
        original = self.prompt.read_text()
        try:
            self.prompt.write_text("--resume somebody-else")
            for agent in ("claude", "codex", "omp"):
                with self.subTest(agent=agent):
                    self.assertEqual(
                        self.captured(agent), ["--", "--resume somebody-else"]
                    )
        finally:
            self.prompt.write_text(original)

    def test_valid_exact_omp_modes(self):
        for identity in (SID, str(self.work / "a session.jsonl")):
            for branch in (False, True):
                with self.subTest(identity=identity, branch=branch):
                    self.assertEqual(
                        spawn.validate(
                            [
                                {
                                    "name": "test",
                                    "agent": "omp",
                                    "dir": str(self.work),
                                    "resume": identity,
                                    "branch": branch,
                                }
                            ]
                        ),
                        [],
                    )

    def test_exact_resume_and_fork(self):
        for agent in ("claude", "codex", "omp"):
            for branch in (False, True):
                with self.subTest(agent=agent, branch=branch):
                    args = self.captured(agent, branch, SID)
                    self.assertIn(SID, args)
                    self.assertEqual(args[-1], self.message)
                    expected = {
                        "claude": "--fork-session" if branch else "--resume",
                        "codex": "fork" if branch else "resume",
                        "omp": "--fork" if branch else "--resume",
                    }[agent]
                    self.assertIn(expected, args)

    def test_omp_absolute_path_is_single_argument(self):
        path = str(self.work / "session ' with spaces.jsonl")
        self.assertEqual(
            self.captured("omp", True, path, "openai-codex/gpt-6-astra"),
            ["--model", "openai-codex/gpt-6-astra", "--fork", path, "--", self.message],
        )

    def test_env_branch_pins_uuid(self):
        for agent, key in (
            ("claude", "CLAUDE_CODE_SESSION_ID"),
            ("codex", "CODEX_THREAD_ID"),
        ):
            with patch.dict(os.environ, {key: SID}):
                self.assertIn(SID, self.captured(agent, True))

    def test_no_latest_session_fallback(self):
        with patch.dict(
            os.environ, {"CLAUDE_CODE_SESSION_ID": "", "CODEX_THREAD_ID": ""}
        ):
            for agent in ("claude", "codex", "omp"):
                with self.subTest(agent=agent):
                    with self.assertRaises(ValueError):
                        spawn.build_command(agent, True, None, None, None)
                    errors = spawn.validate(
                        [
                            {
                                "name": "test",
                                "agent": agent,
                                "dir": str(self.work),
                                "prompt": "test",
                                "branch": True,
                            }
                        ]
                    )
                    self.assertTrue(errors)

    def test_rejects_ambiguous_or_option_identity(self):
        for agent in ("claude", "codex", "omp"):
            for identity in ("--last", "last", "01a094a5", "named session", SID + "\n"):
                with (
                    self.subTest(agent=agent, identity=identity),
                    self.assertRaises(ValueError),
                ):
                    spawn.build_command(agent, False, identity, None, None)

    def test_nonclaude_remote_rejected(self):
        for agent in ("codex", "omp"):
            with self.assertRaises(ValueError):
                spawn.build_command(agent, False, None, None, None, "remote")

    def test_invalid_branch_type_rejected(self):
        errors = spawn.validate(
            [
                {
                    "name": "test",
                    "agent": "omp",
                    "dir": str(self.work),
                    "resume": SID,
                    "branch": "false",
                }
            ]
        )
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
