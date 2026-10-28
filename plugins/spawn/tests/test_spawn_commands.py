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

    def test_non_codex_idle_constructor_is_unchanged(self):
        for agent in ("claude", "omp"):
            expected = (
                'export PATH="$HOME/.local/bin:$HOME/bin:$PATH"\n'
                f"if {agent}; then :; else st=$?; echo; "
                f'echo "{agent} exited with status $st."; '
                'echo "Press any key to close this window."; read -r -n1; fi'
            )
            self.assertEqual(
                spawn.build_command(agent, False, None, None, None), expected
            )

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
                    if agent == "codex" and not branch:
                        # the task dir wins over the thread's recorded cwd
                        self.assertIn('tui.resume_cwd="current"', args)

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

    def test_permission_mode(self):
        command = spawn.build_command("claude", False, SID, None, None, None, "auto")
        self.assertIn("--permission-mode auto", command)
        with self.assertRaises(ValueError):
            spawn.build_command(
                "claude", False, SID, None, None, None, "bypassPermissions"
            )
        errors = spawn.validate(
            [
                {
                    "name": "x",
                    "agent": "codex",
                    "resume": SID,
                    "dir": "/",
                    "permission_mode": "auto",
                }
            ]
        )
        self.assertTrue(any("permission_mode" in e for e in errors))

    def test_codex_approval_and_sandbox(self):
        fresh = spawn.build_command(
            "codex",
            False,
            None,
            None,
            "/tmp/p",
            approval="never",
            sandbox="workspace-write",
        )
        self.assertIn("codex -a never -s workspace-write", fresh)
        resumed = spawn.build_command(
            "codex", False, SID, None, None, approval="never", sandbox="read-only"
        )
        self.assertIn("-a never -s read-only", resumed)
        self.assertIn("resume", resumed)
        for agent, kwargs in (
            ("codex", {"approval": "untrusted"}),
            ("codex", {"sandbox": "danger-full-access"}),
            ("codex", {"approval": ""}),
            ("claude", {"approval": "never"}),
            ("omp", {"sandbox": "workspace-write"}),
        ):
            with self.subTest(agent=agent, **kwargs), self.assertRaises(ValueError):
                spawn.build_command(agent, False, None, None, "/tmp/p", **kwargs)
        errors = spawn.validate(
            [
                {
                    "name": "a",
                    "agent": "claude",
                    "prompt": "x",
                    "dir": "/",
                    "approval": "never",
                },
                {
                    "name": "b",
                    "agent": "codex",
                    "prompt": "x",
                    "dir": "/",
                    "sandbox": "danger-full-access",
                },
                {
                    "name": "c",
                    "agent": "codex",
                    "prompt": "x",
                    "dir": "/",
                    "approval": "never",
                    "sandbox": "workspace-write",
                },
            ]
        )
        self.assertEqual(sum("codex-only" in e for e in errors), 2, errors)

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

    def test_title_on_fresh_and_fork_not_plain_resume(self):
        title = "my-proj/some-task"
        with patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": SID}):
            for branch, resume, named in (
                (False, None, True),
                (True, None, True),
                (True, SID, True),
                (False, SID, False),
            ):
                with self.subTest(branch=branch, resume=resume):
                    command = spawn.build_command(
                        "claude", branch, resume, None, None, title, title=title
                    )
                    self.assertEqual(f"-n {title}" in command, named)
                    self.assertIn(f"--remote-control={title}", command)
        self.assertNotIn(
            f"-n {title}",
            spawn.build_command("codex", False, None, None, None, None, title=title),
        )

    def test_mode_validation(self):
        base = {"name": "t", "agent": "none", "dir": str(self.work)}
        self.assertEqual(spawn.validate([{**base, "mode": "delegated"}]), [])
        self.assertEqual(spawn.validate([base]), [])
        self.assertTrue(spawn.validate([{**base, "mode": "hidden"}]))
        self.assertTrue(spawn.validate([{**base, "mode": []}]))

    def test_delegated_uses_own_socket(self):
        calls = []

        def fake(*args, server=None, prefix=None):
            calls.append((args, server))
            out = "s:1|%1" if args[0] in ("new-window", "new-session") else ""
            return subprocess.CompletedProcess(
                args, 1 if args[0] == "has-session" else 0, out, ""
            )

        with (
            patch.object(spawn, "tmux", fake),
            patch.object(spawn, "login_shell_path_into_server"),
        ):
            entry = spawn.spawn(
                {
                    "name": "t",
                    "agent": "none",
                    "dir": str(self.work),
                    "mode": "delegated",
                }
            )
        self.assertEqual(entry["mode"], "delegated")
        self.assertTrue(calls)
        self.assertTrue(all(server == "delegated" for _, server in calls))

    def test_thinking_from_delegated_pane_goes_to_default(self):
        calls = []

        def fake(*args, server=None, prefix=None):
            calls.append(server)
            out = "s:1|%1" if args[0] in ("new-window", "new-session") else ""
            return subprocess.CompletedProcess(
                args, 1 if args[0] == "has-session" else 0, out, ""
            )

        env = {"TMUX": "/private/tmp/tmux-501/delegated,1,0"}
        with (
            patch.object(spawn, "tmux", fake),
            patch.object(spawn, "login_shell_path_into_server"),
            patch.dict(os.environ, env),
        ):
            spawn.spawn({"name": "t", "agent": "none", "dir": str(self.work)})
        self.assertTrue(calls)
        self.assertTrue(all(server == "default" for server in calls))

    def test_thinking_from_concierge_server_goes_to_default(self):
        calls = []

        def fake(*args, server=None, prefix=None):
            calls.append(server)
            out = "s:1|%1" if args[0] in ("new-window", "new-session") else ""
            return subprocess.CompletedProcess(
                args, 1 if args[0] == "has-session" else 0, out, ""
            )

        env = {"TMUX": "/tmp/tmux-1000/concierge,1,0"}
        with (
            patch.object(spawn, "tmux", fake),
            patch.object(spawn, "login_shell_path_into_server"),
            patch.dict(os.environ, env),
        ):
            spawn.spawn({"name": "t", "agent": "none", "dir": str(self.work)})
        self.assertTrue(calls)
        self.assertTrue(all(server == "default" for server in calls))

    def test_new_server_gets_scope_prefix_and_falls_back(self):
        calls = []
        scope = ["systemd-run", "--user", "--scope", "--"]

        def fake(*args, server=None, prefix=None):
            calls.append((args[0], prefix))
            if args[0] in ("has-session", "list-sessions"):
                return subprocess.CompletedProcess(args, 1, "", "")
            if args[0] == "new-session" and prefix:
                return subprocess.CompletedProcess(args, 1, "", "no user bus")
            out = "s:1|%1" if args[0] == "new-session" else ""
            return subprocess.CompletedProcess(args, 0, out, "")

        with (
            patch.object(spawn, "tmux", fake),
            patch.object(spawn, "login_shell_path_into_server"),
            patch.object(spawn, "server_scope_prefix", return_value=scope),
        ):
            spawn.spawn({"name": "t", "agent": "none", "dir": str(self.work)})
        new_sessions = [p for cmd, p in calls if cmd == "new-session"]
        self.assertEqual(new_sessions, [scope, None])

    def test_scope_prefix_empty_off_linux(self):
        with patch.object(spawn.sys, "platform", "darwin"):
            self.assertEqual(spawn.server_scope_prefix(), [])


