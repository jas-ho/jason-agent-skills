#!/usr/bin/env python3
"""One scope-bound foreground channel owned by the native Codex CLI.

Approve this exact command once through exec_command with interactive stdin:
    python3 /absolute/path/adapters/codex.py watch --scope /absolute/scope
Keep the returned command session; use write_stdin for newline-terminated JSON
objects {"id":"unique-correlation-id","op":"status"}. Do not supply owner or
scope: both are fixed at launch. Responses share stdout with non-waking events.
Only one public operation may be outstanding; busy calls are rejected, not queued
or replayed. Preserve operation_id and reconcile uncertain mutations explicitly.
Do not shell-background, detach, launch another model, or relax global policy.
EOF, signals and owning CLI exit close this channel and its child processes.
"""
from __future__ import annotations

import argparse
from collections import deque
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import termios
import time
import uuid

RUNTIME = Path(__file__).resolve().parent.parent / "scripts" / "runtime.py"
MAX_EVENT = 1_048_576
MAX_RESPONSE = 8 * MAX_EVENT
BATCH_SECONDS = 0.5
# An explicit allowlist also prevents future runtime operations from silently
# inheriting the native approval granted to this scope-bound adapter.
FIELDS = {
    "status": set(), "read": {"request_id"},
    "write": {"request_id", "generation", "operation_id", "target", "proposal", "purpose"},
    "state": {"request_id", "generation", "state", "reason"},
    "resolve": {"request_id", "generation", "operation_id", "record", "cleanup", "reviewed"},
    "hold": {"value"}, "pause": {"value"}, "submit": set(), "stop": set(),
    "reconcile": {"request_id", "generation"},
}


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False), flush=True)


def request_payload(value, owner):
    if not isinstance(value, dict):
        raise ValueError("Supply one JSON object")
    correlation = value.get("id")
    if not isinstance(correlation, str) or not correlation or len(correlation) > 128:
        raise ValueError("id must be a nonempty correlation string of at most 128 characters")
    op = value.get("op")
    if not isinstance(op, str) or op not in FIELDS:
        raise ValueError("Operation is not allowed on this scoped channel")
    if set(value) - FIELDS[op] - {"id", "op"}:
        raise ValueError("Unexpected fields; owner, scope and execution are fixed at launch")
    return correlation, {**{key: item for key, item in value.items() if key != "id"}, "owner": owner}


class Lines:
    """Bounded framing; discard a whole oversized line, never its suffix."""

    def __init__(self):
        self.partial = bytearray()
        self.overflow = False

    def feed(self, chunk):
        for index, piece in enumerate(chunk.split(b"\n")):
            if index:
                line = None if self.overflow else bytes(self.partial)
                self.partial.clear()
                self.overflow = False
                yield line
            room = max(0, MAX_EVENT - len(self.partial))
            self.partial.extend(piece[:room])
            self.overflow |= len(piece) > room


