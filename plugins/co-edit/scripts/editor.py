"""Sentinel-first transport to the transient, editor-only Obsidian bridge."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid


class EditorError(RuntimeError):
    """A refused operation, or a transport outcome that must not be replayed."""

    def __init__(self, message: str, *, code: str = "editor-error", uncertain: bool = False,
                 details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.uncertain = uncertain
        self.details = details or {}


_ACTIONS = frozenset({"attach", "snapshot", "ack", "submit", "notice", "write", "ensure", "receipt", "detach"})
_STATE_DIRS: dict[str, str] = {}


def call(action: str, payload: dict) -> dict:
    """Call once; a missing result is uncertainty, never permission to retry a write.

    The bridge file is loaded by Obsidian's Node runtime, avoiding command-line
    length limits for the implementation. Payloads remain data, not JavaScript.
    """
    if action not in _ACTIONS or not isinstance(payload, dict):
        raise EditorError("Unknown editor action or invalid payload", code="invalid-input")
    payload = dict(payload)
    payload["_source_dir"] = str(Path(__file__).resolve().parent.parent)
    owner = payload.get("owner")
    if not isinstance(owner, str) or not owner:
        raise EditorError("An owner is required", code="invalid-input")
    if "state_dir" not in payload and owner in _STATE_DIRS:
        payload["state_dir"] = _STATE_DIRS[owner]
    if action == "attach":
        payload.setdefault("state_dir", os.environ.get("COEDIT_STATE_DIR", str(Path.home() / ".local/state/coedit")))
    for key in ("path", "scope", "state_dir"):
        value = payload.get(key)
        if value is not None and (not isinstance(value, str) or not Path(value).is_absolute()):
            raise EditorError(f"{key} must be an absolute path", code="invalid-input")
    for key in ("request", "target", "proposal"):
        if key in payload:
            value = payload[key]
            if not isinstance(value, dict) or not isinstance(value.get("path"), str) or not Path(value["path"]).is_absolute():
                raise EditorError(f"{key}.path must be an absolute path", code="invalid-input")
    bridge = str(Path(__file__).with_name("editor_bridge.js").resolve())
    token = "COEDIT_" + uuid.uuid4().hex + ":"
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=True).encode()).decode()
    code = (
        "(async()=>{const token=" + json.dumps(token) + ";try{"
        "const fn=eval(require('fs').readFileSync(" + json.dumps(bridge) + ",'utf8'));"
        "const value=await fn(" + json.dumps(action) + ",JSON.parse(Buffer.from("
        + json.dumps(encoded) + ",'base64').toString('utf8')));"
        "return token+JSON.stringify({ok:true,value});"
        "}catch(e){return token+JSON.stringify({ok:false,error:String(e.message||e),"
        "code:e.code||'editor-error',uncertain:!!e.uncertain,details:e.details||{}});}})()"
    )
    started = time.monotonic()
    returncode = None
    timed_out = False
    read_fd = write_fd = None
    try:
        executable = shutil.which("obsidian")
        if executable is None:
            raise FileNotFoundError("obsidian is not on PATH")
        # Electron locates its helper bundle relative to the executable: launching
        # a ~/bin symlink causes helper failures and intermittent lost CLI replies.
        # Keep the writer open: inherited EOF (and communicate's stdin=PIPE EOF)
        # ends the CLI socket before delayed Obsidian evaluation can reply.
        read_fd, write_fd = os.pipe()
        result = subprocess.run([str(Path(executable).resolve()), "eval", "code=" + code],
                                stdin=read_fd, capture_output=True, text=True, timeout=45)
        returncode = result.returncode
        stdout, stderr = result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        stderr = exc.stderr or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
    except OSError as exc:
        raise EditorError(str(exc), code="transport-unavailable", uncertain=False,
                          details={"returncode": returncode, "signal": None, "timed_out": False,
                                   "elapsed_ms": round((time.monotonic() - started) * 1000)}) from exc
    finally:
        try:
            if read_fd is not None:
                os.close(read_fd)
        finally:
            if write_fd is not None:
                os.close(write_fd)
    outcome = {"returncode": returncode, "signal": -returncode if returncode is not None and returncode < 0 else None,
               "timed_out": timed_out, "elapsed_ms": round((time.monotonic() - started) * 1000),
               "stdout": stdout[-2000:], "stderr": stderr[-2000:]}
    # Electron helper stderr/exit status cannot negate an explicit bridge receipt.
    # Decode exactly one nonce-tagged JSON object, allowing the CLI's `=> ` prefix.
    decoder = json.JSONDecoder()
    matches = []
    start = 0
    while (index := stdout.find(token, start)) >= 0:
        start = index + len(token)
        try:
            value, _ = decoder.raw_decode(stdout[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("ok"), bool):
            matches.append(value)
    if len(matches) != 1:
        raise EditorError("No unambiguous Obsidian result; inspect operation receipt before any replay",
                          code="transport-uncertain", uncertain=True,
                          details=outcome)
    envelope = matches[0]
    if not envelope["ok"]:
        raise EditorError(envelope.get("error", "Editor refused operation"),
                          code=envelope.get("code", "editor-error"),
                          uncertain=envelope.get("uncertain", False),
                          details={**(envelope.get("details") or {}), "transport": outcome})
    value = envelope.get("value")
    if not isinstance(value, dict):
        raise EditorError("Invalid bridge response", code="transport-uncertain", uncertain=True, details=outcome)
    if action == "attach":
        _STATE_DIRS[owner] = payload["state_dir"]
    return value
