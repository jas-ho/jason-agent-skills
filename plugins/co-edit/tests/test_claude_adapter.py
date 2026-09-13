"""Claude Monitor wake and process-lifetime regressions; no editor or model."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters import claude


# Commands arrive through private atomic files, never through the runtime's
# stdin: that pipe must remain the adapter's genuine lifetime channel.
FAKE_RUNTIME = r'''
import json, os, pathlib, selectors, signal, stat, subprocess, sys, time
root = pathlib.Path(os.environ["CLAUDE_FIXTURE"])
owner = sys.argv[sys.argv.index("--owner") + 1]
(root / "runtime-process").write_text(json.dumps([os.getpid(), os.getpgrp()]))

def stop(*_):
    raise SystemExit(0)

signal.signal(signal.SIGTERM, stop)
selector = selectors.DefaultSelector()
try:
    if not stat.S_ISFIFO(os.fstat(sys.stdin.fileno()).st_mode):
        raise RuntimeError("Canonical runtime did not receive a real stdin FIFO")
    selector.register(sys.stdin, selectors.EVENT_READ)
    if os.environ.get("CLAUDE_DESCENDANT") == "1":
        subprocess.Popen([sys.executable, "-c", r"""
import pathlib, signal, sys, time
root = pathlib.Path(sys.argv[1])
signal.signal(signal.SIGTERM, signal.SIG_IGN)
(root / 'descendant-ready').touch()
expires = time.monotonic() + 15
while time.monotonic() < expires:
    if (root / 'detach').exists():
        time.sleep(.5)
        (root / 'orphan-ran').touch()
        break
    time.sleep(.01)