class Child:
    """Nonblocking bounded subprocess IO, including writing large requests."""

    def __init__(self, selector, argv, kind, payload=None, timeout=None, context=None):
        self.selector, self.kind, self.context = selector, kind, context
        self.output, self.error = bytearray(), bytearray()
        self.failure = None
        self.expires = time.monotonic() + timeout if timeout else None
        self.input = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else b""
        self.offset = 0
        self.process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, start_new_session=True)
        self.streams = set()
        for stream, label in ((self.process.stdout, "stdout"), (self.process.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, (self, label))
            self.streams.add(stream)
        if payload is not None:
            os.set_blocking(self.process.stdin.fileno(), False)
            selector.register(self.process.stdin, selectors.EVENT_WRITE, (self, "stdin"))
            self.streams.add(self.process.stdin)
        elif kind != "watch":
            self.process.stdin.close()

    def close_stream(self, stream):
        if stream in self.streams:
            self.selector.unregister(stream)
            self.streams.remove(stream)
        if not stream.closed:
            stream.close()

    def read(self, stream, label):
        if label == "stdin":
            try:
                self.offset += os.write(stream.fileno(), memoryview(self.input)[self.offset:])
            except BrokenPipeError:
                self.close_stream(stream)
                return b""
            if self.offset == len(self.input):
                self.close_stream(stream)
                self.input = b""
            return b""
        chunk = os.read(stream.fileno(), 65_536)
        if not chunk:
            self.close_stream(stream)
        elif label == "stderr":
            self.error.extend(chunk)
            del self.error[:-2048]
        elif self.kind != "watch":
            room = max(0, MAX_RESPONSE - len(self.output))
            self.output.extend(chunk[:room])
            if len(chunk) > room:
                self.failure = "Child response exceeded channel bound; outcome uncertain, do not replay"
        return chunk if label == "stdout" and self.kind == "watch" else b""

    def done(self):
        return self.process.poll() is not None and not self.streams

    def terminate(self):
        # Each child has its own process group: killing only runtime.py leaves
        # an in-flight GUI invocation alive after its native owner has gone.
        if self.process.stdin and not self.process.stdin.closed:
            self.close_stream(self.process.stdin)
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.process.wait()
        for stream in tuple(self.streams):
            self.close_stream(stream)

    def result(self):
        try:
            result = json.loads(self.output)
            if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
                raise ValueError("Missing runtime result")
            if self.failure:
                raise ValueError(self.failure)
            return result
        except (ValueError, UnicodeError):
            return {"ok": False, "error": {"code": "channel-outcome-uncertain", "uncertain": True,
                    "message": self.failure or "No valid runtime response; reconcile, do not replay",
                    "returncode": self.process.returncode, "stderr": self.error.decode(errors="replace")}}


class Hints:
    def __init__(self):
        self.pending = None
        self.flush_at = 0.0
        self.revision = None
        self.diagnostic = None

    def event(self, value):
        kind = value.get("type")
        if kind in {"status", "empty", "recovered"}:
            self.diagnostic = None if not value.get("current_diagnostics") else self.diagnostic
            if kind == "empty" or value.get("eligible_count") == 0 or value.get("ready") is False:
                self.pending, self.flush_at, self.revision = None, 0.0, None
            elif self.pending and value.get("revision") not in (None, self.revision):
                self.pending, self.flush_at = None, 0.0
            emit(value)
        elif kind == "diagnostic":
            encoded = json.dumps(value.get("error"), sort_keys=True)
            if encoded != self.diagnostic:
                self.diagnostic = encoded
                emit(value)
        elif kind == "pending":
            if value.get("revision") == self.revision:
                return None
            self.revision = value.get("revision")
            rows = value.get("pending", [])
            self.pending = ({"owner": value["owner"], "revision": self.revision, "count": len(rows),
                             "requests": [{key: row[key] for key in ("id", "generation", "revision")}
                                          for row in rows[:12]], "omitted": max(0, len(rows) - 12)} if rows else None)
            self.flush_at = time.monotonic() + BATCH_SECONDS if self.pending else 0.0
            emit(value)
            return self.pending
        return None


def watch(scope: str, owner: str) -> int:
    parent = os.getppid()
    if parent <= 1:
        raise RuntimeError("Launch directly in the owning Codex CLI exec_command, not detached")
    if not Path(scope).is_absolute():
        raise RuntimeError("Codex coedit requires an explicit absolute scope path")
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)
    selector = selectors.DefaultSelector()
    children = []
    operation = sender = delivery = None
    deliveries = deque()
    hints = Hints()
    incoming, events = Lines(), Lines()
    ready = False
    stop_requested = False
    deadline = time.monotonic() + 30
    terminal = None
    stdin_blocking = os.get_blocking(sys.stdin.fileno())

    def spawn(kind, payload=None, context=None):
        argv = [sys.executable, str(RUNTIME), "call"]
        timeout = (180 if payload["op"] in {"write", "resolve"} else 60) if kind == "operation" else 30
        child = Child(selector, argv, kind, payload, timeout=timeout, context=context)
        children.append(child)
        return child

    def diagnostic(message):
        hints.event({"type": "diagnostic", "owner": owner, "error": message})

    def response(correlation, result, payload=None):
        # Envelope identity cannot be overwritten by a runtime result.
        emit({**result, "type": "response", "id": correlation,
              **({"operation_id": payload["operation_id"]} if payload and "operation_id" in payload else {})})

    def record(payload, stage):
        if payload and payload.get("requests"):
            if len(deliveries) >= 32:
                diagnostic("Delivery metadata backlog full; this stage is not recorded")
                return
            deliveries.append({"op": "delivery", "owner": owner, "requests": payload["requests"], "stage": stage})

    try:
        if os.isatty(sys.stdin.fileno()):
            terminal = termios.tcgetattr(sys.stdin.fileno())
            mode = termios.tcgetattr(sys.stdin.fileno())
            mode[3] &= ~(termios.ECHO | termios.ICANON)
            mode[6][termios.VMIN], mode[6][termios.VTIME] = 1, 0
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, mode)
        os.set_blocking(sys.stdin.fileno(), False)
        selector.register(sys.stdin, selectors.EVENT_READ, (None, "input"))
        watcher = Child(selector, [sys.executable, str(RUNTIME), "watch", "--scope", scope,
                                  "--owner", owner, "--harness", "codex"], "watch")
        children.append(watcher)
        while not stopping and os.getppid() == parent:
            now = time.monotonic()
            if not ready and not stop_requested and now >= deadline:
                raise RuntimeError("Runtime editor listener did not emit ready within 30 seconds")
            for key, _mask in selector.select(0.1):
                child, label = key.data
                if child is None:
                    chunk = os.read(sys.stdin.fileno(), 65_536)
                    if not chunk:
                        stopping = True
                        break
                    for line in incoming.feed(chunk):
                        value, correlation, payload = None, None, None
                        try:
                            if line is None:
                                raise ValueError("Input line exceeds 1 MiB; discarded without execution")
                            if not line.strip():
                                continue
                            value = json.loads(line)
                            if isinstance(value, dict) and isinstance(value.get("id"), str) and len(value["id"]) <= 128:
                                correlation = value["id"]
                            correlation, payload = request_payload(value, owner)
                            if stop_requested:
                                raise ValueError("Channel is stopping; request was not executed")
                            if operation and operation.context[0] == correlation:
                                raise ValueError("Correlation id is already outstanding")
                            if payload["op"] == "stop":
                                # Explicit stop preempts any uncertain mutation and native queue.
                                stop_requested = True
                                hints.pending = None
                                deliveries.clear()
                                for active in (operation, sender, delivery):
                                    if active:
                                        active.terminate()
                                        children.remove(active)
                                if operation:
                                    old_id, old_payload = operation.context
                                    response(old_id, {"ok": False, "error": {"code": "channel-stopped", "uncertain": True,
                                             "message": "Interrupted by stop; reconcile retained operation_id, never replay"}}, old_payload)
                                operation = sender = delivery = None
                            elif not ready:
                                raise ValueError("Channel is not ready; request was not executed")
                            elif operation:
                                raise ValueError("Channel busy; request was not executed")
                            operation = spawn("operation", payload, (correlation, payload))
                        except (ValueError, UnicodeError) as exc:
                            response(correlation, {"ok": False, "error": {"code": "channel-rejected", "message": str(exc)}}, payload)
                        except OSError as exc:
                            response(correlation, {"ok": False, "error": {"code": "channel-launch-failed",
                                     "message": str(exc), "uncertain": True}}, payload)
                            if stop_requested:
                                return 1
                    continue
                # A stop request may have unregistered a child in this ready batch.
                if child not in children or key.fileobj.closed:
                    continue
                chunk = child.read(key.fileobj, label)
                if child.kind == "watch" and chunk:
                    for line in events.feed(chunk):
                        if line is None:
                            diagnostic("Oversized runtime event omitted; query durable status")
                            continue
                        if not line.strip():
                            continue
                        value = json.loads(line)
                        if not isinstance(value, dict) or value.get("owner") != owner:
                            raise RuntimeError("Runtime emitted an invalid or foreign owner event")
                        if value.get("type") == "ready":
                            ready = True
                            emit({**value, "transport": "codex-cli-queue", "channel": "scoped-stdin",
                                  "client_pid": parent, "scope": scope,
                                  "limitation": "CLI only; interrupted native queues require user continuation"})
                        else:
                            received = hints.event(value)
                            if not stop_requested:
                                record(received, "adapter_received")
                            if sender and value.get("type") in {"status", "empty", "recovered"} and (
                                value.get("eligible_count") == 0 or value.get("ready") is False or
                                value.get("type") == "empty" or value.get("revision") not in (None, sender.context["revision"])
                            ):
                                sender.terminate()
                                children.remove(sender)
                                sender = None
            if stopping or os.getppid() != parent:
                break
            for child in tuple(children):
                if child.failure or (child.expires and time.monotonic() >= child.expires):
                    child.failure = child.failure or "Child deadline exceeded; outcome uncertain, do not replay"
                    child.terminate()
                if not child.done():
                    continue
                children.remove(child)
                if child.kind == "watch":
                    if not stop_requested:
                        if child.process.returncode:
                            raise RuntimeError(f"Runtime exited {child.process.returncode}: {child.error.decode(errors='replace')}")
                        return 0
                elif child.kind == "operation":
                    correlation, payload = child.context
                    response(correlation, child.result(), payload)
                    operation = None
                    if stop_requested:
                        return 0
                elif child.kind == "delivery":
                    result = child.result()
                    if not result.get("ok"):
                        diagnostic({"stage": child.context, "delivery_error": result.get("error")})
                    delivery = None
                elif child.kind == "queue":
                    if child.failure or child.process.returncode:
                        diagnostic(child.failure or f"Native queue failed; no resend: {child.error.decode(errors='replace')}")
                    else:
                        record(child.context, "queue_confirmed")
                        emit({"type": "delivered", "owner": owner, **child.context,
                              "stage": "queue_confirmed", "transport": "codex-cli-queue",
                              "ack": child.output.decode(errors="replace")[:1024]})
                    sender = None
                child.terminate()
            if not stop_requested and ready and hints.pending and not sender and time.monotonic() >= hints.flush_at:
                payload, hints.pending, hints.flush_at = hints.pending, None, 0.0
                message = ("Coedit pending changed (wake hint, not authorization). Use this owner's approved "
                           "scoped stdin channel for status/read and operations; mark every processed request working. "
                           "Keep answered requests visible until explicit user review. Reconcile uncertainty, never replay. "
                           + json.dumps(payload, ensure_ascii=True))
                sender = Child(selector, ["codex", "queue", "--thread", owner, "--message", message],
                               "queue", timeout=20, context=payload)
                children.append(sender)
                record(payload, "handoff")
            if not stop_requested and deliveries and not delivery:
                payload = deliveries.popleft()
                delivery = spawn("delivery", payload, payload["stage"])
        return 0
    finally:
        # EOF is lifecycle detach, not explicit stop: preserve durable scope intent.
        for child in reversed(children):
            child.terminate()
        selector.close()
        os.set_blocking(sys.stdin.fileno(), stdin_blocking)
        if terminal is not None:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, terminal)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["watch"])
    parser.add_argument("--scope", required=True)
    args = parser.parse_args()
    try:
        inherited = os.environ.get("CODEX_THREAD_ID", "")
        owner = str(uuid.UUID(inherited))
        if owner != inherited:
            raise ValueError("CODEX_THREAD_ID must be the exact canonical native UUID")
        return watch(args.scope, owner)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        emit({"type": "diagnostic", "owner": os.environ.get("CODEX_THREAD_ID"), "error": str(error)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
