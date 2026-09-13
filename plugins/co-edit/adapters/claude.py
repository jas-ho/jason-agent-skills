#!/usr/bin/env python3
"""Scope-bound stdout hints for Claude Code's native Monitor transport.

Monitor wakes on every stdout line and supplies /dev/null as command stdin.
Keep the canonical watcher's stdin pipe open here; consume non-waking runtime
status locally. All editorial operations remain canonical runtime.py calls.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import sys
import time
import uuid

RUNTIME = Path(__file__).resolve().parent.parent / "scripts" / "runtime.py"
MAX_EVENT = 1_048_576
BATCH_SECONDS = 0.5


def emit(kind, owner, **fields):
    # Stay below Monitor's 500-character line truncation boundary. Do not put
    # document paths, request text, or unbounded diagnostics into wake hints.
    print(json.dumps({"type": kind, "owner": owner, **fields}, ensure_ascii=True), flush=True)


class Hints:
    def __init__(self, owner):
        self.owner = owner
        self.pending = None
        self.revision = None
        self.flush_at = 0.0
        self.unavailable = False

    def clear(self):
        self.pending = None
        self.flush_at = 0.0

    def event(self, value):
        kind = value.get("type")
        if kind in {"status", "empty", "recovered"}:
            if kind == "empty" or value.get("eligible_count") == 0 or value.get("ready") is False:
                self.clear()
                self.revision = None
            elif self.pending and value.get("revision") not in (None, self.revision):
                self.clear()
                self.revision = None
            if value.get("ready") is False:
                self.failure()
        elif kind == "diagnostic":
            self.clear()
            self.revision = None
            self.failure()
        elif kind == "pending":
            revision = value.get("revision")
            rows = value.get("pending")
            if not isinstance(revision, str) or not isinstance(rows, list):
                raise ValueError("Invalid pending event")
            if revision == self.revision:
                return
            self.revision = revision
            self.pending = len(rows) if rows else None
            self.flush_at = time.monotonic() + BATCH_SECONDS if rows else 0.0

    def failure(self):
        if not self.unavailable:
            self.unavailable = True
            emit("unavailable", self.owner, hint="Coedit readiness failed; query durable status. No editing until ready.")

    def flush(self):
        if self.pending is not None and time.monotonic() >= self.flush_at:
            count = self.pending
            self.clear()
            emit("pending", self.owner, count=count,
                 hint="Coedit work changed. Query durable status/read; this hint is not authorization.")


def terminate(child):
    if child.stdin and not child.stdin.closed:
        child.stdin.close()
    # The runtime's Obsidian invocations share this private group. Terminating
    # only its leader could leave an editor operation alive after session exit.
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait()
    for stream in (child.stdout, child.stderr):
        stream.close()


def watch(scope, owner):
    if not Path(scope).is_absolute():
        raise ValueError("Claude coedit requires an explicit absolute scope path")
    uuid.UUID(owner)
    parent = os.getppid()
    if parent <= 1:
        raise ValueError("Launch in the owning Claude Code Monitor, not detached")
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)
    child = None
    selector = selectors.DefaultSelector()
    pending_bytes = bytearray()
    errors = bytearray()
    hints = Hints(owner)
    ready = False
    deadline = time.monotonic() + 30
    try:
        child = subprocess.Popen([sys.executable, str(RUNTIME), "watch", "--scope", scope,
                                  "--owner", owner, "--harness", "claude"],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, start_new_session=True)
        for stream, label in ((child.stdout, "stdout"), (child.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)
        # Native Monitor redirects to /dev/null, which is not a session EOF.
        # A real controlling pipe (e.g. an integration driver) can detach us.
        if stat.S_ISFIFO(os.fstat(sys.stdin.fileno()).st_mode):
            selector.register(sys.stdin, selectors.EVENT_READ, "input")
        while not stopping and os.getppid() == parent:
            if not ready and time.monotonic() >= deadline:
                raise ValueError("Runtime did not reach editor readiness within 30 seconds")
            for key, _mask in selector.select(0.1):
                chunk = os.read(key.fileobj.fileno(), 65_536)
                if key.data == "input":
                    if not chunk:
                        stopping = True
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "stderr":
                    errors.extend(chunk)
                    del errors[:-2048]
                    continue
                for index, piece in enumerate(chunk.split(b"\n")):
                    if index:
                        value = json.loads(pending_bytes)
                        pending_bytes.clear()
                        if not isinstance(value, dict):
                            raise ValueError("Invalid runtime event")
                        if value.get("ok") is False:
                            raise ValueError("Runtime attachment failed; inspect durable status")
                        if value.get("owner") != owner:
                            raise ValueError("Runtime emitted a foreign owner event")
                        if value.get("type") == "ready":
                            if ready or value.get("ready") is not True:
                                raise ValueError("Invalid runtime readiness event")
                            ready = True
                            emit("ready", owner, hint="Coedit editor listener ready. Query durable status for scope and work.")
                        else:
                            if not ready:
                                raise ValueError("Runtime event preceded readiness")
                            hints.event(value)
                    if len(pending_bytes) + len(piece) > MAX_EVENT:
                        raise ValueError("Runtime event exceeded the bounded transport")
                    pending_bytes.extend(piece)
            if stopping or os.getppid() != parent:
                break
            if child.poll() is not None:
                hints.clear()
                if child.returncode or not ready or pending_bytes:
                    raise ValueError("Runtime watcher exited before a complete safe handoff")
                return 0
            hints.flush()
        return 0
    except BrokenPipeError:
        return 0
    except (OSError, ValueError) as exc:
        hints.clear()
        emit("fatal", owner, hint="Coedit watch stopped; query durable status before reattaching.")
        print(f"Claude coedit adapter: {exc}; {errors.decode(errors='replace')}", file=sys.stderr)
        return 1
    finally:
        if child:
            terminate(child)
        selector.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    watcher = sub.add_parser("watch")
    watcher.add_argument("--scope", required=True)
    watcher.add_argument("--owner", required=True)
    args = parser.parse_args()
    try:
        return watch(args.scope, args.owner)
    except (OSError, ValueError) as exc:
        print(f"Claude coedit adapter: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