""", str(root)])
        expires = time.monotonic() + 5
        while not (root / "descendant-ready").exists():
            if time.monotonic() >= expires:
                raise RuntimeError("Descendant failed to initialize")
            time.sleep(.01)
    print(json.dumps({"type": "ready", "owner": owner, "ready": True}), flush=True)
    index = 0
    expires = time.monotonic() + 15
    while time.monotonic() < expires:
        if selector.select(.01):
            if not os.read(sys.stdin.fileno(), 4096):
                (root / "stdin-eof").touch()
                break
        command = root / ("command-%d" % index)
        if command.exists():
            payload = command.read_bytes()
            # A buffered write completes partial pipe writes for oversized frames.
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()
            index += 1
    else:
        raise RuntimeError("Finite fixture lifetime expired")
finally:
    (root / "runtime-stopped").touch()
    selector.close()
'''


class RuntimeFixture:
    def __init__(self, root, *, monitor=False, native_parent=False, descendant=False):
        self.root = root
        self.owner = str(uuid.uuid4())
        self.events = []
        self.errors = bytearray()
        self.pending = bytearray()
        self.stdout_eof = False
        self.command_index = 0
        runtime = root / "runtime.py"
        runtime.write_text(FAKE_RUNTIME)
        launcher = ("import sys; from pathlib import Path; "
                    f"sys.path.insert(0, {str(Path(claude.__file__).resolve().parents[1])!r}); "
                    "from adapters import claude; "
                    f"claude.RUNTIME = Path({str(runtime)!r}); "
                    "sys.exit(claude.main())")
        command = [sys.executable, "-c", launcher, "watch", "--scope", str(root),
                   "--owner", self.owner]
        if native_parent:
            # This process alone is terminated by the test. The adapter receives
            # neither a signal nor an input EOF; only its native parent changes.
            parent = ("import subprocess,sys; "
                      "child = subprocess.Popen(sys.argv[1:], stdin=subprocess.DEVNULL); "
                      "sys.exit(child.wait())")
            command = [sys.executable, "-c", parent, *command]
        self.process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL if monitor or native_parent else subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
            env={**os.environ, "CLAUDE_FIXTURE": str(root),
                 "CLAUDE_DESCENDANT": "1" if descendant else "0",
                 "PYTHONDONTWRITEBYTECODE": "1"})
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ, "stdout")
        self.selector.register(self.process.stderr, selectors.EVENT_READ, "stderr")

    def pump(self, timeout):
        for key, _ in self.selector.select(timeout):
            chunk = os.read(key.fileobj.fileno(), 65536)
            if not chunk:
                self.selector.unregister(key.fileobj)
                if key.data == "stdout":
                    self.stdout_eof = True
            elif key.data == "stderr":
                self.errors.extend(chunk)
            else:
                self.pending.extend(chunk)
                while b"\n" in self.pending:
                    line, _, rest = self.pending.partition(b"\n")
                    self.pending = bytearray(rest)
                    self.events.append(json.loads(line))

    def until(self, predicate, timeout=6):
        expires = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= expires:
                raise AssertionError(f"Adapter timed out: {self.events}; "
                                     f"stderr={self.errors.decode(errors='replace')}")
            self.pump(.05)

    def observe_for(self, seconds):
        expires = time.monotonic() + seconds
        while time.monotonic() < expires:
            self.pump(max(0, min(.05, expires - time.monotonic())))

    def event(self, kind, **fields):
        return {"type": kind, "owner": self.owner, **fields}

    def send(self, *events, raw=None):
        payload = raw if raw is not None else b"".join(
            json.dumps(event).encode() + b"\n" for event in events)
        staged = self.root / "staged-command"
        staged.write_bytes(payload)
        staged.replace(self.root / f"command-{self.command_index}")
        self.command_index += 1

    def close(self):
        # Both groups are private sessions created by this fixture/adapter.
        # Never signal a discovered editor, ambient parent, or global process.
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                pass
        groups = [self.process.pid]
        record = self.root / "runtime-process"
        if record.exists():
            pid, group = json.loads(record.read_text())
            if pid == group:
                groups.append(group)
        for group in groups:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.process.wait(timeout=4)
        self.selector.close()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


class ClaudeAdapterTests(unittest.TestCase):
    @contextmanager
    def runtime(self, **options):
        # The system temp directory is outside the Obsidian vault; no fixtures
        # or launchers can be deleted by vault sync or affect real trial state.
        with tempfile.TemporaryDirectory(prefix="coedit-claude-", dir="/tmp") as directory:
            fixture = RuntimeFixture(Path(directory), **options)
            try:
                fixture.until(lambda: bool(fixture.events))
                self.assertEqual([event["type"] for event in fixture.events], ["ready"])
                yield fixture
            finally:
                fixture.close()

    def test_status_and_recovered_do_not_wake_or_preserve_stale_pending(self):
        with self.runtime() as fixture:
            for clearing in (
                fixture.event("status", ready=True, eligible_count=0, revision="empty"),
                fixture.event("recovered", ready=True, eligible_count=1, revision="replacement"),
            ):
                with self.subTest(clearing=clearing["type"]):
                    fixture.send(
                        fixture.event("status", ready=True, eligible_count=1, revision="raw"),
                        fixture.event("recovered", ready=True, eligible_count=1, revision="raw"),
                        fixture.event("pending", revision="stale", pending=[{"id": "obsolete"}]),
                        clearing)
                    fixture.observe_for(claude.BATCH_SECONDS + .4)
                    self.assertEqual([event["type"] for event in fixture.events], ["ready"])
            # Clearing an unsent batch must permit the same revision to wake
            # when authoritative work subsequently becomes eligible again.
            fixture.send(fixture.event("pending", revision="stale", pending=[{"id": "current"}]))
            fixture.until(lambda: len(fixture.events) > 1)
            self.assertEqual([event["type"] for event in fixture.events], ["ready", "pending"])
            self.assertEqual(fixture.events[-1]["count"], 1)

    def test_invalid_frames_and_foreign_owner_fail_closed_and_stop_runtime(self):
        for attack in ("malformed", "oversized", "foreign-owner"):
            with self.subTest(attack=attack), self.runtime() as fixture:
                valid = fixture.event("pending", revision="smuggled", pending=[{"id": "unsafe"}])
                suffix = json.dumps(valid).encode() + b"\n"
                if attack == "malformed":
                    payload = b'{"type":not-json}\n' + suffix
                elif attack == "oversized":
                    payload = b"x" * (claude.MAX_EVENT + 1) + b"\n" + suffix
                else:
                    payload = json.dumps({**valid, "owner": str(uuid.uuid4())}).encode() + b"\n"
                fixture.send(raw=payload)
                fixture.until(lambda: fixture.stdout_eof)
                self.assertEqual(fixture.process.wait(timeout=4), 1)
                self.assertEqual([event["type"] for event in fixture.events], ["ready", "fatal"])
                self.assertTrue((fixture.root / "runtime-stopped").exists())

    def test_monitor_devnull_keeps_runtime_fifo_open_for_later_work(self):
        with self.runtime(monitor=True) as fixture:
            fixture.observe_for(claude.BATCH_SECONDS + .3)
            self.assertIsNone(fixture.process.poll())
            self.assertFalse((fixture.root / "stdin-eof").exists())
            fixture.send(fixture.event("pending", revision="later", pending=[{"id": "new-work"}]))
            fixture.until(lambda: len(fixture.events) > 1)
            self.assertEqual([event["type"] for event in fixture.events], ["ready", "pending"])
            self.assertFalse((fixture.root / "stdin-eof").exists())

    def exercise_detach(self, native_parent):
        with self.runtime(native_parent=native_parent, descendant=True) as fixture:
            self.assertTrue((fixture.root / "descendant-ready").exists())
            (fixture.root / "detach").touch()
            if native_parent:
                fixture.process.terminate()  # Only the native parent, not its group.
                self.assertEqual(fixture.process.wait(timeout=4), -signal.SIGTERM)
            else:
                fixture.process.stdin.close()
            fixture.until(lambda: fixture.stdout_eof)
            if not native_parent:
                self.assertEqual(fixture.process.wait(timeout=4), 0)
            self.assertEqual([event["type"] for event in fixture.events], ["ready"])
            self.assertTrue((fixture.root / "runtime-stopped").exists())
            # The descendant ignores SIGTERM and would perform an observable
            # side effect after detach if group cleanup stopped at the leader.
            fixture.observe_for(.8)
            self.assertFalse((fixture.root / "orphan-ran").exists())

    def test_controlling_fifo_eof_terminates_runtime_and_descendant(self):
        self.exercise_detach(False)

    def test_native_parent_only_termination_cleans_runtime_and_descendant(self):
        self.exercise_detach(True)


if __name__ == "__main__":
    unittest.main()