class IdentityTests(unittest.TestCase):
    def test_modes_markers_and_normalized_parent(self):
        fresh, prompt = spawn.codex_registration(False, None, "brief")
        self.assertEqual(fresh["mode"], "fresh")
        self.assertTrue(prompt.endswith("\n\n" + fresh["marker"]))
        with patch.dict(os.environ, {"CODEX_THREAD_ID": " " + SID + "\n"}):
            fork, empty = spawn.codex_registration(True, None, "")
        self.assertEqual(fork["parent_id"], SID)
        self.assertEqual(empty, "")
        self.assertNotIn("marker", fork)
        resume, prompt = spawn.codex_registration(False, SID, "literal")
        self.assertEqual(resume["resume_id"], SID)
        self.assertEqual(prompt, "literal")
        self.assertNotIn("marker", resume)

    def test_runtime_registration_uses_tmux_root_and_effective_home(self):
        seed, _ = spawn.codex_registration(False, None, "brief")
        result = subprocess.CompletedProcess([], 0, "12345\n", "")
        with (
            patch.dict(
                os.environ, {"TMUX_PANE": "%7", "CODEX_HOME": "/tmp/custom ' home"}
            ),
            patch.object(spawn, "tmux", return_value=result) as call,
        ):
            self.assertEqual(spawn.register_codex(seed), 0)
        self.assertEqual(
            call.call_args_list[0].args, ("display", "-p", "-t", "%7", "#{pane_pid}")
        )
        args = call.call_args_list[1].args
        self.assertEqual(args[:5], ("set-option", "-p", "-t", "%7", "@codex-spawn"))
        record = json.loads(args[-1])
        self.assertEqual(record["pane_pid"], 12345)
        self.assertEqual(record["codex_home"], os.path.realpath("/tmp/custom ' home"))
        self.assertEqual(record["cwd"], os.path.realpath(os.getcwd()))
        self.assertGreater(record["started_at"], 0)
        with (
            patch.dict(os.environ, {"TMUX_PANE": "%7"}),
            patch.object(
                spawn,
                "tmux",
                return_value=subprocess.CompletedProcess([], 1, "", "fail"),
            ),
        ):
            self.assertEqual(spawn.register_codex(seed), 1)

    def test_wrapper_order_and_json_quoting(self):
        seed, _ = spawn.codex_registration(False, None, "brief")
        command = spawn.build_command(
            "codex", False, None, None, "/tmp/brief 'quoted", codex_record=seed
        )
        self.assertLess(
            command.index('prompt="$(cat'), command.index("--register-codex")
        )
        self.assertLess(
            command.index("--register-codex"), command.index('if codex -- "$prompt"')
        )
        helper = next(
            line for line in command.splitlines() if "--register-codex" in line
        )
        argv = shlex.split(helper.split(" || ", 1)[0])
        self.assertEqual(json.loads(argv[-1]), seed)
        self.assertIn("identity unavailable", helper)


if __name__ == "__main__":
    unittest.main()
