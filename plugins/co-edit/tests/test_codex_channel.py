"""Scope authority and owner-lifetime regressions; no native editor or Codex service."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters import codex


class ProtocolTests(unittest.TestCase):
    def test_untrusted_requests_cannot_expand_the_approved_authority(self):
        owner = str(uuid.uuid4())
        attacks = [
            {"op": "start", "scope": "/elsewhere"},
            {"op": "status", "owner": str(uuid.uuid4())},
            {"op": "status", "scope": "/elsewhere"},
            {"op": "status", "command": "touch /tmp/escape"},
            {"op": "delivery", "stage": "queue_confirmed", "requests": []},
            {"op": "submit", "espanso_trigger": "arm"},
        ]
        for attack in attacks:
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                codex.request_payload({"id": "attempt", **attack}, owner)

    def test_oversized_line_cannot_smuggle_a_valid_request_suffix(self):
        framing = codex.Lines()
        self.assertEqual(list(framing.feed(b"x" * codex.MAX_EVENT)), [])
        self.assertEqual(list(framing.feed(b'{"id":"escape","op":"stop"}\n{"id":"safe","op":"status"}\n')),
                         [None, b'{"id":"safe","op":"status"}'])

    def test_recovered_empty_status_discards_unsent_work_without_error_wakes(self):
        hints = codex.Hints()
        request = {"id": "request", "generation": 3, "revision": "exact"}
        output = io.StringIO()
        with redirect_stdout(output):
            hints.event({"type": "pending", "owner": "owner", "revision": "batch", "pending": [request]})
            self.assertIsNotNone(hints.pending)
            hints.event({"type": "diagnostic", "owner": "owner", "error": "offline"})
            hints.event({"type": "status", "owner": "owner", "ready": True, "eligible_count": 0,
                         "current_diagnostics": [], "revision": "empty"})
            self.assertIsNone(hints.pending)
            hints.event({"type": "diagnostic", "owner": "owner", "error": "offline"})
            self.assertIsNone(hints.pending)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([event["type"] for event in events], ["pending", "diagnostic", "status", "diagnostic"])


FAKE_RUNTIME = r'''
import json, os, pathlib, subprocess, sys, time
root = pathlib.Path(os.environ["CHANNEL_FIXTURE"])
if sys.argv[1] == "watch":
    owner = sys.argv[sys.argv.index("--owner") + 1]
    print(json.dumps({"type": "ready", "owner": owner, "ready": True}), flush=True)
    while not (root / "operation-started").exists():
        time.sleep(.01)
    print(json.dumps({"type": "pending", "owner": owner, "revision": "batch-one", "pending": [
        {"id": "request-one", "generation": 2, "revision": "signed-revision"}]}), flush=True)
    sys.stdin.read()
else:
    data = json.load(sys.stdin)
    if data["op"] == "write":
        child = subprocess.Popen([sys.executable, "-c",
            "import pathlib,sys,time; time.sleep(4); pathlib.Path(sys.argv[1]).write_text('orphaned')",
            str(root / "orphan-ran")])
        (root / "operation-started").touch()
        time.sleep(60)
    elif data["op"] == "delivery":
        print(json.dumps({"ok": True}), flush=True)
    elif data["op"] == "stop":
        (root / "explicit-stop").touch()
        print(json.dumps({"ok": True, "stopped": True}), flush=True)
'''


class LifetimeTests(unittest.TestCase):
    def exercise_shutdown(self, explicit):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime.py"
            runtime.write_text(FAKE_RUNTIME)
            queue = root / "codex"
            queue.write_text(f"#!{sys.executable}\nprint('queued')\n")
            queue.chmod(0o700)
            owner = str(uuid.uuid4())
            environment = {**os.environ, "CODEX_THREAD_ID": owner, "CHANNEL_FIXTURE": directory,
                           "PATH": directory + os.pathsep + os.environ.get("PATH", ""),
                           "PYTHONDONTWRITEBYTECODE": "1"}
            launcher = ("import sys; from pathlib import Path; "
                        f"sys.path.insert(0, {str(Path(codex.__file__).resolve().parents[1])!r}); "
                        "from adapters import codex; "
                        f"codex.RUNTIME = Path({str(runtime)!r}); "
                        "sys.exit(codex.main())")
            process = subprocess.Popen([sys.executable, "-c", launcher, "watch", "--scope", directory],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       env=environment)
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            framing = codex.Lines()
            observed = []

            def until(predicate, timeout=8):
                expires = time.monotonic() + timeout
                while not predicate():
                    if time.monotonic() >= expires:
                        self.fail(f"Channel did not reach expected event: {observed}")
                    for key, _ in selector.select(.1):
                        chunk = os.read(key.fileobj.fileno(), 65_536)
                        if not chunk:
                            self.fail(f"Channel exited before expected event: {observed}")
                        observed.extend(json.loads(line) for line in framing.feed(chunk) if line)

            def send(value):
                process.stdin.write(json.dumps(value).encode() + b"\n")
                process.stdin.flush()

            try:
                until(lambda: any(event["type"] == "ready" for event in observed))
                send({"id": "mutation-call", "op": "write", "request_id": "request-one", "generation": 2,
                      "operation_id": "preserved-operation", "target": {"path": "fixture-only"}})
                # The native wake must complete while the operation is still blocked.
                until(lambda: any(event["type"] == "delivered" for event in observed))
                self.assertFalse(any(event["type"] == "response" for event in observed))
                if explicit:
                    send({"id": "stop-call", "op": "stop"})
                    until(lambda: any(event.get("id") == "stop-call" for event in observed))
                    stopped = next(event for event in observed if event.get("id") == "stop-call")
                    self.assertTrue(stopped["ok"])
                    interrupted = next(event for event in observed if event.get("id") == "mutation-call")
                    self.assertTrue(interrupted["error"]["uncertain"])
                    self.assertEqual(interrupted["operation_id"], "preserved-operation")
                else:
                    process.stdin.close()
                self.assertEqual(process.wait(timeout=8), 0)
                # An orphaned editor child would perform this delayed side effect.
                time.sleep(4.2)
                self.assertFalse((root / "orphan-ran").exists())
                self.assertEqual((root / "explicit-stop").exists(), explicit)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
                selector.close()
                for stream in (process.stdin, process.stdout, process.stderr):
                    if not stream.closed:
                        stream.close()

    def test_eof_detaches_inflight_descendants_without_explicit_stop(self):
        self.exercise_shutdown(False)

    def test_explicit_stop_cancels_inflight_work_and_returns_correlated_result(self):
        self.exercise_shutdown(True)


if __name__ == "__main__":
    unittest.main()
