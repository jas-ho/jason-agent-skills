"""Exercise delayed subprocess replies with the caller's stdin already at EOF."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]

# A real child process models the measured CLI behavior: EOF terminates its reply
# channel before delayed evaluation completes. No Obsidian app or notes are used.
CLI = r'''
import json
import os
from pathlib import Path
import re
import select
import sys
import time

with open(os.environ["ATTEMPTS"], "a") as log:
    log.write("invoked\n")
if select.select([sys.stdin], [], [], 0.15)[0] and not os.read(0, 1):
    raise SystemExit(0)
mode = os.environ["MODE"]
if mode == "timeout":
    time.sleep(30)
if mode == "absent":
    raise SystemExit(0)
token = json.loads(re.search(r'const token=("[^"]+")', sys.argv[2]).group(1))
# Concurrent CLI logs include code (and hence the own nonce), not its envelope.
print("Received CLI command " + repr(sys.argv))
print('=> COEDIT_foreign:{"ok":true,"value":{"wrong":true}}')
print("=> " + token + json.dumps({"ok": True, "value": {"committed": True}}))
print("unrelated helper error", file=sys.stderr)
raise SystemExit(7)
'''

CALLER = r'''
import errno
import json
import os
import sys
from scripts import editor

# Track actual descriptors to verify lifetime after success, launch error and
# timeout, not merely that a particular subprocess keyword was forwarded.
pipe = os.pipe
fds = []
def tracked_pipe():
    pair = pipe()
    fds.extend(pair)
    return pair
os.pipe = tracked_pipe
run = editor.subprocess.run
if os.environ["MODE"] == "timeout":
    def bounded_run(*args, **kwargs):
        kwargs["timeout"] = 0.4
        return run(*args, **kwargs)
    editor.subprocess.run = bounded_run
try:
    value = editor.call("notice", {"owner": "transport-regression"})
    result = {"value": value}
except editor.EditorError as error:
    result = {"code": error.code, "uncertain": error.uncertain, "details": error.details}
leaked = []
for fd in fds:
    try:
        os.fstat(fd)
        leaked.append(fd)
    except OSError as error:
        if error.errno != errno.EBADF:
            raise
result["leaked_fds"] = leaked
print(json.dumps(result))
'''


class TransportLifetime(unittest.TestCase):
    def invoke(self, mode):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "real-cli"
            executable.write_text("#!" + ("/nonexistent/coedit-interpreter" if mode == "launch-error" else sys.executable) + "\n" + CLI)
            executable.chmod(0o755)
            (root / "obsidian").symlink_to(executable)
            attempts = root / "attempts"
            env = {**os.environ, "PATH": str(root), "PYTHONPATH": str(ROOT),
                   "ATTEMPTS": str(attempts), "MODE": mode}
            # communicate closes this stdin before editor.call starts. The
            # production transport must not inherit EOF or use stdin=PIPE.
            result = subprocess.run([sys.executable, "-c", CALLER], input="", text=True,
                                    capture_output=True, env=env, timeout=5, check=True)
            return json.loads(result.stdout), attempts.read_text().splitlines() if attempts.exists() else []

    def test_delayed_receipt_survives_eof_pollution_and_nonzero_exit(self):
        result, attempts = self.invoke("reply")
        self.assertEqual(result["value"], {"committed": True})
        self.assertEqual(result["leaked_fds"], [])
        self.assertEqual(attempts, ["invoked"])

    def test_missing_reply_is_uncertain_without_replay(self):
        result, attempts = self.invoke("absent")
        self.assertEqual(result["code"], "transport-uncertain")
        self.assertTrue(result["uncertain"])
        self.assertEqual(result["details"]["returncode"], 0)
        self.assertFalse(result["details"]["timed_out"])
        self.assertGreaterEqual(result["details"]["elapsed_ms"], 100)
        self.assertEqual(result["leaked_fds"], [])
        self.assertEqual(attempts, ["invoked"])

    def test_timeout_closes_descriptors_without_replay(self):
        result, attempts = self.invoke("timeout")
        self.assertEqual(result["code"], "transport-uncertain")
        self.assertTrue(result["uncertain"])
        self.assertTrue(result["details"]["timed_out"])
        self.assertIsNone(result["details"]["returncode"])
        self.assertEqual(result["leaked_fds"], [])
        self.assertEqual(attempts, ["invoked"])

    def test_launch_error_closes_descriptors(self):
        result, attempts = self.invoke("launch-error")
        self.assertEqual(result["code"], "transport-unavailable")
        self.assertFalse(result["uncertain"])
        self.assertEqual(result["leaked_fds"], [])
        self.assertEqual(attempts, [])


if __name__ == "__main__":
    unittest.main()
