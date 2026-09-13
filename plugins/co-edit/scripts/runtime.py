#!/usr/bin/env python3
"""Shared, owner-fenced coedit ledger and JSON command line.

Starting an explicit scope imports previously unknown signed snapshot requests;
that admission is not evidence of historical typing. Known changed revisions
always require new submission, including after event coverage loss.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import select
import signal
import re
import sqlite3
import stat
import sys
import time
from urllib.parse import quote
import uuid


LEASE_SECONDS = 120
CUT_GRACE_SECONDS = 5
if __package__:
    from . import requests as markers
else:
    import requests as markers
VALID = {"submitted", "working", "awaiting-user"}
TERMINAL = {"resolved", "cancelled"}


class RuntimeError(Exception):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code = code
        self.details = details


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def uid():
    return str(uuid.uuid4())


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def bridge(action, payload):
    import editor
    return editor.call(action, payload)


class Runtime:
    def __init__(self, state_dir=None, editor_call=None):
        self.root = Path(state_dir or os.environ.get("COEDIT_STATE_DIR", "~/.local/state/coedit")).expanduser().resolve()
        forbidden = [Path(__file__).resolve().parents[1]]
        for config in (Path.home() / "Library/Application Support/obsidian/obsidian.json", Path.home() / ".config/obsidian/obsidian.json"):
            if config.exists():
                try:
                    settings = json.loads(config.read_text())
                    forbidden.extend(Path(value["path"]).resolve() for value in settings.get("vaults", {}).values() if value.get("path"))
                except (OSError, ValueError, TypeError) as exc:
                    raise RuntimeError("vault-config-unreadable", "Cannot verify runtime state is outside registered Obsidian vaults.", path=str(config)) from exc
        if any(self.root == path or path in self.root.parents for path in forbidden):
            raise RuntimeError("unsafe-state-dir", "Runtime state must be outside every Obsidian vault and the coedit source package.")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "ledger.sqlite3", timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=15000")
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS owners (
          owner TEXT PRIMARY KEY, scope TEXT NOT NULL, harness TEXT NOT NULL,
          pid INTEGER NOT NULL, lease REAL NOT NULL, active INTEGER NOT NULL,
          intent INTEGER NOT NULL DEFAULT 1, hold INTEGER NOT NULL DEFAULT 0,
          pause INTEGER NOT NULL DEFAULT 0, epoch TEXT, seq INTEGER NOT NULL DEFAULT 0,
          ready INTEGER NOT NULL DEFAULT 0, diagnostic TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, text TEXT NOT NULL,
          paused INTEGER NOT NULL DEFAULT 0, error TEXT, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS requests (
          id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
          raw TEXT NOT NULL, revision TEXT NOT NULL, start INTEGER NOT NULL,
          line INTEGER NOT NULL, generation INTEGER NOT NULL DEFAULT 0,
          submission_id TEXT, submitted_at TEXT, state TEXT NOT NULL, reason TEXT,
          missing_since REAL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS requests_document ON requests(document_id);
        CREATE INDEX IF NOT EXISTS requests_state ON requests(state);
        CREATE TABLE IF NOT EXISTS submissions (
          id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id),
          generation INTEGER NOT NULL, revision TEXT NOT NULL, raw TEXT NOT NULL,
          submitted_at TEXT NOT NULL, source TEXT NOT NULL,
          UNIQUE(request_id,generation));
        CREATE TABLE IF NOT EXISTS receipts (
          operation_id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id),
          generation INTEGER NOT NULL, owner TEXT NOT NULL, purpose TEXT NOT NULL,
          payload TEXT NOT NULL, status TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS receipts_request_generation ON receipts(request_id,generation,status,purpose);
        CREATE TABLE IF NOT EXISTS resolutions (
          operation_id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id),
          generation INTEGER NOT NULL, record TEXT NOT NULL, original_raw TEXT NOT NULL,
          sidecar TEXT NOT NULL, anchor TEXT NOT NULL, created_at TEXT NOT NULL,
          status TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS resolutions_request_generation ON resolutions(request_id,generation,status);
        CREATE TABLE IF NOT EXISTS archive_revisions (document_path TEXT NOT NULL,revision TEXT NOT NULL,PRIMARY KEY(document_path,revision));
        CREATE TABLE IF NOT EXISTS diagnostics (
          owner TEXT NOT NULL, epoch TEXT NOT NULL, seq INTEGER NOT NULL,
          data TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(owner,epoch,seq));
        CREATE TABLE IF NOT EXISTS resolution_cleanups (
          operation_id TEXT NOT NULL, ordinal INTEGER NOT NULL,path TEXT NOT NULL,
          expected TEXT NOT NULL,PRIMARY KEY(operation_id,ordinal));
        CREATE TABLE IF NOT EXISTS request_blocks (
          request_id TEXT PRIMARY KEY, raw TEXT NOT NULL, prior_state TEXT NOT NULL,
          continuous INTEGER NOT NULL, started_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS copy_lineage (
          document_id TEXT NOT NULL, raw TEXT NOT NULL, PRIMARY KEY(document_id,raw));
        CREATE TABLE IF NOT EXISTS request_timings (
          request_id TEXT NOT NULL, generation INTEGER NOT NULL, stage TEXT NOT NULL,
          at TEXT NOT NULL, PRIMARY KEY(request_id,generation,stage));
        CREATE TABLE IF NOT EXISTS resolution_reviews (
          request_id TEXT NOT NULL, generation INTEGER NOT NULL, operation_id TEXT NOT NULL,
          reviewed_at TEXT NOT NULL, PRIMARY KEY(request_id,generation,operation_id));
        CREATE TABLE IF NOT EXISTS incidents (
          owner TEXT NOT NULL, key TEXT NOT NULL, data TEXT NOT NULL,
          first_at TEXT NOT NULL, last_at TEXT NOT NULL, recovered_at TEXT,
          count INTEGER NOT NULL, PRIMARY KEY(owner,key));
        CREATE TABLE IF NOT EXISTS notices (
          key TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued');
        CREATE TABLE IF NOT EXISTS ledger_migrations (name TEXT PRIMARY KEY);
        ''')
        os.chmod(self.root / "ledger.sqlite3", 0o600)
        self.editor = editor_call or bridge
        self._notice_context = None
        # Additive migrations preserve all old IDs, receipts and resolution rows.
        with self.transaction():
            if not self.db.execute("SELECT 1 FROM ledger_migrations WHERE name='notice-recovery'").fetchone():
                self.db.execute("ALTER TABLE notices ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
                self.db.execute("ALTER TABLE notices ADD COLUMN retry_at REAL NOT NULL DEFAULT 0")
                self.db.execute("INSERT INTO ledger_migrations VALUES('notice-recovery')")
            if not self.db.execute("SELECT 1 FROM ledger_migrations WHERE name='timing-answer-backfill'").fetchone():
                self.db.execute("""INSERT OR IGNORE INTO request_timings
                  SELECT request_id,generation,'submitted_at',submitted_at FROM submissions""")
                self.db.execute("""INSERT OR IGNORE INTO request_timings
                  SELECT request_id,generation,'committed_at',MIN(updated_at) FROM receipts
                  WHERE status='committed' AND purpose IN ('apply','answer','proposal') GROUP BY request_id,generation""")
                for purpose, stage in (("answer", "answered_at"), ("archive", "archived_at")):
                    self.db.execute("""INSERT OR IGNORE INTO request_timings
                      SELECT request_id,generation,?,MIN(updated_at) FROM receipts
                      WHERE status='committed' AND purpose=? GROUP BY request_id,generation""", (stage, purpose))
                self.db.execute("""UPDATE requests SET state='answered',reason=NULL
                  WHERE state IN ('submitted','working','awaiting-user','repair-needed')
                  AND revision=(SELECT revision FROM submissions WHERE request_id=requests.id AND generation=requests.generation)
                  AND EXISTS (SELECT 1 FROM receipts WHERE request_id=requests.id AND generation=requests.generation AND purpose='answer' AND status='committed')""")
                self.db.execute("INSERT INTO ledger_migrations VALUES('timing-answer-backfill')")
            if not self.db.execute("SELECT 1 FROM ledger_migrations WHERE name='diagnostic-incidents'").fetchone():
                for row in self.db.execute("SELECT owner,epoch,seq,data FROM diagnostics"):
                    item = json.loads(row["data"])
                    key = "legacy:" + row["epoch"] + ":" + str(row["seq"])
                    self.db.execute("INSERT OR IGNORE INTO incidents VALUES(?,?,?,?,?,NULL,1)", (row["owner"], key, json.dumps(item), item.get("time", utc()), item.get("time", utc())))
                self.db.execute("INSERT INTO ledger_migrations VALUES('diagnostic-incidents')")

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def close(self):
        self.db.close()

    def call_editor(self, action, **payload):
        payload.setdefault("state_dir", str(self.root))
        return self.editor(action, payload)

    def timing(self, request_id, generation, stage, at=None):
        self.db.execute("INSERT OR IGNORE INTO request_timings VALUES(?,?,?,?)", (request_id, generation, stage, at or utc()))

    def incident(self, owner, key, item):
        at = utc()
        self.db.execute("""INSERT INTO incidents VALUES(?,?,?,?,?,NULL,1)
          ON CONFLICT(owner,key) DO UPDATE SET data=excluded.data,last_at=excluded.last_at,
          recovered_at=NULL,count=incidents.count+1""", (owner, key, json.dumps(item), at, at))

    def recover_incidents(self, owner, prefix, active=()):
        for row in self.db.execute("SELECT key FROM incidents WHERE owner=? AND recovered_at IS NULL", (owner,)):
            if row["key"].startswith(prefix) and row["key"] not in active:
                self.db.execute("UPDATE incidents SET recovered_at=? WHERE owner=? AND key=?", (utc(), owner, row["key"]))
        self.db.execute("""DELETE FROM incidents WHERE owner=? AND recovered_at IS NOT NULL AND key NOT IN
          (SELECT key FROM incidents WHERE owner=? AND recovered_at IS NOT NULL ORDER BY recovered_at DESC LIMIT 100)""", (owner, owner))

    def queue_notice(self, row_id, message, level="info"):
        if not self._notice_context:
            return
        row = self.db.execute("SELECT r.*,d.path FROM requests r JOIN documents d ON d.id=r.document_id WHERE r.id=?", (row_id,)).fetchone()
        payload = {**self._notice_context, "request_id": row_id, "generation": row["generation"], "path": row["path"], "raw": row["raw"], "revision": row["revision"], "message": message, "level": level}
        payload["key"] = markers.fingerprint(json.dumps([payload["owner"], payload["epoch"], payload["after_seq"], row_id, row["generation"], row["revision"], message]))
        self.db.execute("INSERT OR IGNORE INTO notices(key,owner,payload) VALUES(?,?,?)", (payload["key"], payload["owner"], json.dumps(payload)))

    def flush_notices(self, owner, retry_failed=False):
        epoch = self.owner(owner)["epoch"]
        for row in list(self.db.execute("SELECT * FROM notices WHERE owner=? AND status IN ('queued','failed')", (owner,))):
            payload = json.loads(row["payload"])
            document = self.db.execute("SELECT text,error FROM documents WHERE path=?", (payload["path"],)).fetchone()
            current = self.db.execute("SELECT generation,revision FROM requests WHERE id=?", (payload.get("request_id"),)).fetchone()
            stale = payload["epoch"] != epoch or (current is not None and (
                current["generation"] != payload.get("generation") or current["revision"] != payload["revision"]))
            if not stale and document and document["error"]:
                continue
            if stale or not document or not any(item.raw == payload["raw"] for item in markers.parse(document["text"], payload["path"])):
                self.db.execute("UPDATE notices SET status='superseded' WHERE key=?", (row["key"],))
                self.recover_incidents(owner, "notice:" + row["key"])
                continue
            now = time.time()
            if row["attempts"] >= 3 or row["retry_at"] > now or (row["status"] == "failed" and not retry_failed):
                continue
            claimed = self.db.execute("UPDATE notices SET attempts=attempts+1,retry_at=? WHERE key=? AND attempts=? AND retry_at<=?",
                                      (now + 60, row["key"], row["attempts"], now))
            if not claimed.rowcount:
                continue
            try:
                self.call_editor("notice", **payload)
            except Exception as exc:
                self.db.execute("UPDATE notices SET status='failed',retry_at=? WHERE key=?", (time.time() + 2 ** row["attempts"], row["key"]))
                self.incident(owner, "notice:" + row["key"], {"code": "notice-failed", "message": str(exc), "details": {"key": row["key"]}})
                break
            else:
                self.db.execute("UPDATE notices SET status='delivered' WHERE key=?", (row["key"],))
                self.recover_incidents(owner, "notice:" + row["key"])

    def committed_answer(self, request_id, generation):
        return self.db.execute("SELECT 1 FROM receipts WHERE request_id=? AND generation=? AND purpose='answer' AND status='committed'", (request_id, generation)).fetchone() is not None

    def review_required(self, request_id, generation, operation_id):
        return self.committed_answer(request_id, generation) and not self.db.execute(
            "SELECT 1 FROM resolution_reviews WHERE request_id=? AND generation=? AND operation_id=?",
            (request_id, generation, operation_id)).fetchone()

    def settle_receipt(self, receipt, authorize=True):
        if receipt["status"] not in {"committed", "rejected"}:
            return
        purpose = receipt["purpose"]
        if receipt["status"] == "committed":
            if purpose in {"apply", "answer", "proposal"}:
                self.timing(receipt["request_id"], receipt["generation"], "committed_at", receipt["updated_at"])
            if purpose in {"answer", "archive"}:
                self.timing(receipt["request_id"], receipt["generation"], "answered_at" if purpose == "answer" else "archived_at", receipt["updated_at"])
            if purpose == "answer":
                self.db.execute("""UPDATE requests SET state='answered',reason=NULL,updated_at=?
                  WHERE id=? AND generation=? AND state IN ('submitted','working','awaiting-user','repair-needed','uncertain-write')
                  AND missing_since IS NULL AND revision=(SELECT revision FROM submissions WHERE request_id=requests.id AND generation=requests.generation)
                  AND NOT EXISTS (SELECT 1 FROM request_blocks WHERE request_id=requests.id)
                  AND NOT EXISTS (SELECT 1 FROM documents WHERE id=requests.document_id AND error IS NOT NULL)""",
                  (utc(), receipt["request_id"], receipt["generation"]))
                return
        if authorize:
            self.db.execute("""UPDATE requests SET state=CASE WHEN EXISTS(
                SELECT 1 FROM resolutions WHERE request_id=requests.id AND generation=requests.generation AND status!='resolved')
              THEN 'repair-needed' ELSE 'working' END,reason=NULL,updated_at=?
              WHERE id=? AND generation=? AND state='uncertain-write' AND missing_since IS NULL
              AND revision=(SELECT revision FROM submissions WHERE request_id=requests.id AND generation=requests.generation)
              AND NOT EXISTS (SELECT 1 FROM receipts WHERE request_id=requests.id AND status IN ('prepared','uncertain'))
              AND NOT EXISTS (SELECT 1 FROM receipts WHERE request_id=requests.id AND generation=requests.generation AND purpose='answer' AND status='committed')
              AND NOT EXISTS (SELECT 1 FROM request_blocks WHERE request_id=requests.id)
              AND NOT EXISTS (SELECT 1 FROM documents WHERE id=requests.document_id AND error IS NOT NULL)""",
              (utc(), receipt["request_id"], receipt["generation"]))

    def owner(self, owner, live=True):
        row = self.db.execute("SELECT * FROM owners WHERE owner=?", (owner,)).fetchone()
        if row is None:
            raise RuntimeError("unknown-owner", "Start an explicit file/folder scope first.", owner=owner)
        if live and (not row["active"] or row["lease"] < time.time() or not alive(row["pid"])):
            raise RuntimeError("owner-expired", "The owning harness watcher is not live; reattach its scope.", owner=owner)
        return row

    def admitted(self, owner, path):
        if not isinstance(path, str) or not markers.authorized(owner["scope"], path):
            raise RuntimeError("outside-scope", "Path is outside the explicit scope, unsupported, excluded, or a symlink.", path=path)

    @staticmethod
    def overlaps(a, b):
        if markers.authorized(a, b) or markers.authorized(b, a):
            return True
        pa, pb = Path(a), Path(b)
        return (pa.is_dir() and (pa == pb or pa in pb.parents)) or (pb.is_dir() and pb in pa.parents) or markers.sidecar(a) == markers.sidecar(b)

    def attach(self, scope, owner, harness):
        try:
            uuid.UUID(owner)
        except (ValueError, TypeError):
            raise RuntimeError("invalid-owner", "Owner must be the owning session's UUID.")
        p = Path(scope)
        if not p.is_absolute() or not p.exists() or p.resolve() != p:
            raise RuntimeError("invalid-scope", "Scope must be an existing explicit absolute real file/folder path.")
        if not p.is_dir() and p.suffix.lower() not in markers.SUPPORTED:
            raise RuntimeError("unsupported-format", "Live coedit supports .md and .typ, not this file type.")
        with self.transaction():
            for row in self.db.execute("SELECT * FROM owners WHERE active=1"):
                if row["lease"] >= time.time() and alive(row["pid"]) and self.overlaps(scope, row["scope"]):
                    raise RuntimeError("scope-owned", "An existing live watcher owns an overlapping scope; stop it first.", owner=row["owner"], scope=row["scope"])
            self.db.execute('''INSERT INTO owners(owner,scope,harness,pid,lease,active,intent,created_at)
              VALUES(?,?,?,?,?,1,1,?) ON CONFLICT(owner) DO UPDATE SET scope=excluded.scope,
              harness=excluded.harness,pid=excluded.pid,lease=excluded.lease,active=1,intent=1,
              ready=0,diagnostic=NULL''', (owner, scope, harness, os.getpid(), time.time() + LEASE_SECONDS, utc()))
        try:
            attached = self.call_editor("attach", owner=owner, scope=scope, pid=os.getpid())
            with self.transaction():
                current = self.owner(owner)
                epoch = attached["epoch"]
                if epoch != current["epoch"]:
                    self.db.execute("UPDATE owners SET epoch=?,seq=0 WHERE owner=?", (epoch, owner))
            self.sync(owner, force_gap=True, import_unknown=True)
            self.db.execute("UPDATE owners SET ready=1,diagnostic=NULL WHERE owner=?", (owner,))
            return self.status(owner, synchronize=False)
        except BaseException:
            self.db.execute("UPDATE owners SET active=0,ready=0 WHERE owner=? AND pid=?", (owner, os.getpid()))
            try:
                self.call_editor("detach", owner=owner)
            except Exception:
                pass
            raise

    def stop(self, owner, explicit=True):
        row = self.owner(owner, live=False)
        # Fence before external detach; no new preparation can pass afterward.
        self.db.execute("UPDATE owners SET active=0,ready=0,intent=? WHERE owner=?", (0 if explicit else row["intent"], owner))
        self.call_editor("detach", owner=owner)
        return {"owner": owner, "stopped": True, "intent": not explicit and bool(row["intent"])}

    def _submit(self, row_id, raw, source, at=None):
        row = self.db.execute("SELECT * FROM requests WHERE id=?", (row_id,)).fetchone()
        generation = row["generation"] + 1
        submission, at = uid(), at or utc()
        digest = markers.fingerprint(raw)
        self.db.execute('''INSERT INTO submissions VALUES(?,?,?,?,?,?,?)''', (submission, row_id, generation, digest, raw, at, source))
        self.db.execute('''UPDATE requests SET raw=?,revision=?,generation=?,submission_id=?,submitted_at=?,
          state='submitted',reason=NULL,missing_since=NULL,updated_at=? WHERE id=?''', (raw, digest, generation, submission, at, at, row_id))
        self.db.execute("DELETE FROM request_blocks WHERE request_id=?", (row_id,))
        self.timing(row_id, generation, "submitted_at", at)
        if source != "initial-snapshot":
            self.queue_notice(row_id, "Submitted exact request revision.")

    def _reconcile(self, path, text, *, gap=False, event=False, explicit=None, at=None, old_path=None, import_unknown=False):
        if old_path and old_path != path:
            old = self.db.execute("SELECT * FROM documents WHERE path=?", (old_path,)).fetchone()
            other = self.db.execute("SELECT id FROM documents WHERE path=?", (path,)).fetchone()
            if old and not other:
                self.db.execute("UPDATE documents SET path=? WHERE id=?", (path, old["id"]))
        doc = self.db.execute("SELECT * FROM documents WHERE path=?", (path,)).fetchone()
        new_doc = doc is None
        if new_doc:
            doc_id = uid()
            self.db.execute("INSERT INTO documents VALUES(?,?,?,0,NULL,?)", (doc_id, path, "", utc()))
            doc = self.db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        parsed = markers.parse(text, path)
        old_counts = {}
        for item in markers.parse(doc["text"], path):
            old_counts[item.raw] = old_counts.get(item.raw, 0) + 1
        for raw, count in old_counts.items():
            if count > 1:
                self.db.execute("INSERT OR IGNORE INTO copy_lineage VALUES(?,?)", (doc["id"], raw))
        paused = any(item.kind == "PAUSE" for item in parsed)
        parsed = [item for item in parsed if item.kind != "PAUSE"]
        rows = list(self.db.execute("SELECT * FROM requests WHERE document_id=? ORDER BY start", (doc["id"],)))
        current = {}
        for item in parsed:
            current.setdefault(item.raw, []).append(item)
        # Invalidate ambiguity provenance BEFORE the exact-match fast path.
        for block in list(self.db.execute("SELECT b.* FROM request_blocks b JOIN requests r ON r.id=b.request_id WHERE r.document_id=?", (doc["id"],))):
            if gap or block["raw"] not in current:
                self.db.execute("UPDATE request_blocks SET continuous=0 WHERE request_id=?", (block["request_id"],))
                self.db.execute("UPDATE requests SET state='needs-resubmission',reason=? WHERE id=? AND state NOT IN ('resolved','cancelled')", ("Duplicate continuity was lost; remove and reinsert ⏵ to submit.", block["request_id"]))
        rows = list(self.db.execute("SELECT * FROM requests WHERE document_id=? ORDER BY start", (doc["id"],)))
        used = set()
        remaining = []
        for raw, items in current.items():
            exact = [row for row in rows if row["raw"] == raw]
            if len(items) != 1 or len(exact) > 1:
                self.db.execute("INSERT OR IGNORE INTO copy_lineage VALUES(?,?)", (doc["id"], raw))
                # One durable blocked identity per ambiguous raw is sufficient;
                # never select an occurrence or collapse two into executable work.
                if not exact:
                    row_id = uid()
                    self.db.execute("INSERT INTO requests(id,document_id,raw,revision,start,line,state,reason,updated_at) VALUES(?,?,?,?,?,?,'needs-resubmission',?,?)", (row_id, doc["id"], raw, markers.fingerprint(raw), items[0].start, items[0].line, "Identical request occurrences are ambiguous; make their text distinct, then resubmit.", utc()))
                    exact = [self.db.execute("SELECT * FROM requests WHERE id=?", (row_id,)).fetchone()]
                    used.add(row_id)
                for row in exact:
                    used.add(row["id"])
                    if row["state"] not in TERMINAL:
                        created = self.db.execute("INSERT OR IGNORE INTO request_blocks VALUES(?,?,?,?,?)", (row["id"], raw, row["state"], int(not gap and row["missing_since"] is None and raw in doc["text"]), utc())).rowcount
                        if created:
                            self.queue_notice(row["id"], "Identical requests are ambiguous; edits are blocked.", "warning")
                continue
            item = items[0]
            if exact:
                row = exact[0]
                used.add(row["id"])
                block = self.db.execute("SELECT * FROM request_blocks WHERE request_id=?", (row["id"],)).fetchone()
                if block:
                    # Only new, continuously observed ambiguity can restore.
                    if not block["continuous"]:
                        self.db.execute("UPDATE requests SET state='needs-resubmission',reason=? WHERE id=? AND state NOT IN ('resolved','cancelled')", ("Duplicate continuity was lost; remove and reinsert ⏵ to submit.", row["id"]))
                    if block["continuous"] and block["raw"] == raw:
                        self.db.execute("UPDATE requests SET state=?,reason=NULL WHERE id=? AND state NOT IN ('resolved','cancelled')", (block["prior_state"], row["id"]))
                    self.db.execute("DELETE FROM request_blocks WHERE request_id=?", (row["id"],))
                    row = self.db.execute("SELECT * FROM requests WHERE id=?", (row["id"],)).fetchone()
                reason = None if row["missing_since"] is not None and row["state"] in VALID else row["reason"]
                self.db.execute("UPDATE requests SET start=?,line=?,missing_since=NULL,reason=?,updated_at=? WHERE id=?", (item.start, item.line, reason, utc(), row["id"]))
                if explicit == raw:
                    self._submit(row["id"], raw, "shortcut", at)
                continue
            remaining.append(item)
        unmatched = [row for row in rows if row["id"] not in used and (row["state"] not in TERMINAL or row["raw"] in doc["text"])]
        # Conservatively pair changed carriers by document order. A removed old
        # request plus a new one is not permission to reinterpret a visible token.
        for index, item in enumerate(remaining):
            previous = unmatched[index] if index < len(unmatched) else None
            row_id = previous["id"] if previous else uid()
            used.add(row_id)
            historical = self.db.execute("SELECT 1 FROM archive_revisions WHERE document_path=? AND revision=?", (path, item.revision)).fetchone()
            if previous:
                self.db.execute("UPDATE requests SET raw=?,revision=?,start=?,line=?,state='needs-resubmission',reason=?,missing_since=NULL,updated_at=? WHERE id=?", (item.raw, item.revision, item.start, item.line, "Request revision changed; remove and reinsert ⏵ to submit.", utc(), row_id))
                self.db.execute("DELETE FROM request_blocks WHERE request_id=?", (row_id,))
            else:
                state = "resolved" if historical else "needs-resubmission"
                self.db.execute("INSERT INTO requests(id,document_id,raw,revision,start,line,state,reason,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (row_id, doc["id"], item.raw, item.revision, item.start, item.line, state, "Archived request; undo does not authorize replay." if historical else "Unsigned or unproven revision; deliberately submit with ⏵.", utc()))
            explicit_match = explicit == item.raw
            lineage = [entry for stored in self.db.execute("SELECT raw FROM copy_lineage WHERE document_id=?", (doc["id"],)) for entry in markers.parse(stored["raw"], path)]
            derived = previous is None and item.signed and any(entry.kind == item.kind and entry.author == item.author for entry in lineage)
            typed = event and not gap and item.signed and previous is not None and markers.token_only_submission(previous["raw"], item, path)
            imported = import_unknown and item.signed and not previous and not derived
            if (not historical or previous is not None or explicit_match) and (explicit_match or typed or imported):
                self._submit(row_id, item.raw, "shortcut" if explicit_match else "typed" if typed else "initial-snapshot", at)
            elif derived and event and not import_unknown:
                self.queue_notice(row_id, "Copied old signature does not submit changed wording; remove and reinsert ⏵.", "warning")
        now = time.time()
        for row in rows:
            if row["id"] in used or row["state"] in TERMINAL:
                continue
            missing = row["missing_since"] or now
            state, reason = row["state"], "Request is absent; cut/paste grace is active."
            if now - missing >= CUT_GRACE_SECONDS:
                state, reason = "cancelled", "Request removed beyond cut/paste grace; no automatic replay."
            self.db.execute("UPDATE requests SET missing_since=?,state=?,reason=?,updated_at=? WHERE id=?", (missing, state, reason, utc(), row["id"]))
        self.db.execute("UPDATE documents SET text=?,paused=?,error=NULL,updated_at=? WHERE id=?", (text, paused, utc(), doc["id"]))

    def sync(self, owner, force_gap=False, import_unknown=False):
        own = self.owner(owner)
        try:
            snap = self.call_editor("snapshot", owner=owner, after_seq=own["seq"])
        except Exception as exc:
            with self.transaction():
                self.incident(owner, "transport:snapshot", error_json(exc)["error"])
                self.db.execute("UPDATE owners SET ready=0,diagnostic=? WHERE owner=?", (str(exc), owner))
                for block in list(self.db.execute("SELECT b.request_id,d.path FROM request_blocks b JOIN requests r ON r.id=b.request_id JOIN documents d ON d.id=r.document_id")):
                    if markers.authorized(own["scope"], block["path"]):
                        self.db.execute("UPDATE request_blocks SET continuous=0 WHERE request_id=?", (block["request_id"],))
                        self.db.execute("UPDATE requests SET state='needs-resubmission',reason=? WHERE id=? AND state NOT IN ('resolved','cancelled')", ("Duplicate continuity was lost through a snapshot error; resubmit.", block["request_id"]))
            raise
        epoch, seq = snap["epoch"], snap["seq"]
        self._notice_context = {"owner": owner, "epoch": epoch, "after_seq": seq}
        with self.transaction():
            self.recover_incidents(owner, "transport:")
            self.recover_incidents(owner, "post-commit:")
            self.recover_incidents(owner, "legacy:")
            own = self.owner(owner)
            gap = force_gap or bool(snap.get("coverage_lost")) or own["epoch"] != epoch
            if own["epoch"] == epoch and seq < own["seq"]:
                return snap
            cursor = own["seq"] if own["epoch"] == epoch else 0
            documents = [doc for doc in snap.get("documents", []) if markers.authorized(own["scope"], doc["path"])]
            for document in documents:
                path = document["path"]
                self.admitted(own, path)
                if not document.get("error"):
                    for source_path, raw in markers.archive_records(document["text"], path):
                        if markers.authorized(own["scope"], source_path):
                            self.db.execute("INSERT OR IGNORE INTO archive_revisions VALUES(?,?)", (source_path, markers.fingerprint(raw)))
            for event_row in sorted(snap.get("events", []), key=lambda row: row["seq"]):
                if event_row["seq"] <= cursor:
                    continue
                if not markers.authorized(own["scope"], event_row["path"]):
                    continue
                if event_row.get("old_path") and not markers.authorized(own["scope"], event_row["old_path"]):
                    event_row = {key: value for key, value in event_row.items() if key != "old_path"}
                if event_row.get("error"):
                    self.db.execute("UPDATE request_blocks SET continuous=0 WHERE request_id IN (SELECT r.id FROM requests r JOIN documents d ON d.id=r.document_id WHERE d.path=?)", (event_row["path"],))
                    self.db.execute("UPDATE requests SET state='needs-resubmission',reason=? WHERE id IN (SELECT request_id FROM request_blocks WHERE continuous=0) AND state NOT IN ('resolved','cancelled')", ("Duplicate continuity was lost through an editor event error; resubmit.",))
                    continue
                self._reconcile(event_row["path"], event_row.get("text", ""), gap=gap, event=event_row.get("kind") == "change" and not event_row.get("operation_id"), explicit=event_row.get("raw") if event_row.get("kind") == "submit" else None, at=event_row.get("time"), old_path=event_row.get("old_path"), import_unknown=import_unknown)
            seen = set()
            for document in documents:
                path = document["path"]
                seen.add(path)
                if document.get("error"):
                    if not self.db.execute("SELECT 1 FROM documents WHERE path=?", (path,)).fetchone():
                        self.db.execute("INSERT INTO documents VALUES(?,?,?,0,NULL,?)", (uid(), path, "", utc()))
                    self.db.execute("UPDATE documents SET error=? WHERE path=?", (str(document["error"]), path))
                    self.db.execute("UPDATE request_blocks SET continuous=0 WHERE request_id IN (SELECT r.id FROM requests r JOIN documents d ON d.id=r.document_id WHERE d.path=?)", (path,))
                    self.db.execute("UPDATE requests SET state='needs-resubmission',reason=? WHERE id IN (SELECT request_id FROM request_blocks WHERE continuous=0) AND state NOT IN ('resolved','cancelled')", ("Duplicate continuity was lost through an unreadable buffer; resubmit.",))
                    continue
                self._reconcile(path, document["text"], gap=gap, import_unknown=import_unknown)
            for doc in list(self.db.execute("SELECT path FROM documents")):
                if markers.authorized(own["scope"], doc["path"]) and doc["path"] not in seen:
                    self._reconcile(doc["path"], "", gap=True)
            active_incidents = []
            for document in documents:
                if document.get("error"):
                    key = "snapshot:document:" + document["path"]
                    active_incidents.append(key)
                    self.incident(owner, key, {"code": "document-blocked", "message": str(document["error"]), "path": document["path"]})
            for item in snap.get("diagnostics", []):
                key = "snapshot:" + str(item.get("code", "diagnostic")) + ":" + str(item.get("path", ""))
                active_incidents.append(key)
                self.incident(owner, key, {"message": item.get("message", str(item)), **item})
            self.recover_incidents(owner, "snapshot:", active_incidents)
            active_requests = []
            for row in self.db.execute("SELECT r.*,d.path FROM requests r JOIN documents d ON d.id=r.document_id WHERE r.generation>0 AND r.state IN ('needs-resubmission','uncertain-write')"):
                if markers.authorized(own["scope"], row["path"]):
                    key = "request:" + row["id"]
                    active_requests.append(key)
                    if row["state"] == "needs-resubmission" and not self.db.execute("SELECT 1 FROM incidents WHERE owner=? AND key=? AND recovered_at IS NULL", (owner, key)).fetchone():
                        self.queue_notice(row["id"], "Request invalidated; remove and reinsert ⏵ to submit.", "warning")
                    self.incident(owner, key, {"code": row["state"], "message": row["reason"] or row["state"], "path": row["path"], "request_id": row["id"]})
            self.recover_incidents(owner, "request:", active_requests)
            active_operations = []
            for incident in self.db.execute("SELECT key,data FROM incidents WHERE owner=? AND recovered_at IS NULL AND key LIKE 'operation:%'", (owner,)):
                detail = json.loads(incident["data"])
                request_id = detail.get("request_id")
                current = self.db.execute("SELECT state,generation,revision FROM requests WHERE id=?", (request_id,)).fetchone()
                obsolete = current and (current["state"] in TERMINAL or (
                    detail.get("revision") is not None and
                    (detail["revision"] != current["revision"] or detail.get("generation") != current["generation"])))
                unfinished = self.db.execute("SELECT 1 FROM receipts WHERE request_id=? AND status IN ('prepared','uncertain')", (request_id,)).fetchone() or self.db.execute("SELECT 1 FROM resolutions WHERE request_id=? AND status!='resolved'", (request_id,)).fetchone()
                if not obsolete or unfinished:
                    active_operations.append(incident["key"])
            self.recover_incidents(owner, "operation:", active_operations)
            diagnostic = json.dumps(active_incidents) if active_incidents else None
            self.db.execute("UPDATE owners SET epoch=?,seq=?,lease=?,diagnostic=?,ready=1 WHERE owner=?", (epoch, seq, time.time() + LEASE_SECONDS, diagnostic, owner))
            for receipt in self.db.execute("""SELECT p.*,d.path FROM requests r JOIN receipts p ON r.id=p.request_id AND r.generation=p.generation
              JOIN documents d ON d.id=r.document_id WHERE
              (r.state='uncertain-write' AND p.status IN ('committed','rejected')) OR
              (p.status='committed' AND p.purpose='answer' AND r.state IN ('submitted','working','awaiting-user','repair-needed'))"""):
                if receipt["path"] in seen:
                    self.settle_receipt(receipt)
        # Durable commit precedes ack: crash at either boundary is idempotent.
        self._notice_context = None
        self.call_editor("ack", owner=owner, through_seq=seq)
        self.flush_notices(owner, retry_failed=True)
        return snap

    def request(self, owner, request_id, generation=None, writable=False, resolution_id=None):
        own = self.owner(owner)
        row = self.db.execute("SELECT r.*,d.path AS file,d.text,d.error,d.paused FROM requests r JOIN documents d ON d.id=r.document_id WHERE r.id=?", (request_id,)).fetchone()
        if row is None:
            raise RuntimeError("unknown-request", "Request ID is not in the durable ledger.", request_id=request_id)
        self.admitted(own, row["file"])
        if generation is not None and (not isinstance(generation, int) or isinstance(generation, bool) or generation != row["generation"]):
            raise RuntimeError("stale-generation", "Read the current request and use its explicitly submitted generation.", generation=row["generation"])
        if writable:
            if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
                raise RuntimeError("generation-required", "Mutation requires a positive explicitly submitted generation, never null.")
            if own["hold"]:
                raise RuntimeError("held", "Applies are held; release hold before writing.")
            if row["error"]:
                raise RuntimeError("document-blocked", "Resolve conflicting or inaccessible editor buffers first.", reason=row["error"])
            if self.db.execute("SELECT 1 FROM request_blocks WHERE request_id=?", (request_id,)).fetchone():
                raise RuntimeError("ambiguous-request", "Identical request occurrences block mutation.")
            if self.committed_answer(request_id, generation) and (not resolution_id or self.review_required(request_id, generation, resolution_id)):
                raise RuntimeError("review-required", "Keep the answer visible until the human reviews it; resolve with reviewed: true.")
            resolution = self.db.execute("SELECT operation_id FROM resolutions WHERE request_id=? AND generation=? AND status!='resolved'", (request_id, generation)).fetchone()
            if resolution and resolution["operation_id"] != resolution_id:
                raise RuntimeError("resolution-in-progress", "Only the saved resolution's unfinished archive/cleanup stages may continue.", operation_id=resolution["operation_id"])
            unfinished = self.db.execute("SELECT operation_id,status FROM receipts WHERE request_id=? AND status IN ('prepared','uncertain') LIMIT 1", (request_id,)).fetchone()
            if unfinished:
                raise RuntimeError("uncertain-write", "Reconcile the outstanding operation before any new write, even after resubmission.", **dict(unfinished))
            allowed_state = row["state"] in VALID or (row["state"] == "answered" and resolution_id is not None) or (
                row["state"] == "repair-needed" and resolution is not None and resolution["operation_id"] == resolution_id)
            if not allowed_state or row["missing_since"] is not None or not row["generation"]:
                raise RuntimeError("not-authorized", "Current request is not an applicable submitted revision.", state=row["state"], reason=row["reason"])
            submitted = self.db.execute("SELECT revision FROM submissions WHERE request_id=? AND generation=?", (request_id, row["generation"])).fetchone()
            if not submitted or submitted["revision"] != row["revision"]:
                raise RuntimeError("revision-invalidated", "The visible request differs from the signed submission; resubmit it.")
        return row

    def public(self, row):
        path = row["file"]
        link = "obsidian://open?path=" + quote(path, safe="")
        result = {key: row[key] for key in ("id", "generation", "submission_id", "revision", "submitted_at", "file", "raw", "line", "state", "reason", "missing_since")}
        submission = self.db.execute("SELECT revision FROM submissions WHERE request_id=? AND generation=?", (row["id"], row["generation"])).fetchone()
        result["submitted_revision"] = submission["revision"] if submission else None
        result.update(link=link, sidecar=markers.sidecar(path), sidecar_link="obsidian://open?path=" + quote(markers.sidecar(path), safe=""))
        parsed = markers.parse(row["raw"], path)
        body = parsed[0].body if parsed else row["raw"]
        result["summary"] = " ".join(body.rstrip().removesuffix(markers.TOKEN).split())[:180]
        stages = ("submitted_at", "hint_emitted_at", "adapter_received_at", "handoff_at", "queue_confirmed_at", "picked_up_at", "committed_at", "answered_at", "archived_at")
        result["timings"] = dict.fromkeys(stages)
        result["timings"].update({item["stage"]: item["at"] for item in self.db.execute("SELECT stage,at FROM request_timings WHERE request_id=? AND generation=?", (row["id"], row["generation"]))})
        result["recovery"] = self.recovery(row["id"], row["generation"])
        block = self.db.execute("SELECT continuous,prior_state FROM request_blocks WHERE request_id=?", (row["id"],)).fetchone()
        result["blocked"] = bool(block or row["error"] or row["missing_since"] is not None)
        if block:
            result["blocker"] = "Identical raw requests are ambiguous." if block["continuous"] else "Duplicate continuity was lost; resubmit."
            result["pre_block_state"] = block["prior_state"]
        pending_resolution = self.db.execute("SELECT operation_id FROM resolutions WHERE request_id=? AND generation=? AND status!='resolved' ORDER BY created_at LIMIT 1", (row["id"], row["generation"])).fetchone()
        code, label = "submit", "Remove and reinsert ⏵ to submit this revision."
        if self.db.execute("SELECT 1 FROM receipts WHERE request_id=? AND status IN ('prepared','uncertain')", (row["id"],)).fetchone():
            code, label = "reconcile", "Reconcile receipts; never replay an uncertain edit."
        elif result["blocked"]:
            code, label = "unblock", result.get("blocker") or row["error"] or "Restore the exact request before editing."
        elif pending_resolution and row["state"] in VALID | {"answered", "repair-needed"} and not self.review_required(row["id"], row["generation"], pending_resolution["operation_id"]):
            code, label = "repair", "Resume the saved resolution; do not repeat committed work."
        elif self.committed_answer(row["id"], row["generation"]) and row["state"] in VALID | {"answered", "repair-needed"}:
            code, label = "review", "Read the visible answer; resolve only after human review."
        elif row["state"] == "repair-needed":
            code, label = "repair", "Resume the saved resolution; do not repeat the main edit."
        elif row["state"] == "awaiting-user":
            code, label = "await-user", "Wait for the human's decision."
        elif row["state"] in {"submitted", "working"} and result["recovery"]["apply"]["status"] == "committed":
            code, label = "resolve", "Resolve the completed edit; never replay the main edit."
        elif row["state"] in {"submitted", "working"}:
            code, label = "work", "Read the exact request and mark it working before processing."
        elif row["state"] in TERMINAL:
            code, label = "none", "No action; committed work must not be replayed."
        result["next_action"] = {"code": code, "label": label}
        if "error" in row.keys() and row["error"]:
            result["reason"] = row["error"]
            result["blocked"] = True
        return result

    def recovery(self, request_id, generation):
        result = {}
        for purpose in ("apply", "answer", "archive", "cleanup"):
            rows = list(self.db.execute("SELECT operation_id,status FROM receipts WHERE request_id=? AND generation=? AND purpose=? ORDER BY created_at,operation_id", (request_id, generation, purpose)))
            states = {row["status"] for row in rows}
            status = "none"
            if "uncertain" in states:
                status = "uncertain"
            elif "prepared" in states:
                status = "partial" if "committed" in states else "prepared"
            elif states == {"committed"}:
                status = "committed"
            elif "committed" in states:
                status = "partial"
            elif states:
                status = "blocked"
            result[purpose] = {"status": status, "operation_ids": [row["operation_id"] for row in rows]}
        return result

    def status(self, owner=None, synchronize=True):
        if owner and synchronize:
            own = self.owner(owner, live=False)
            if own["active"] and own["lease"] >= time.time() and alive(own["pid"]):
                self.sync(owner)
        owners = [self.owner(owner, live=False)] if owner else list(self.db.execute("SELECT * FROM owners ORDER BY created_at"))
        scopes, pending, documents = [], [], []
        for own in owners:
            live = bool(own["active"] and own["lease"] >= time.time() and alive(own["pid"]))
            scopes.append({"owner": own["owner"], "scope": own["scope"], "harness": own["harness"], "ready": bool(live and own["ready"]), "active": live, "intent": bool(own["intent"]), "hold": bool(own["hold"]), "pause": bool(own["pause"]), "error": own["diagnostic"]})
        for row in self.db.execute("SELECT r.*,d.path AS file,d.error FROM requests r JOIN documents d ON d.id=r.document_id WHERE state NOT IN ('resolved','cancelled') ORDER BY submitted_at,r.id"):
            if any(markers.authorized(own["scope"], row["file"]) for own in owners):
                pending.append(self.public(row))
        for doc in self.db.execute("SELECT path,error,paused FROM documents"):
            if any(markers.authorized(own["scope"], doc["path"]) for own in owners):
                documents.append({"path": doc["path"], "format": "typst" if Path(doc["path"]).suffix.lower() == ".typ" else "markdown", "editor_capability": "blocked" if doc["error"] else "guarded-editor-required", "error": doc["error"], "paused": bool(doc["paused"])})
        result = {"scopes": scopes, "pending": pending, "documents": documents, "ready": bool(scopes and all(row["ready"] for row in scopes))}
        result["diagnostics"] = {"current": [], "history": []}
        for row in self.db.execute("SELECT * FROM incidents ORDER BY first_at,key"):
            if any(own["owner"] == row["owner"] for own in owners):
                item = {**json.loads(row["data"]), **{key: row[key] for key in ("first_at", "last_at", "recovered_at", "count")}}
                item.setdefault("code", "diagnostic")
                item.setdefault("message", item["code"])
                result["diagnostics"]["history" if row["recovered_at"] else "current"].append(item)
        eligible = []
        for item in pending:
            doc = next(doc for doc in documents if doc["path"] == item["file"])
            scope = next(scope for scope in scopes if markers.authorized(scope["scope"], item["file"]))
            if scope["ready"] and not scope["pause"] and not scope["hold"] and not doc["paused"] and not item["blocked"] and item["state"] in {"submitted", "repair-needed", "uncertain-write"} and not self.committed_answer(item["id"], item["generation"]):
                eligible.append(item)
        result["eligible"] = eligible
        result["revision"] = markers.fingerprint(json.dumps([{key: item[key] for key in ("id", "generation", "revision", "state")} for item in eligible], sort_keys=True))
        result.update(eligible_count=len(eligible), answered_count=sum(item["state"] == "answered" for item in pending),
                      awaiting_user_count=sum(item["state"] == "awaiting-user" for item in pending),
                      unsubmitted_count=sum(item["state"] == "needs-resubmission" for item in pending),
                      blocked_count=sum(item["blocked"] for item in pending),
                      current_diagnostics=result["diagnostics"]["current"])
        if owner:
            result.update({key: scopes[0][key] for key in ("owner", "scope", "hold", "pause")})
        return result

    @staticmethod
    def status_event(status):
        fields = ("owner", "scope", "hold", "pause", "ready", "revision", "eligible_count", "answered_count", "awaiting_user_count", "unsubmitted_count", "blocked_count", "current_diagnostics")
        return {"type": "status", **{key: status[key] for key in fields}}

    @staticmethod
    def status_signature(event, status):
        compact = {**event, "current_diagnostics": [{key: item[key] for key in ("code", "message", "path", "request_id") if key in item} for item in event["current_diagnostics"]]}
        compact["recovery"] = [{"id": item["id"], "generation": item["generation"], "recovery": item["recovery"], "next_action": item["next_action"]} for item in status["pending"]]
        return markers.fingerprint(json.dumps(compact, sort_keys=True))

    def read_request(self, owner, request_id):
        self.sync(owner)
        row = self.request(owner, request_id)
        adjacent = self.db.execute("SELECT path,text,error FROM documents WHERE path=?", (markers.sidecar(row["file"]),)).fetchone()
        receipts = [dict(item) for item in self.db.execute("SELECT * FROM receipts WHERE request_id=? ORDER BY created_at", (request_id,))]
        resolutions = [dict(item) for item in self.db.execute("SELECT * FROM resolutions WHERE request_id=? ORDER BY created_at", (request_id,))]
        return {"request": self.public(row), "document": {"path": row["file"], "text": row["text"], "error": row["error"]}, "sidecar": dict(adjacent) if adjacent else None, "operations": receipts, "resolutions": resolutions}

    def reconcile(self, owner, request_id, generation=None):
        row = self.request(owner, request_id)
        generation = row["generation"] if generation is None else generation
        if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1 or not self.db.execute("SELECT 1 FROM submissions WHERE request_id=? AND generation=?", (request_id, generation)).fetchone():
            raise RuntimeError("unknown-generation", "Reconcile requires an existing submitted generation.")
        # Snapshot/receipt only: never ensure, ack, notice, resolve or write.
        snapshot_error, documents, ambiguous = None, {}, False
        own = self.owner(owner)
        try:
            snap = self.call_editor("snapshot", owner=owner, after_seq=own["seq"])
            documents = {item["path"]: item for item in snap.get("documents", []) if markers.authorized(own["scope"], item["path"])}
            document = documents.get(row["file"])
            count = document["text"].count(row["raw"]) if document and not document.get("error") else 0
            ambiguous = count > 1
            drifted = any(event.get("path") == row["file"] and event["seq"] > own["seq"] and
                          (event.get("error") or event.get("text", "").count(row["raw"]) == 0)
                          for event in snap.get("events", []))
            if (count == 0 or drifted) and row["state"] not in TERMINAL:
                self.db.execute("UPDATE requests SET state='needs-resubmission',reason=?,updated_at=? WHERE id=?",
                                ("Receipt inspection found lost request authority; normal synchronization must process current events.", utc(), request_id))
        except Exception as exc:
            snapshot_error = error_json(exc)["error"]
        outcomes = []
        for receipt in list(self.db.execute("SELECT * FROM receipts WHERE request_id=? AND generation=? ORDER BY created_at", (request_id, generation))):
            try:
                proof = self.receipt(owner, receipt["operation_id"], authorize=False)
                outcomes.append({"operation_id": receipt["operation_id"], "purpose": receipt["purpose"], **proof})
            except RuntimeError as exc:
                outcomes.append({"operation_id": receipt["operation_id"], "purpose": receipt["purpose"], "status": receipt["status"], "error": error_json(exc)["error"]})
        resolutions = []
        for saved in self.db.execute("SELECT * FROM resolutions WHERE request_id=? AND generation=?", (request_id, generation)):
            document = documents.get(saved["sidecar"])
            cleanups = list(self.db.execute("SELECT * FROM resolution_cleanups WHERE operation_id=? ORDER BY ordinal", (saved["operation_id"],)))
            present = bool(not snapshot_error and self.archive_present(saved, document, cleanups, row["file"]))
            resolutions.append({**dict(saved), "archive_present": present})
            if present:
                base = saved["operation_id"] + ":archive"
                attempts = [row for row in self.db.execute("SELECT * FROM receipts WHERE request_id=? AND generation=? AND purpose='archive' ORDER BY created_at,rowid", (request_id, generation)) if row["operation_id"] == base or row["operation_id"].startswith(base + ":")]
                receipt = next((row for row in reversed(attempts) if row["status"] != "rejected"), None)
                archive_id = receipt["operation_id"] if receipt else base if not attempts else base + ":" + str(len(attempts) + 1)
                if not receipt or receipt["status"] != "committed":
                    proof = {"operation_id": archive_id, "status": "committed", "source": "archive-anchor", "path": saved["sidecar"]}
                    with self.transaction():
                        if receipt:
                            self.db.execute("UPDATE receipts SET status='committed',result=?,updated_at=? WHERE operation_id=?", (json.dumps(proof), utc(), archive_id))
                        else:
                            self.db.execute("INSERT INTO receipts VALUES(?,?,?,?,?,?,?,?,?,?)", (archive_id, request_id, generation, owner, "archive", "{}", "committed", json.dumps(proof), utc(), utc()))
                        self.timing(request_id, generation, "archived_at")
                    outcomes = [outcome for outcome in outcomes if outcome["operation_id"] != archive_id]
                    outcomes.append({"purpose": "archive", **proof})
        if not snapshot_error:
            with self.transaction():
                for receipt in self.db.execute("SELECT * FROM receipts WHERE request_id=? AND generation=? AND status='committed'", (request_id, generation)):
                    self.settle_receipt(receipt, authorize=False)
        current = self.public(self.request(owner, request_id))
        if ambiguous:
            current.update(blocked=True, blocker="Identical request occurrences are ambiguous.",
                           next_action={"code": "unblock", "label": "Remove ambiguity before any mutation."})
        return {"request": current, "generation": generation, "recovery": self.recovery(request_id, generation), "receipts": outcomes, "resolutions": resolutions, "snapshot_error": snapshot_error}

    def delivery(self, owner, requests, stage):
        self.owner(owner)
        if stage not in {"adapter_received", "handoff", "queue_confirmed"} or not isinstance(requests, list):
            raise RuntimeError("invalid-delivery", "Supply exact request identities and an observed delivery stage.")
        accepted, stale = [], []
        with self.transaction():
            for identity in requests:
                if not isinstance(identity, dict) or set(identity) != {"id", "generation", "revision"}:
                    raise RuntimeError("invalid-delivery", "Each delivery identity requires only id, generation and revision.")
                row = self.request(owner, identity["id"])
                if isinstance(identity["generation"], bool) or not isinstance(identity["generation"], int) or row["generation"] != identity["generation"] or row["revision"] != identity["revision"] or not row["generation"]:
                    stale.append(identity)
                    continue
                self.timing(row["id"], row["generation"], stage + "_at")
                accepted.append(identity)
        return {"owner": owner, "stage": stage, "recorded": accepted, "stale": stale}

    def submit(self, owner):
        if not isinstance(owner, str) or not owner:
            raise RuntimeError("owner-required", "Deliberate native signing requires its owning harness UUID.")
        snap = self.sync(owner)
        active = snap.get("active")
        if not active:
            raise RuntimeError("no-active-editor", "Focus the request in an Obsidian Markdown/Typst editor.")
        own = self.owner(owner)
        self.admitted(own, active["path"])
        document = next((doc for doc in snap["documents"] if doc["path"] == active["path"]), None)
        if not document or document.get("error"):
            raise RuntimeError("active-buffer-unavailable", "The active editor does not have an unambiguous live snapshot.")
        text, cursor = document["text"], active["cursor_offset"]
        candidates = [item for item in markers.parse(text, active["path"]) if item.start <= cursor <= item.end and item.kind != "PAUSE"]
        if len(candidates) != 1:
            raise RuntimeError("cursor-not-request", "Place the cursor inside one executable user request, outside examples/history.")
        item = candidates[0]
        if text.count(item.raw) != 1:
            raise RuntimeError("ambiguous-request", "Identical raw request occurs more than once; make it distinct before submitting.")
        payload = dict(owner=owner, path=active["path"], raw=item.raw, replacement=item.submitted_raw(), after_seq=own["seq"], epoch=own["epoch"])
        result = self.call_editor("submit", **payload)
        self.sync(owner)
        submitted_raw = result.get("raw", item.submitted_raw())
        rows = list(self.db.execute("SELECT r.id FROM requests r JOIN documents d ON d.id=r.document_id WHERE d.path=? AND r.raw=?", (active["path"], submitted_raw)))
        if len(rows) != 1:
            raise RuntimeError("submission-not-recorded", "Bridge submission could not be reconciled uniquely; inspect status before retrying.")
        return {"owner": owner, "request": self.public(self.request(owner, rows[0]["id"]))}

    def receipt(self, owner, operation_id, authorize=True):
        old = self.db.execute("SELECT * FROM receipts WHERE operation_id=?", (operation_id,)).fetchone()
        if not old:
            return None
        self.request(owner, old["request_id"])
        if old["status"] == "committed":
            # A committed proof is immutable even after a human undoes the edit.
            return json.loads(old["result"])
        try:
            proof = self.call_editor("receipt", owner=old["owner"], operation_id=operation_id)
        except Exception as exc:
            proof = {"status": "unknown", "error": str(exc)}
        if proof.get("status") == "committed":
            self.db.execute("UPDATE receipts SET status='committed',result=?,updated_at=? WHERE operation_id=?", (json.dumps(proof), utc(), operation_id))
            self.settle_receipt({**dict(old), "status": "committed", "updated_at": utc()}, authorize=authorize)
            return proof
        if proof.get("status") == "rejected" and proof.get("attempted") is False:
            self.db.execute("UPDATE receipts SET status='rejected',result=?,updated_at=? WHERE operation_id=?", (json.dumps(proof), utc(), operation_id))
            raise RuntimeError("operation-rejected", "Editor durably proved no mutation was attempted; use a fresh guarded attempt, never replay this ID.", operation_id=operation_id)
        if old["status"] == "rejected":
            raise RuntimeError("operation-rejected", "Editor proved this operation did not mutate. Reread current buffers and use a new operation_id.", operation_id=operation_id)
        raise RuntimeError("uncertain-write", "An operation was already prepared without committed proof. Do not replay it; inspect editor receipt and before/after buffers.", operation_id=operation_id, receipt=proof, prepared=json.loads(old["payload"]))

    def write(self, owner, request_id, generation, operation_id, target, proposal=None, purpose="apply", resolution_id=None, archive_guard=None):
        if not isinstance(operation_id, str) or not operation_id or len(operation_id) > 200:
            raise RuntimeError("invalid-operation-id", "Supply a stable unique operation_id (maximum 200 characters).")
        if purpose not in {"apply", "answer", "proposal", "archive", "cleanup"}:
            raise RuntimeError("invalid-purpose", "Use apply, answer or proposal for public writes.")
        if not isinstance(target, dict) or not all(isinstance(target.get(key), str) for key in ("path", "expected", "replacement")):
            raise RuntimeError("invalid-target", "Target requires absolute path and exact expected/replacement strings.")
        if not target["expected"] and not isinstance(target.get("base"), str):
            raise RuntimeError("append-needs-base", "Appending requires the full exact current buffer in target.base.")
        if proposal is not None and (not isinstance(proposal, dict) or not isinstance(proposal.get("path"), str) or not isinstance(proposal.get("expected"), str) or not proposal["expected"]):
            raise RuntimeError("invalid-proposal", "Selected proposal requires an absolute path and nonempty exact source revision.")
        public_payload = dict(target=target, proposal=proposal, purpose=purpose)
        if purpose in {"archive", "cleanup"} and not resolution_id:
            raise RuntimeError("resolution-required", "Archive and cleanup belong to a saved internal resolution.")
        if purpose == "cleanup" and not archive_guard:
            raise RuntimeError("archive-proof-required", "Cleanup requires current exact archive evidence.")
        if archive_guard is not None:
            public_payload["archive_guard"] = archive_guard
        encoded = json.dumps(public_payload, sort_keys=True)
        own = self.owner(owner)
        self.admitted(own, target["path"])
        if proposal:
            self.admitted(own, proposal["path"])
        old = self.db.execute("SELECT * FROM receipts WHERE operation_id=?", (operation_id,)).fetchone()
        if old:
            if old["request_id"] != request_id or old["generation"] != generation or old["payload"] != encoded:
                raise RuntimeError("operation-id-reused", "This operation_id belongs to different content or authorization; never reuse it.")
            return {"receipt": self.receipt(owner, operation_id), "request": self.public(self.request(owner, request_id))}
        self.sync(owner)
        with self.transaction():
            row = self.request(owner, request_id, generation, writable=True, resolution_id=resolution_id if purpose in {"archive", "cleanup"} else None)
            own = self.owner(owner)
            self.db.execute("INSERT INTO receipts VALUES(?,?,?,?,?,?,?,NULL,?,?)", (operation_id, request_id, generation, owner, purpose, encoded, "prepared", utc(), utc()))
            request_guard = {"path": row["file"], "raw": row["raw"]}
            epoch, seq = own["epoch"], own["seq"]
        try:
            result = self.call_editor("write", owner=owner, epoch=epoch, after_seq=seq, operation_id=operation_id, request=request_guard, target=target,
                                      **({"proposal": proposal} if proposal else {}), **({"archive_guard": archive_guard} if archive_guard else {}))
            if result.get("status") != "committed":
                raise RuntimeError("ambiguous-editor-result", "Editor did not return a committed receipt.", receipt=result)
        except Exception as exc:
            try:
                result = self.receipt(owner, operation_id)
            except RuntimeError as proof_error:
                if proof_error.code == "operation-rejected":
                    raise proof_error from exc
                uncertain = getattr(exc, "uncertain", True)
                self.db.execute("UPDATE receipts SET status=?,result=?,updated_at=? WHERE operation_id=?", ("uncertain" if uncertain else "rejected", json.dumps({"error": str(exc)}), utc(), operation_id))
                if uncertain:
                    self.db.execute("UPDATE requests SET state='uncertain-write',reason=?,updated_at=? WHERE id=?", ("Operation " + operation_id + " may have committed; inspect receipts; do not replay.", utc(), request_id))
                raise RuntimeError("uncertain-write" if uncertain else getattr(exc, "code", "editor-refused"), str(exc), operation_id=operation_id) from exc
        with self.transaction():
            self.db.execute("UPDATE receipts SET status='committed',result=?,updated_at=? WHERE operation_id=?", (json.dumps(result), utc(), operation_id))
            receipt = self.db.execute("SELECT * FROM receipts WHERE operation_id=?", (operation_id,)).fetchone()
            # Timing evidence is durable even if post-commit visibility is lost.
            if purpose in {"apply", "answer", "proposal"}:
                self.timing(request_id, generation, "committed_at", receipt["updated_at"])
            if purpose in {"answer", "archive"}:
                self.timing(request_id, generation, "answered_at" if purpose == "answer" else "archived_at", receipt["updated_at"])
        if purpose == "answer":
            try:
                self.sync(owner)
            except Exception as exc:
                self.incident(owner, "post-commit:" + operation_id, {"code": "post-commit-refresh-failed", "message": str(exc), "request_id": request_id})
                # A read/notice failure cannot change committed proof to uncertain.
        return {"receipt": result, "request": self.public(self.request(owner, request_id))}

    def cleanup_plan(self, owner, row, supplied):
        if supplied is not None and not isinstance(supplied, list):
            raise RuntimeError("invalid-cleanup", "cleanup must be an array of exact {path,expected} spans.")
        receipts = [json.loads(item["payload"]) for item in self.db.execute(
            "SELECT payload FROM receipts WHERE request_id=? AND generation=? AND status='committed' AND purpose IN ('answer','proposal')",
            (row["id"], row["generation"]))]
        plan = list(supplied or [])
        def comments(text, path):
            pattern = r"<!--\s*CLAUDE.*?-->" if Path(path).suffix.lower() == ".md" else r"(?<!:)//\s*CLAUDE[^\n]*"
            return [match.group() for match in re.finditer(pattern, text, re.DOTALL | re.I)]
        for receipt in receipts:
            target = receipt["target"]
            document = self.db.execute("SELECT text,error FROM documents WHERE path=?", (target["path"],)).fetchone()
            for comment in comments(target["replacement"], target["path"]):
                if comment in target["expected"]:
                    continue
                if not document or document["error"] or document["text"].count(comment) != 1:
                    raise RuntimeError("cleanup-needed", "An owned assistant comment is missing, changed or ambiguous; preserve the request and inspect the committed answer before resolving.", path=target["path"])
                if not any(item.get("path") == target["path"] and comment in item.get("expected", "") for item in plan if isinstance(item, dict)):
                    plan.append({"path": target["path"], "expected": comment})
        unique = []
        for item in plan:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("expected"), str) or not item["expected"]:
                raise RuntimeError("invalid-cleanup", "Each cleanup requires an absolute path and nonempty exact expected span.")
            self.admitted(self.owner(owner), item["path"])
            expected = item["expected"]
            document = self.db.execute("SELECT text,error FROM documents WHERE path=?", (item["path"],)).fetchone()
            owned = any(receipt["target"]["path"] == item["path"] and expected in receipt["target"]["replacement"] and expected not in receipt["target"]["expected"] for receipt in receipts)
            assistant_only = comments(expected, item["path"]) == [expected.strip()]
            if not owned or (not assistant_only and item["path"] != markers.sidecar(row["file"])) or row["raw"] in expected or expected in row["raw"] or markers.parse(expected, item["path"]):
                raise RuntimeError("cleanup-needed", "Cleanup span is changed, user-owned, or not proven generated scaffolding. Preserve it and inspect the current proposal; do not replay the main edit.", path=item["path"])
            if not document or document["error"] or document["text"].count(expected) != 1:
                raise RuntimeError("cleanup-needed", "Cleanup span no longer uniquely matches the live buffer. Preserve user edits and inspect the proposal.", path=item["path"])
            normalized = {"path": item["path"], "expected": expected}
            if normalized not in unique:
                if any(other["path"] == item["path"] and (expected in other["expected"] or other["expected"] in expected) for other in unique):
                    raise RuntimeError("invalid-cleanup", "Cleanup spans overlap; provide one exact encompassing owned span.")
                unique.append(normalized)
        for receipt in receipts:
            target = receipt["target"]
            if receipt["purpose"] == "proposal" and target["path"] == markers.sidecar(row["file"]) and not comments(target["replacement"], target["path"]):
                if not any(item["path"] == target["path"] and target["replacement"].strip() in item["expected"] for item in unique):
                    raise RuntimeError("cleanup-needed", "Supply exact cleanup for the active sidecar proposal before resolving. Changed proposal wording is preserved, not guessed.", path=target["path"])
        return unique

    @staticmethod
    def archive_literal(text, role, protected=()):
        # Encode HTML/newlines and only characters needed to break exact anchors.
        chunks = [html.escape(char, quote=False) if char not in "\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029" else "&#" + str(ord(char)) + ";" for char in text]
        for anchor in protected:
            if not anchor:
                continue
            start = 0
            while True:
                start = text.find(anchor, start)
                if start < 0:
                    break
                if "".join(chunks[start:start + len(anchor)]) == anchor:
                    chunks[start] = "&#" + str(ord(text[start])) + ";"
                start += 1
        return "<pre data-coedit-" + role + ">" + "".join(chunks) + "</pre>"

    @staticmethod
    def archive_present(saved, document, cleanups, source):
        if not document or document.get("error") or not isinstance(document.get("text"), str):
            return False
        matches = [segment for section in markers.archive_sections(document["text"], saved["sidecar"])
                   for anchor, segment in markers.archive_entries(section) if anchor == saved["anchor"]]
        if len(matches) != 1:
            return False
        segment = matches[0]
        expected = [("original", saved["original_raw"]), ("decision", saved["record"])]
        for item in cleanups:
            expected.extend((("path", item["path"]), ("cleanup", item["expected"])))
        return markers.archive_evidence(segment) == (source, expected)

    def cleanup_archive_guard(self, owner, saved, cleanups):
        source = self.request(owner, saved["request_id"])["file"]
        self.sync(owner)
        document = self.db.execute("SELECT text,error FROM documents WHERE path=?", (saved["sidecar"],)).fetchone()
        if not self.archive_present(saved, dict(document) if document else None, cleanups, source):
            raise RuntimeError("cleanup-needed", "The saved archive is missing or changed; preserve active text and repair history explicitly. A past receipt does not authorize cleanup.")
        self.call_editor("ensure", owner=owner, path=saved["sidecar"], existing_only=True)
        self.sync(owner)
        document = self.db.execute("SELECT text,error FROM documents WHERE path=?", (saved["sidecar"],)).fetchone()
        if not self.archive_present(saved, dict(document) if document else None, cleanups, source):
            raise RuntimeError("cleanup-needed", "Archive changed while opening its editor; no cleanup is authorized.")
        return {"path": saved["sidecar"], "base": document["text"]}

    def resolve(self, owner, request_id, generation, operation_id, record, cleanup=None, reviewed=False):
        if not isinstance(record, str) or not record.strip() or not isinstance(operation_id, str) or not operation_id or len(operation_id) > 180:
            raise RuntimeError("invalid-resolution", "Resolution requires a nonempty human-readable record and stable operation_id (maximum 180 characters).")
        self.request(owner, request_id)
        saved = self.db.execute("SELECT * FROM resolutions WHERE operation_id=?", (operation_id,)).fetchone()
        if saved:
            if saved["request_id"] != request_id or saved["generation"] != generation or saved["record"] != record:
                raise RuntimeError("operation-id-reused", "Resolution operation_id belongs to different content or authorization.")
            if cleanup is not None:
                recorded = [{"path": item["path"], "expected": item["expected"]} for item in self.db.execute("SELECT path,expected FROM resolution_cleanups WHERE operation_id=? ORDER BY ordinal", (operation_id,))]
                if any(item not in recorded for item in cleanup):
                    raise RuntimeError("operation-id-reused", "Resolution cleanup content changed. Preserve the existing receipt and inspect the pending repair.")
            if saved["status"] == "resolved":
                return {"resolved": True, "request": self.public(self.request(owner, request_id)), "archive_anchor": saved["anchor"]}
        if reviewed is True:
            if not isinstance(generation, int) or isinstance(generation, bool) or not self.db.execute("SELECT 1 FROM submissions WHERE request_id=? AND generation=?", (request_id, generation)).fetchone():
                raise RuntimeError("unknown-generation", "Review must name an existing submitted generation.")
            with self.transaction():
                self.db.execute("INSERT OR IGNORE INTO resolution_reviews VALUES(?,?,?,?)", (request_id, generation, operation_id, utc()))
        if not saved:
            if self.review_required(request_id, generation, operation_id):
                raise RuntimeError("review-required", "Keep the answer visible until human review; use reviewed: true only after review.")
            self.sync(owner)
            with self.transaction():
                existing = self.db.execute("SELECT operation_id FROM resolutions WHERE request_id=? AND generation=? AND status!='resolved' LIMIT 1", (request_id, generation)).fetchone()
                if existing:
                    raise RuntimeError("resume-existing", "Resume the existing resolution; reconcile its receipts before continuing.", operation_id=existing["operation_id"])
                row = self.request(owner, request_id, generation, writable=True, resolution_id=operation_id)
                plan = self.cleanup_plan(owner, row, cleanup)
                anchor = "coedit-" + hashlib.sha256(operation_id.encode()).hexdigest()[:24]
                self.db.execute("INSERT INTO resolutions VALUES(?,?,?,?,?,?,?,?,?)", (operation_id, request_id, generation, record, row["raw"], markers.sidecar(row["file"]), anchor, utc(), "prepared"))
                for index, item in enumerate(plan):
                    self.db.execute("INSERT INTO resolution_cleanups VALUES(?,?,?,?)", (operation_id, index, item["path"], item["expected"]))
            saved = self.db.execute("SELECT * FROM resolutions WHERE operation_id=?", (operation_id,)).fetchone()
        cleanups = list(self.db.execute("SELECT * FROM resolution_cleanups WHERE operation_id=? ORDER BY ordinal", (operation_id,)))
        def stage_id(stage):
            base = operation_id + ":" + stage
            attempts = [row for row in self.db.execute("SELECT operation_id,status FROM receipts WHERE request_id=? ORDER BY created_at", (request_id,))
                        if row["operation_id"] == base or row["operation_id"].startswith(base + ":")]
            if not attempts:
                return base
            return base + ":" + str(len(attempts) + 1) if attempts[-1]["status"] == "rejected" else attempts[-1]["operation_id"]
        archive_id, cleanup_id = stage_id("archive"), stage_id("cleanup")
        try:
            archive_receipt = self.db.execute("SELECT * FROM receipts WHERE operation_id=?", (archive_id,)).fetchone()
            if archive_receipt:
                self.receipt(owner, archive_id)
            else:
                if self.review_required(request_id, generation, operation_id):
                    raise RuntimeError("review-required", "Human review is required before archive or cleanup.")
                self.sync(owner)
                self.request(owner, request_id, generation, writable=True, resolution_id=operation_id)
                ensured = self.call_editor("ensure", owner=owner, path=saved["sidecar"])
                text = ensured["text"]
                anchor_line = "^" + saved["anchor"]
                if anchor_line in markers.executable_view(text, saved["sidecar"], archives_only=True).splitlines():
                    # The archive itself is durable proof of a prior archive,
                    # never proof that a main-file edit or cleanup occurred.
                    proof = {"status": "committed", "operation_id": archive_id, "source": "archive-anchor", "path": saved["sidecar"]}
                    self.db.execute("INSERT INTO receipts VALUES(?,?,?,?,?,?,?,?,?,?)", (archive_id, request_id, generation, owner, "archive", "{}", "committed", json.dumps(proof), utc(), utc()))
                else:
                    protected = [saved["original_raw"], *(item["expected"] for item in cleanups)]
                    quoted = self.archive_literal(saved["original_raw"], "original", protected)
                    decision = self.archive_literal(record, "decision", protected)
                    archived_cleanup = "".join("\n\n**Archived scaffold**\n\n" + self.archive_literal(item["path"], "path", protected) + "\n\n" + self.archive_literal(item["expected"], "cleanup", protected) for item in cleanups)
                    source = self.request(owner, request_id)["file"]
                    offset, level, needs_heading = markers.history_insertion(text, saved["sidecar"])
                    heading = "#" * (level + 1) + " " if level < 6 else ""
                    entry = "\n\n" + ("## History\n\n" if needs_heading else "") + heading + saved["created_at"][:10] + " — Coedit resolution\n\n" + anchor_line + "\n\n**Coedit source:** " + json.dumps(source) + "\n\n**Original request**\n\n" + quoted + "\n\n**Answer / decision**\n\n" + decision + archived_cleanup + "\n\n"
                    resulting = text[:offset] + entry + text[offset:]
                    archive_view = markers.executable_view(resulting, saved["sidecar"], archives_only=True)
                    if any(anchor in entry or resulting.count(anchor) > text.count(anchor) for anchor in protected) or anchor_line not in archive_view.splitlines() or (source, saved["original_raw"]) not in markers.archive_records(resulting, saved["sidecar"]):
                        raise RuntimeError("unsafe-archive", "Archive structure would introduce a protected anchor or leave active History; preserve the note and repair its structure.")
                    suffix = text[offset:]
                    target = {"path": saved["sidecar"], "expected": suffix, "replacement": entry + suffix}
                    if not suffix:
                        target["base"] = text
                    self.write(owner, request_id, generation, archive_id, target, purpose="archive", resolution_id=operation_id)
            scaffold_ids = []
            for item in cleanups:
                child_id = stage_id("scaffold-" + str(item["ordinal"]))
                scaffold_ids.append(child_id)
                if self.db.execute("SELECT 1 FROM receipts WHERE operation_id=?", (child_id,)).fetchone():
                    self.receipt(owner, child_id)
                else:
                    self.write(owner, request_id, generation, child_id, {"path": item["path"], "expected": item["expected"], "replacement": ""}, purpose="cleanup", resolution_id=operation_id, archive_guard=self.cleanup_archive_guard(owner, saved, cleanups))
            cleanup = self.db.execute("SELECT * FROM receipts WHERE operation_id=?", (cleanup_id,)).fetchone()
            if cleanup:
                self.receipt(owner, cleanup_id)
            else:
                self.write(owner, request_id, generation, cleanup_id, {"path": self.request(owner, request_id)["file"], "expected": saved["original_raw"], "replacement": ""}, purpose="cleanup", resolution_id=operation_id, archive_guard=self.cleanup_archive_guard(owner, saved, cleanups))
            self.cleanup_archive_guard(owner, saved, cleanups)
            for item in [*cleanups, {"path": self.request(owner, request_id)["file"], "expected": saved["original_raw"]}]:
                document = self.db.execute("SELECT text,error FROM documents WHERE path=?", (item["path"],)).fetchone()
                if not document or document["error"] or item["expected"] in document["text"]:
                    raise RuntimeError("cleanup-needed", "Previously cleaned text was restored or cannot be verified; preserve it rather than replay cleanup.", path=item["path"])
            with self.transaction():
                self.db.execute("UPDATE resolutions SET status='resolved' WHERE operation_id=?", (operation_id,))
                self.db.execute("UPDATE requests SET state='resolved',reason=NULL,missing_since=NULL,updated_at=? WHERE id=? AND generation=? AND revision=?", (utc(), request_id, generation, markers.fingerprint(saved["original_raw"])))
                self.db.execute("INSERT OR IGNORE INTO archive_revisions VALUES(?,?)", (self.request(owner, request_id)["file"], markers.fingerprint(saved["original_raw"])))
            return {"resolved": True, "request": self.public(self.request(owner, request_id)), "archive_anchor": saved["anchor"], "archive_operation_id": archive_id, "cleanup_operation_id": cleanup_id, "scaffold_operation_ids": scaffold_ids}
        except Exception as exc:
            self.db.execute("UPDATE resolutions SET status='repair-needed' WHERE operation_id=?", (operation_id,))
            # Never turn invalidated/uncertain revisions back into authorization.
            self.db.execute("UPDATE requests SET state='repair-needed',reason=?,updated_at=? WHERE id=? AND state IN ('submitted','working','awaiting-user','repair-needed')", ("Archive/cleanup incomplete for " + operation_id + "; repair with the same resolution, never replay the main edit. " + str(exc), utc(), request_id))
            raise

    def dispatch(self, data):
        try:
            result = self._dispatch(data)
            if isinstance(data, dict) and data.get("op") in {"write", "resolve", "state", "submit"} and result.get("request"):
                self.recover_incidents(data.get("owner") or result.get("owner"), "operation:" + result["request"]["id"])
            return result
        except Exception as exc:
            if isinstance(data, dict) and isinstance(data.get("owner"), str) and isinstance(data.get("request_id"), str):
                try:
                    owner = self.owner(data["owner"])
                    row = self.request(data["owner"], data["request_id"])
                    item = {**error_json(exc)["error"], "request_id": row["id"], "path": row["file"], "generation": row["generation"], "revision": row["revision"]}
                    with self.transaction():
                        self.incident(owner["owner"], "operation:" + row["id"], item)
                        if getattr(exc, "uncertain", True) is False or getattr(exc, "code", "") in {"review-required", "not-authorized", "ambiguous-request", "cleanup-needed", "revision-invalidated"}:
                            self._notice_context = {"owner": owner["owner"], "epoch": owner["epoch"], "after_seq": owner["seq"]}
                            self.queue_notice(row["id"], str(exc), "warning")
                    self._notice_context = None
                    if getattr(exc, "uncertain", True) is False or getattr(exc, "code", "") in {"review-required", "not-authorized", "ambiguous-request", "cleanup-needed", "revision-invalidated"}:
                        self.flush_notices(owner["owner"])
                except Exception:
                    # Preserve the original operation failure even if feedback fails.
                    self._notice_context = None
            raise

    def _dispatch(self, data):
        if not isinstance(data, dict):
            raise RuntimeError("invalid-call", "Supply one JSON object.")
        op = data.get("op")
        owner = data.get("owner")
        required = {"read": ("request_id",), "reconcile": ("request_id",), "delivery": ("requests", "stage"), "state": ("request_id", "generation", "state"), "write": ("request_id", "generation", "operation_id", "target"), "resolve": ("request_id", "generation", "operation_id", "record")}
        missing = [key for key in required.get(op, ()) if key not in data]
        if missing:
            raise RuntimeError("invalid-call", "Missing required operation fields.", fields=missing)
        if op == "status":
            return self.status(owner)
        if op == "submit":
            return self.submit(owner)
        if not isinstance(owner, str):
            raise RuntimeError("owner-required", "This operation requires its live harness owner UUID.")
        if op == "stop":
            return self.stop(owner)
        if op in {"hold", "pause"}:
            if not isinstance(data.get("value"), bool):
                raise RuntimeError("invalid-value", "hold/pause value must be a JSON boolean.")
            self.owner(owner)
            self.db.execute("UPDATE owners SET " + op + "=? WHERE owner=?", (int(data["value"]), owner))
            return self.status(owner)
        if op == "read":
            return self.read_request(owner, data["request_id"])
        if op == "reconcile":
            return self.reconcile(owner, data["request_id"], data.get("generation"))
        if op == "delivery":
            return self.delivery(owner, data["requests"], data["stage"])
        if op == "state":
            if data.get("state") not in {"working", "awaiting-user"}:
                raise RuntimeError("invalid-state", "Progress state must be working or awaiting-user.")
            self.sync(owner)
            with self.transaction():
                row = self.request(owner, data["request_id"], data["generation"], writable=True)
                self.db.execute("UPDATE requests SET state=?,reason=?,updated_at=? WHERE id=?", (data["state"], data.get("reason"), utc(), row["id"]))
                if data["state"] == "working":
                    self.timing(row["id"], row["generation"], "picked_up_at")
            return {"request": self.public(self.request(owner, row["id"]))}
        if op == "write":
            if data.get("purpose", "apply") not in {"apply", "answer", "proposal"}:
                raise RuntimeError("invalid-purpose", "Public write purpose must be apply, answer or proposal.")
            return self.write(owner, data["request_id"], data["generation"], data["operation_id"], data["target"], data.get("proposal"), data.get("purpose", "apply"))
        if op == "resolve":
            return self.resolve(owner, data["request_id"], data["generation"], data["operation_id"], data["record"], data.get("cleanup"), data.get("reviewed", False))
        raise RuntimeError("unknown-operation", "Supported operations: status, read, hold, pause, submit, write, state, resolve, reconcile, delivery, stop.")


def error_json(exc):
    return {"ok": False, "error": {"code": getattr(exc, "code", "runtime-error"), "message": str(exc), **getattr(exc, "details", {})}}


def emit(data):
    print(json.dumps(data, ensure_ascii=False), flush=True)


def watch(runtime, args):
    running = True
    def stop_signal(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    parent = os.getppid()
    pipe_input = stat.S_ISFIFO(os.fstat(sys.stdin.fileno()).st_mode)
    attached = False
    last_revision, last_error, last_status = None, None, None
    try:
        status = runtime.attach(args.scope, args.owner, args.harness)
        attached = True
        emit({"type": "ready", **status})
        while running and os.getppid() == parent and alive(parent):
            if pipe_input and select.select([sys.stdin], [], [], 0)[0]:
                if not os.read(sys.stdin.fileno(), 4096):
                    break
            try:
                runtime.sync(args.owner)
                status = runtime.status(args.owner, synchronize=False)
                eligible, revision = status["eligible"], status["revision"]
                if eligible and revision != last_revision:
                    with runtime.transaction():
                        for row in eligible:
                            runtime.timing(row["id"], row["generation"], "hint_emitted_at")
                    eligible = [runtime.public(runtime.request(args.owner, row["id"])) for row in eligible]
                    emit({"type": "pending", "owner": args.owner, "revision": revision, "pending": eligible})
                last_revision, last_error = revision, None
            except Exception as exc:
                if getattr(exc, "code", None) == "owner-expired":
                    break
                diagnostic = error_json(exc)["error"]
                encoded = json.dumps(diagnostic, sort_keys=True)
                runtime.db.execute("UPDATE owners SET diagnostic=?,ready=0 WHERE owner=?", (str(exc), args.owner))
                runtime.incident(args.owner, "transport:watch", diagnostic)
                if encoded != last_error:
                    emit({"type": "diagnostic", "owner": args.owner, "error": diagnostic})
                    last_error = encoded
                status = runtime.status(args.owner, synchronize=False)
                last_revision = status["revision"]
            event = runtime.status_event(status)
            signature = runtime.status_signature(event, status)
            if signature != last_status:
                emit(event)
                last_status = signature
            time.sleep(0.25)
    finally:
        if attached:
            own = runtime.owner(args.owner, live=False)
            if own["pid"] == os.getpid():
                try:
                    runtime.stop(args.owner, explicit=not bool(own["intent"]))
                except Exception as exc:
                    emit({"type": "diagnostic", "owner": args.owner, "error": error_json(exc)["error"]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    watcher = sub.add_parser("watch")
    watcher.add_argument("--scope", required=True)
    watcher.add_argument("--owner", required=True)
    watcher.add_argument("--harness", choices=["omp", "claude", "codex"], required=True)
    sub.add_parser("call")
    submit = sub.add_parser("submit")
    submit.add_argument("--owner", required=True)
    runtime = None
    args = parser.parse_args()
    try:
        runtime = Runtime()
        if args.command == "watch":
            watch(runtime, args)
        else:
            result = runtime.dispatch(json.load(sys.stdin)) if args.command == "call" else runtime.submit(args.owner)
            emit({"ok": True, **result})
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        failure = error_json(exc)
        emit({"type": "diagnostic", "owner": args.owner, "error": failure["error"]} if args.command == "watch" else failure)
        return 1
    finally:
        if runtime:
            runtime.close()


if __name__ == "__main__":
    sys.exit(main())
