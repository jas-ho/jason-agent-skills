"""State-machine regressions for authorization loss and interrupted mutations.

The editor double models observable live buffers/events/receipts; actual Editor
transactions remain covered by Main's separate Obsidian integration smoke.
"""
from pathlib import Path
import sys
import html
import json
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import requests
from scripts.runtime import Runtime, RuntimeError, utc


class Refused(Exception):
    code = "test-refused"
    uncertain = False


class Editor:
    def __init__(self, path, text):
        self.documents = {path: text}
        self.events = []
        self.seq = 0
        self.epoch = "epoch-one"
        self.coverage_lost = True
        self.receipts = {}
        self.calls = []
        self.lose_reply = False
        self.hide_receipt = False
        self.fail_archive = False
        self.active = path
        self.cursor = len(text)
        self.actions = []
        self.notices = []
        self.snapshot_error = None
        self.fail_cleanup = False

    def change(self, path, text, **extra):
        self.seq += 1
        self.documents[path] = text
        self.events.append({"seq": self.seq, "path": path, "text": text, "kind": "change", "time": utc(), **extra})

    def __call__(self, action, payload):
        self.actions.append(action)
        if action == "notice":
            self.notices.append(payload)
            return {"shown": True, "key": payload["key"]}
        if action == "attach":
            return {"epoch": self.epoch, "owner": payload["owner"], "vault": str(Path(self.active).parent)}
        if action == "snapshot":
            if self.snapshot_error:
                raise OSError(self.snapshot_error)
            return {"epoch": self.epoch, "seq": self.seq, "events": [item.copy() for item in self.events if item["seq"] > payload.get("after_seq", 0)], "documents": [{"path": path, "text": text} for path, text in self.documents.items()], "coverage_lost": self.coverage_lost, "active": {"path": self.active, "cursor_offset": self.cursor}}
        if action == "ack":
            self.events = [item for item in self.events if item["seq"] > payload["through_seq"]]
            self.coverage_lost = False
            return {"acked": payload["through_seq"]}
        if action == "detach":
            return {"detached": True}
        if action == "receipt":
            return {"status": "unknown"} if self.hide_receipt else self.receipts.get(payload["operation_id"], {"status": "unknown"})
        if action == "ensure":
            if payload.get("existing_only") and payload["path"] not in self.documents:
                raise Refused("archive was removed")
            self.documents.setdefault(payload["path"], "")
            return {"text": self.documents[payload["path"]]}
        if action == "submit":
            text = self.documents[payload["path"]]
            if text.count(payload["raw"]) != 1:
                raise Refused("request drifted")
            replacement = text.replace(payload["raw"], payload["replacement"], 1)
            if replacement != text:
                self.change(payload["path"], replacement, operation_id="submit:fake")
            self.change(payload["path"], replacement, kind="submit", raw=payload["replacement"])
            return {"raw": payload["replacement"], "seq": self.seq}
        if action == "write":
            target = payload["target"]
            guard = payload.get("archive_guard")
            if guard and (self.documents.get(guard["path"]) != guard["base"] or any(
                    event["seq"] > payload["after_seq"] and event["path"] == guard["path"] for event in self.events)):
                raise Refused("archive guard changed")
            if self.fail_cleanup and target["replacement"] == "":
                raise Refused("cleanup editor unavailable")
            if self.fail_archive and target["path"].endswith(".notes.md"):
                raise Refused("sidecar editor unavailable")
            request = payload["request"]
            if self.documents[request["path"]].count(request["raw"]) != 1:
                raise Refused("request changed")
            for event in self.events:
                if event["seq"] > payload["after_seq"] and event["path"] == request["path"] and event["text"].count(request["raw"]) != 1:
                    raise Refused("request changed and reverted")
            if payload.get("proposal"):
                proposal = payload["proposal"]
                if self.documents[proposal["path"]].count(proposal["expected"]) != 1:
                    raise Refused("proposal changed")
            text = self.documents[target["path"]]
            if target["expected"]:
                if text.count(target["expected"]) != 1:
                    raise Refused("target changed or ambiguous")
                text = text.replace(target["expected"], target["replacement"], 1)
            else:
                if text != target["base"]:
                    raise Refused("append base changed")
                text += target["replacement"]
            self.calls.append(payload["operation_id"])
            self.change(target["path"], text, operation_id=payload["operation_id"])
            proof = {"operation_id": payload["operation_id"], "status": "committed"}
            self.receipts[payload["operation_id"]] = proof
            if self.lose_reply:
                raise OSError("transport vanished after editor commit")
            return proof
        raise AssertionError("Unsupported editor action: " + action)


class Authorization(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.path = str(self.root / "article.md")
        self.raw = "<!-- TODO(jason): Change alpha to beta ⏵ -->"
        self.text = "alpha\n" + self.raw
        Path(self.path).write_text(self.text)
        self.editor = Editor(self.path, self.text)
        self.runtime = Runtime(self.root / "state", self.editor)
        self.owner = str(uuid.uuid4())
        self.runtime.attach(self.path, self.owner, "omp")
        self.request = self.runtime.status(self.owner)["pending"][0]

    def tearDown(self):
        self.runtime.close()
        self.temp.cleanup()

    def current(self):
        return self.runtime.status(self.owner)["pending"][0]

    def apply(self, operation="apply-one"):
        return self.runtime.write(self.owner, self.request["id"], self.request["generation"], operation, {"path": self.path, "expected": "alpha\n", "replacement": "beta\n"})

    def test_body_change_and_revert_never_reauthorizes_visible_token(self):
        self.editor.change(self.path, self.text.replace("Change alpha", "Do not change alpha"))
        self.editor.change(self.path, self.text)
        current = self.current()
        self.assertEqual(current["id"], self.request["id"])
        self.assertEqual(current["state"], "needs-resubmission")
        with self.assertRaises(RuntimeError):
            self.apply()
        self.assertEqual(self.editor.documents[self.path], self.text)

    def test_gap_retains_unchanged_but_invalidates_changed_request(self):
        self.editor.coverage_lost = True
        self.assertEqual(self.current()["state"], "submitted")
        self.editor.documents[self.path] = self.text.replace("alpha to beta", "alpha to gamma")
        self.editor.coverage_lost = True
        current = self.current()
        self.assertEqual(current["id"], self.request["id"])
        self.assertEqual(current["state"], "needs-resubmission")

    def test_token_remove_reinsert_is_new_exact_generation(self):
        unsigned = self.text.replace("⏵", "")
        self.editor.change(self.path, unsigned)
        self.editor.change(self.path, self.text)
        current = self.current()
        self.assertEqual(current["generation"], self.request["generation"] + 1)
        self.assertEqual(current["state"], "submitted")
        self.assertNotEqual(current["submission_id"], self.request["submission_id"])

    def test_shortcut_signing_is_one_submission_and_can_resubmit_same_raw(self):
        self.editor.change(self.path, self.text.replace("⏵", ""))
        self.current()
        self.editor.cursor = self.editor.documents[self.path].index("-->")
        first = self.runtime.submit(self.owner)["request"]
        second = self.runtime.submit(self.owner)["request"]
        self.assertEqual(first["generation"], self.request["generation"] + 1)
        self.assertEqual(second["generation"], first["generation"] + 1)
        self.assertEqual(first["revision"], second["revision"])

    def test_continuously_present_duplicate_restores_original_not_diverged_copy(self):
        self.editor.change(self.path, self.text + "\n" + self.raw)
        blocked = self.current()
        self.assertEqual(blocked["state"], "submitted")
        self.assertTrue(blocked["blocked"])
        with self.assertRaises(RuntimeError):
            self.apply()
        copied = self.raw.replace("alpha to beta", "alpha to gamma")
        self.editor.change(self.path, self.text + "\n" + copied)
        pending = self.runtime.status(self.owner)["pending"]
        original = next(item for item in pending if item["id"] == self.request["id"])
        derived = next(item for item in pending if item["raw"] == copied)
        self.assertFalse(original["blocked"])
        self.assertEqual(original["generation"], self.request["generation"])
        self.assertEqual(derived["state"], "needs-resubmission")
        self.apply()
        self.assertTrue(self.editor.documents[self.path].startswith("beta\n"))

    def test_cut_paste_retains_identity_without_new_generation(self):
        self.editor.change(self.path, "alpha\n")
        self.current()
        self.editor.change(self.path, "alpha\n\n\n" + self.raw)
        current = self.current()
        self.assertEqual((current["id"], current["generation"], current["state"]), (self.request["id"], self.request["generation"], "submitted"))
        self.assertIsNone(current["missing_since"])

    def test_committed_transport_loss_recovers_receipt_without_replaying(self):
        self.editor.lose_reply = True
        result = self.apply()
        self.assertEqual(result["receipt"]["status"], "committed")
        self.apply()
        self.assertEqual(self.editor.calls, ["apply-one"])
        self.assertTrue(self.editor.documents[self.path].startswith("beta\n"))

    def test_unknown_receipt_blocks_new_operation_even_after_resubmit(self):
        self.editor.lose_reply = self.editor.hide_receipt = True
        with self.assertRaises(RuntimeError) as error:
            self.apply()
        self.assertEqual(error.exception.code, "uncertain-write")
        self.editor.cursor = self.editor.documents[self.path].index("-->")
        self.runtime.submit(self.owner)
        current = self.current()
        with self.assertRaises(RuntimeError):
            self.runtime.write(self.owner, current["id"], current["generation"], "new-id", {"path": self.path, "expected": "beta\n", "replacement": "gamma\n"})
        self.assertEqual(self.editor.calls, ["apply-one"])

    def test_archive_failure_repair_does_not_reapply_and_undo_does_not_requeue(self):
        self.apply()
        self.editor.fail_archive = True
        with self.assertRaises(RuntimeError):
            self.runtime.resolve(self.owner, self.request["id"], self.request["generation"], "finish", "Applied the requested change.")
        self.assertEqual(self.current()["state"], "repair-needed")
        self.editor.fail_archive = False
        self.runtime.resolve(self.owner, self.request["id"], self.request["generation"], "finish", "Applied the requested change.")
        self.assertEqual(self.editor.calls.count("apply-one"), 1)
        self.assertNotIn(self.raw, self.editor.documents[self.path])
        archive = self.editor.documents[requests.sidecar(self.path)]
        self.assertIn((self.path, self.raw), requests.archive_records(archive, requests.sidecar(self.path)))
        self.assertEqual(requests.parse(archive, requests.sidecar(self.path)), [])
        self.editor.change(self.path, self.text)
        self.assertEqual(self.runtime.status(self.owner)["pending"], [])
        self.assertEqual(self.editor.calls.count("apply-one"), 1)

    def test_resolved_undo_requires_deliberate_new_submission(self):
        self.runtime.resolve(self.owner, self.request["id"], self.request["generation"], "resolved", "No change needed.")
        self.editor.change(self.path, self.text)
        self.assertEqual(self.runtime.status(self.owner)["pending"], [])
        self.editor.change(self.path, self.text.replace("⏵", ""))
        self.editor.change(self.path, self.text)
        current = self.current()
        self.assertEqual(current["id"], self.request["id"])
        self.assertEqual(current["generation"], self.request["generation"] + 1)
        self.assertEqual(current["state"], "submitted")

    def test_explicit_restart_imports_unknown_but_not_changed_signed_requests(self):
        self.runtime.stop(self.owner, explicit=False)
        fresh = "<!-- TODO(jason): Newly submitted independent request ⏵ -->"
        self.editor.documents[self.path] = self.text.replace("alpha to beta", "alpha to gamma") + "\n" + fresh
        self.runtime.attach(self.path, self.owner, "omp")
        pending = self.runtime.status(self.owner)["pending"]
        self.assertEqual(next(item for item in pending if item["id"] == self.request["id"])["state"], "needs-resubmission")
        self.assertEqual(next(item for item in pending if item["raw"] == fresh)["state"], "submitted")

    def test_archive_does_not_suppress_same_wording_in_other_document(self):
        self.runtime.resolve(self.owner, self.request["id"], self.request["generation"], "resolved", "Done.")
        self.runtime.stop(self.owner)
        other = str(self.root / "other.md")
        Path(other).write_text(self.text)
        self.editor.documents[other] = self.text
        self.editor.active = other
        self.runtime.attach(other, self.owner, "omp")
        current = self.current()
        self.assertEqual(current["file"], other)
        self.assertEqual(current["state"], "submitted")
        self.assertNotEqual(current["id"], self.request["id"])

    def test_new_harness_scope_keeps_document_and_request_identity(self):
        self.runtime.stop(self.owner, explicit=False)
        new_owner = str(uuid.uuid4())
        self.runtime.attach(self.path, new_owner, "codex")
        pending = self.runtime.status(new_owner)["pending"][0]
        self.assertEqual((pending["id"], pending["generation"]), (self.request["id"], self.request["generation"]))

    def answer(self, operation="answer-one"):
        answer = "<!-- CLAUDE: The answer is beta. -->"
        result = self.runtime.write(self.owner, self.request["id"], self.request["generation"], operation,
                                    {"path": self.path, "expected": self.raw, "replacement": self.raw + "\n" + answer}, purpose="answer")
        return answer, result

    def test_answer_remains_visible_and_cannot_be_working_until_reviewed_resolution(self):
        answer, result = self.answer()
        self.assertEqual(result["request"]["state"], "answered")
        self.assertEqual(self.runtime.status(self.owner)["eligible_count"], 0)
        for reviewed in (False, "true", 1):
            with self.assertRaises(RuntimeError) as error:
                self.runtime.resolve(self.owner, self.request["id"], self.request["generation"], "review", "Answered.", reviewed=reviewed)
            self.assertEqual(error.exception.code, "review-required")
        with self.assertRaises(RuntimeError):
            self.runtime.dispatch({"op": "state", "owner": self.owner, "request_id": self.request["id"], "generation": self.request["generation"], "state": "working"})
        self.assertIn(answer, self.editor.documents[self.path])
        self.assertIn(self.raw, self.editor.documents[self.path])
        self.runtime.resolve(self.owner, self.request["id"], self.request["generation"], "review", "Answered.", reviewed=True)
        self.assertNotIn(answer, self.editor.documents[self.path])
        self.assertNotIn(self.raw, self.editor.documents[self.path])
        archive = self.editor.documents[requests.sidecar(self.path)]
        self.assertIn(answer, html.unescape(archive))

    def test_legacy_answer_and_saved_repair_cannot_bypass_review(self):
        answer, _ = self.answer()
        self.editor.fail_archive = True
        with self.assertRaises(RuntimeError):
            self.runtime.resolve(self.owner, self.request["id"], self.request["generation"], "repair-review", "Answered.", reviewed=True)
        self.runtime.db.execute("DELETE FROM resolution_reviews")
        self.runtime.db.execute("UPDATE requests SET state='working'")
        self.runtime.close()
        self.runtime = Runtime(self.root / "state", self.editor)
        self.assertEqual(self.current()["state"], "answered")
        self.editor.fail_archive = False
        self.editor.actions.clear()
        with self.assertRaises(RuntimeError) as error:
            self.runtime.resolve(self.owner, self.request["id"], self.request["generation"], "repair-review", "Answered.")
        self.assertEqual(error.exception.code, "review-required")
        self.assertNotIn("ensure", self.editor.actions)
        self.assertNotIn("write", self.editor.actions)
        self.assertIn(answer, self.editor.documents[self.path])

    def test_legacy_repair_with_committed_archive_still_preserves_unreviewed_answer(self):
        answer, _ = self.answer()
        self.editor.fail_cleanup = True
        with self.assertRaises(RuntimeError):
            self.runtime.resolve(self.owner, self.request["id"], self.request["generation"], "archived-answer", "Answered.", reviewed=True)
        self.runtime.db.execute("DELETE FROM resolution_reviews")
        self.runtime.db.execute("UPDATE requests SET state='working'")
        self.editor.fail_cleanup = False
        calls = list(self.editor.calls)
        with self.assertRaises(RuntimeError) as error:
            self.runtime.resolve(self.owner, self.request["id"], self.request["generation"], "archived-answer", "Answered.")
        self.assertEqual(error.exception.code, "review-required")
        self.assertEqual(self.editor.calls, calls)
        self.assertIn(answer, self.editor.documents[self.path])
        self.assertIn(self.raw, self.editor.documents[self.path])

    def test_reconcile_recognizes_prepared_archive_from_readable_history_without_cleanup(self):
        self.apply()
        self.editor.fail_cleanup = True
        with self.assertRaises(RuntimeError):
            self.runtime.resolve(self.owner, self.request["id"], self.request["generation"], "archive-proof", "Applied.")
        self.runtime.db.execute("UPDATE receipts SET status='uncertain',result=NULL WHERE operation_id='archive-proof:archive'")
        self.editor.hide_receipt = True
        self.editor.change(self.path, self.editor.documents[self.path].replace("alpha to beta", "alpha to gamma"))
        self.editor.actions.clear()
        result = self.runtime.reconcile(self.owner, self.request["id"])
        self.assertEqual(result["recovery"]["archive"]["status"], "committed")
        self.assertEqual(result["request"]["state"], "needs-resubmission")
        self.assertTrue(result["resolutions"][0]["archive_present"])
        self.assertTrue(set(self.editor.actions) <= {"snapshot", "receipt"})
        self.assertEqual(self.editor.calls.count("archive-proof:archive"), 1)

    def test_answer_commit_does_not_relabel_changed_generation(self):
        def concurrent_editor(action, payload):
            result = self.editor(action, payload)
            if action == "write":
                changed = self.editor.documents[self.path].replace(self.raw, self.raw.replace("alpha to beta", "alpha to gamma"))
                self.editor.change(self.path, changed)
            return result
        self.runtime.editor = concurrent_editor
        _, result = self.answer()
        self.assertEqual(result["receipt"]["status"], "committed")
        self.assertEqual(result["request"]["state"], "needs-resubmission")
        self.assertNotEqual(result["request"]["revision"], self.request["revision"])
        self.runtime.editor = self.editor
        self.editor.cursor = self.editor.documents[self.path].index("-->")
        current = self.runtime.submit(self.owner)["request"]
        reconciled = self.runtime.reconcile(self.owner, self.request["id"], self.request["generation"])
        self.assertEqual(reconciled["recovery"]["answer"]["status"], "committed")
        self.assertEqual(reconciled["request"]["generation"], current["generation"])
        self.assertEqual(reconciled["request"]["state"], "submitted")

    def test_reconcile_returns_old_proof_without_write_authority_or_editor_mutation(self):
        self.editor.lose_reply = self.editor.hide_receipt = True
        with self.assertRaises(RuntimeError):
            self.answer()
        self.editor.change(self.path, self.editor.documents[self.path].replace("alpha to beta", "alpha to gamma"))
        self.editor.hide_receipt = False
        self.runtime.db.execute("UPDATE owners SET hold=1")
        self.editor.actions.clear()
        result = self.runtime.reconcile(self.owner, self.request["id"])
        self.assertEqual(result["recovery"]["answer"]["status"], "committed")
        self.assertEqual(result["request"]["state"], "needs-resubmission")
        self.assertTrue(set(self.editor.actions) <= {"snapshot", "receipt"})
        self.assertEqual(self.editor.calls, ["answer-one"])

    def test_duplicate_gap_or_disappearance_loses_continuity(self):
        self.editor.change(self.path, self.text + "\n" + self.raw)
        self.current()
        self.editor.coverage_lost = True
        self.editor.documents[self.path] = self.text
        self.assertEqual(self.current()["state"], "needs-resubmission")
        self.editor.cursor = self.editor.documents[self.path].index("-->")
        self.runtime.submit(self.owner)
        self.editor.change(self.path, self.text + "\n" + self.raw)
        self.current()
        self.editor.change(self.path, "alpha\n")
        self.editor.change(self.path, self.text)
        self.assertEqual(self.current()["state"], "needs-resubmission")

    def test_snapshot_error_invalidates_duplicate_proof_even_after_exact_recovery(self):
        self.editor.change(self.path, self.text + "\n" + self.raw)
        self.current()
        self.editor.snapshot_error = "snapshot transport unavailable"
        with self.assertRaises(OSError):
            self.current()
        self.editor.snapshot_error = None
        self.editor.change(self.path, self.text)
        self.assertEqual(self.current()["state"], "needs-resubmission")

    def test_diverged_copy_old_glyph_is_not_imported_after_restart(self):
        self.editor.change(self.path, self.text + "\n" + self.raw)
        self.current()
        self.runtime.stop(self.owner, explicit=False)
        copied = self.raw.replace("alpha to beta", "alpha to gamma")
        self.editor.documents[self.path] = self.text + "\n" + copied
        self.runtime.attach(self.path, self.owner, "omp")
        pending = self.runtime.status(self.owner)["pending"]
        self.assertEqual(next(item for item in pending if item["raw"] == copied)["state"], "needs-resubmission")
        self.assertEqual(next(item for item in pending if item["raw"] == self.raw)["state"], "needs-resubmission")

    def test_archive_reuses_lexical_history_and_breaks_all_literal_anchors(self):
        sidecar = requests.sidecar(self.path)
        prefix = "## History\n\nPrevious human record.\n\n"
        suffix = "## Active\n\nHuman content stays active.\n"
        self.editor.documents[sidecar] = prefix + suffix
        record = "Literal request: " + self.raw + "\n## Active\nStill quoted: " + self.raw
        self.runtime.resolve(self.owner, self.request["id"], self.request["generation"], "safe-archive", record)
        archive = self.editor.documents[sidecar]
        self.assertTrue(archive.startswith(prefix))
        self.assertTrue(archive.endswith(suffix))
        self.assertEqual(archive.count("## History"), 1)
        self.assertNotIn(self.raw, archive)
        self.assertIn(record, html.unescape(archive))
        self.assertIn((self.path, self.raw), requests.archive_records(archive, sidecar))
        self.assertEqual(requests.parse(archive, sidecar), [])
        phrase = "literal cleanup phrase"
        literal = self.runtime.archive_literal("before " + phrase + "\nafter " + phrase, "decision", [phrase])
        self.assertNotIn(phrase, literal)
        self.assertEqual(html.unescape(literal.removeprefix("<pre data-coedit-decision>").removesuffix("</pre>")), "before " + phrase + "\nafter " + phrase)

    def test_structural_archive_anchor_collision_refuses_without_cleanup(self):
        sidecar = requests.sidecar(self.path)
        self.editor.documents[sidecar] = "literal cleanup phrase"
        self.runtime.write(self.owner, self.request["id"], self.request["generation"], "proposal",
                           {"path": sidecar, "expected": "literal cleanup phrase", "replacement": "Original request"}, purpose="proposal")
        with self.assertRaises(RuntimeError) as error:
            self.runtime.resolve(self.owner, self.request["id"], self.request["generation"], "unsafe", "Done.",
                                 cleanup=[{"path": sidecar, "expected": "Original request"}])
        self.assertEqual(error.exception.code, "unsafe-archive")
        self.assertIn(self.raw, self.editor.documents[self.path])
        self.assertEqual(self.editor.documents[sidecar], "Original request")

    def test_delivery_is_exact_non_waking_and_status_clears_on_answer(self):
        before = self.runtime.status(self.owner)
        identity = {key: self.request[key] for key in ("id", "generation", "revision")}
        self.editor.actions.clear()
        self.runtime.delivery(self.owner, [identity], "handoff")
        self.assertEqual(self.editor.actions, [])
        after = self.runtime.status(self.owner, synchronize=False)
        self.assertEqual(before["revision"], after["revision"])
        self.assertEqual(self.runtime.status_signature(self.runtime.status_event(before), before), self.runtime.status_signature(self.runtime.status_event(after), after))
        stamp = after["pending"][0]["timings"]["handoff_at"]
        self.runtime.delivery(self.owner, [identity], "handoff")
        self.assertEqual(self.current()["timings"]["handoff_at"], stamp)
        self.editor.cursor = self.editor.documents[self.path].index("-->")
        current = self.runtime.submit(self.owner)["request"]
        result = self.runtime.delivery(self.owner, [identity], "queue_confirmed")
        self.assertEqual(result["stale"], [identity])
        self.assertIsNone(self.current()["timings"]["queue_confirmed_at"])
        self.request = current
        self.answer()
        status = self.runtime.status(self.owner)
        event = self.runtime.status_event(status)
        self.assertEqual((event["type"], event["eligible_count"], event["answered_count"]), ("status", 0, 1))

    def test_recovered_diagnostic_preserves_evidence_without_clock_wakes(self):
        self.editor.snapshot_error = "temporary snapshot loss"
        with self.assertRaises(OSError):
            self.current()
        failed = self.runtime.status(self.owner, synchronize=False)
        self.assertEqual(failed["diagnostics"]["current"][0]["message"], "temporary snapshot loss")
        self.assertFalse(failed["ready"])
        self.editor.snapshot_error = None
        recovered = self.runtime.status(self.owner)
        self.assertEqual(recovered["diagnostics"]["current"], [])
        self.assertIsNotNone(recovered["diagnostics"]["history"][0]["recovered_at"])
        self.assertTrue(recovered["ready"])
        self.assertNotEqual(self.runtime.status_signature(self.runtime.status_event(failed), failed), self.runtime.status_signature(self.runtime.status_event(recovered), recovered))

    def test_submission_notice_follows_durable_commit_and_initial_import_is_silent(self):
        self.assertEqual(self.editor.notices, [])
        committed = []
        def notice_observer(action, payload):
            if action == "notice" and payload["level"] == "info":
                import sqlite3
                with sqlite3.connect(self.root / "state" / "ledger.sqlite3") as ledger:
                    row = ledger.execute("SELECT revision FROM submissions WHERE request_id=? ORDER BY generation DESC LIMIT 1", (self.request["id"],)).fetchone()
                    committed.append(row[0] if row else None)
            return self.editor(action, payload)
        self.runtime.editor = notice_observer
        self.editor.change(self.path, self.text.replace("⏵", ""))
        self.editor.change(self.path, self.text)
        current = self.current()
        notices = [item for item in self.editor.notices if item["level"] == "info"]
        self.assertEqual(committed, [current["revision"]])
        self.assertEqual([item["revision"] for item in notices], committed)

    def test_one_invalidation_notice_per_transition(self):
        self.editor.change(self.path, self.text.replace("alpha to beta", "alpha to gamma"))
        self.current()
        warnings = [item for item in self.editor.notices if item["level"] == "warning"]
        self.assertEqual(len(warnings), 1)
        self.current()
        self.assertEqual([item for item in self.editor.notices if item["level"] == "warning"], warnings)

    def test_reviewed_answer_repair_guidance_never_reopens_write_authority(self):
        answer, _ = self.answer()
        self.editor.fail_cleanup = True
        with self.assertRaises(RuntimeError):
            self.runtime.resolve(self.owner, self.request["id"], 1, "review-repair", "Reviewed.", reviewed=True)
        current = self.current()
        self.assertEqual(current["state"], "answered")
        self.assertEqual(current["next_action"]["code"], "repair")
        self.assertIn(answer, self.editor.documents[self.path])
        with self.assertRaises(RuntimeError):
            self.runtime.dispatch({"op": "state", "owner": self.owner, "request_id": self.request["id"], "generation": 1, "state": "working"})
        self.editor.fail_cleanup = False
        self.runtime.resolve(self.owner, self.request["id"], 1, "review-repair", "Reviewed.")
        self.assertEqual(self.editor.calls.count("review-repair:archive"), 1)

    def test_new_resolution_id_cannot_repeat_partially_committed_archive(self):
        self.answer()
        self.editor.fail_cleanup = True
        with self.assertRaises(RuntimeError):
            self.runtime.resolve(self.owner, self.request["id"], 1, "first-resolution", "Reviewed.", reviewed=True)
        before = dict(self.editor.documents)
        calls = list(self.editor.calls)
        with self.assertRaises(RuntimeError) as error:
            self.runtime.resolve(self.owner, self.request["id"], 1, "second-resolution", "Reviewed.", reviewed=True)
        self.assertEqual(error.exception.code, "resume-existing")
        self.assertEqual(self.editor.documents, before)
        self.assertEqual(self.editor.calls, calls)

    def test_cancelled_request_retires_obsolete_refusal(self):
        payload = {"op": "write", "owner": self.owner, "request_id": self.request["id"],
                   "generation": 0, "operation_id": "refused",
                   "target": {"path": self.path, "expected": "alpha\n", "replacement": "beta\n"}}
        with self.assertRaises(RuntimeError) as error:
            self.runtime.dispatch(payload)
        with patch("scripts.runtime.CUT_GRACE_SECONDS", 0):
            self.editor.change(self.path, "alpha\n")
            status = self.runtime.status(self.owner)
        self.assertEqual(status["pending"], [])
        self.assertEqual(status["diagnostics"]["current"], [])
        self.assertTrue(any(item["code"] == error.exception.code for item in status["diagnostics"]["history"]))

    def test_cancellation_keeps_unreconciled_mutation_incident_current(self):
        self.editor.lose_reply = self.editor.hide_receipt = True
        with self.assertRaises(RuntimeError):
            self.runtime.dispatch({"op": "write", "owner": self.owner, "request_id": self.request["id"],
                                   "generation": 1, "operation_id": "uncertain",
                                   "target": {"path": self.path, "expected": "alpha\n", "replacement": "beta\n"}})
        with patch("scripts.runtime.CUT_GRACE_SECONDS", 0):
            self.editor.change(self.path, "beta\n")
            status = self.runtime.status(self.owner)
        self.assertTrue(any(item["code"] == "uncertain-write" for item in status["diagnostics"]["current"]))

    def test_pasted_signed_carrier_needs_witnessed_unsigned_transition(self):
        unsigned = "<!-- TODO(jason): A genuinely new request -->"
        signed = unsigned.replace(" -->", " ⏵ -->")
        self.editor.change(self.path, self.text + "\n" + signed)
        rows = self.runtime.status(self.owner)["pending"]
        added = next(row for row in rows if row["raw"] == signed)
        self.assertEqual((added["generation"], added["state"]), (0, "needs-resubmission"))
        self.editor.change(self.path, self.text + "\n" + unsigned)
        self.editor.change(self.path, self.text + "\n" + signed)
        added = next(row for row in self.runtime.status(self.owner)["pending"] if row["id"] == added["id"])
        self.assertEqual((added["generation"], added["state"]), (1, "submitted"))

    def test_live_new_document_is_not_an_initial_import_window(self):
        self.runtime.stop(self.owner)
        self.runtime.attach(str(self.root), self.owner, "omp")
        other = str(self.root / "introduced.md")
        Path(other).write_text(self.raw)
        self.editor.change(other, self.raw)
        introduced = next(row for row in self.runtime.status(self.owner)["pending"] if row["file"] == other)
        self.assertEqual((introduced["generation"], introduced["state"]), (0, "needs-resubmission"))

    def test_repair_rejects_public_write_and_state_reset(self):
        self.apply()
        self.editor.fail_archive = True
        with self.assertRaises(RuntimeError):
            self.runtime.resolve(self.owner, self.request["id"], 1, "repair-only", "Applied.")
        before = dict(self.editor.documents)
        with self.assertRaises(RuntimeError):
            self.runtime.write(self.owner, self.request["id"], 1, "extra-edit",
                               {"path": self.path, "expected": "beta\n", "replacement": "gamma\n"})
        with self.assertRaises(RuntimeError):
            self.runtime.dispatch({"op": "state", "owner": self.owner, "request_id": self.request["id"], "generation": 1, "state": "working"})
        self.assertEqual(self.editor.documents, before)

    def test_removed_committed_archive_never_authorizes_cleanup(self):
        self.answer()
        self.editor.fail_cleanup = True
        with self.assertRaises(RuntimeError):
            self.runtime.resolve(self.owner, self.request["id"], 1, "archive-undo", "Reviewed.", reviewed=True)
        self.editor.fail_cleanup = False
        self.editor.change(requests.sidecar(self.path), "")
        before = dict(self.editor.documents)
        with self.assertRaises(RuntimeError) as error:
            self.runtime.resolve(self.owner, self.request["id"], 1, "archive-undo", "Reviewed.")
        self.assertEqual(error.exception.code, "cleanup-needed")
        self.assertEqual(self.editor.documents, before)
        self.assertIn(self.raw, self.editor.documents[self.path])

    def test_reconcile_leaves_pending_submission_events_and_cursor_untouched(self):
        before = self.runtime.owner(self.owner)["seq"]
        self.editor.change(self.path, self.text.replace("⏵", ""))
        self.editor.change(self.path, self.text)
        self.runtime.reconcile(self.owner, self.request["id"])
        row = self.runtime.request(self.owner, self.request["id"])
        self.assertEqual(row["generation"], 1)
        self.assertEqual(self.runtime.owner(self.owner)["seq"], before)
        self.assertEqual(self.current()["generation"], 2)

    def test_notice_retry_recovers_only_its_own_delivery(self):
        def intermittent(action, payload):
            if action == "notice" and payload["level"] == "info" and not failed:
                failed.append(payload["key"])
                raise OSError("notice delivery unavailable")
            return self.editor(action, payload)
        failed = []
        self.runtime.editor = intermittent
        self.editor.change(self.path, self.text.replace("⏵", ""))
        self.editor.change(self.path, self.text)
        self.current()
        self.assertTrue(failed)
        self.runtime.incident(self.owner, "notice:independent", {"code": "notice-failed", "message": "Other undelivered confirmation."})
        with patch("scripts.runtime.time.time", return_value=time.time() + 2):
            self.current()
        status = self.runtime.status(self.owner, synchronize=False)
        self.assertEqual([item["key"] for item in self.editor.notices if item["level"] == "info"], failed)
        self.assertTrue(any(item["message"] == "Other undelivered confirmation." for item in status["diagnostics"]["current"]))
        self.assertTrue(any(item.get("details", {}).get("key") == failed[0] for item in status["diagnostics"]["history"]))

    def test_failed_notice_retries_are_bounded(self):
        attempts = []
        def unavailable(action, payload):
            if action == "notice" and payload["level"] == "info":
                attempts.append(payload["key"])
                raise OSError("notice service unavailable")
            return self.editor(action, payload)
        self.runtime.editor = unavailable
        self.editor.change(self.path, self.text.replace("⏵", ""))
        self.editor.change(self.path, self.text)
        started = time.time()
        for offset in (0, 3, 7, 15, 31):
            with patch("scripts.runtime.time.time", return_value=started + offset):
                self.current()
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len(set(attempts)), 1)

    def test_unrelated_witnessed_sign_survives_old_duplicate_history(self):
        self.editor.change(self.path, self.text + "\n" + self.raw)
        self.current()
        self.editor.change(self.path, self.text)
        self.current()
        unsigned = "<!-- TODO(jason): Unrelated later request -->"
        self.editor.change(self.path, self.text + "\n" + unsigned)
        self.runtime.status(self.owner)
        signed = unsigned.replace(" -->", " ⏵ -->")
        self.editor.change(self.path, self.text + "\n" + signed)
        fresh = next(row for row in self.runtime.status(self.owner)["pending"] if row["raw"] == signed)
        self.assertEqual((fresh["generation"], fresh["state"]), (1, "submitted"))

    def test_restored_cleaned_scaffold_is_not_replayed_or_resolved(self):
        self.answer()
        delivered = self.editor.documents[self.path]
        def refuse_final_cleanup(action, payload):
            if action == "write" and payload["target"]["expected"] == self.raw and payload["target"]["replacement"] == "":
                raise Refused("main cleanup temporarily unavailable")
            return self.editor(action, payload)
        self.runtime.editor = refuse_final_cleanup
        with self.assertRaises(RuntimeError):
            self.runtime.resolve(self.owner, self.request["id"], 1, "restored-scaffold", "Reviewed.", reviewed=True)
        self.runtime.editor = self.editor
        self.editor.change(self.path, delivered)
        with self.assertRaises(RuntimeError) as error:
            self.runtime.resolve(self.owner, self.request["id"], 1, "restored-scaffold", "Reviewed.")
        self.assertEqual(error.exception.code, "cleanup-needed")
        self.assertIn("<!-- CLAUDE: The answer is beta. -->", self.editor.documents[self.path])
        self.assertNotEqual(self.runtime.request(self.owner, self.request["id"])["state"], "resolved")

    def test_rejected_proof_overrides_lost_write_response(self):
        def reject_without_reply(action, payload):
            if action == "write":
                self.editor.receipts[payload["operation_id"]] = {"status": "rejected", "attempted": False, "operation_id": payload["operation_id"]}
                raise OSError("response lost after terminal guarded refusal")
            return self.editor(action, payload)
        self.runtime.editor = reject_without_reply
        with self.assertRaises(RuntimeError) as error:
            self.apply("known-rejection")
        self.assertEqual(error.exception.code, "operation-rejected")
        self.assertEqual(self.editor.documents[self.path], self.text)
        self.runtime.editor = self.editor
        self.apply("fresh-after-rejection")
        self.assertTrue(self.editor.documents[self.path].startswith("beta\n"))

    def test_readonly_rejected_reconciliation_defers_authority_to_normal_sync(self):
        def reject_without_reply(action, payload):
            if action == "write":
                self.editor.receipts[payload["operation_id"]] = {"status": "rejected", "attempted": False, "operation_id": payload["operation_id"]}
                raise OSError("response and initial receipt unavailable")
            return self.editor(action, payload)
        self.runtime.editor = reject_without_reply
        self.editor.hide_receipt = True
        with self.assertRaises(RuntimeError):
            self.apply("late-rejection-proof")
        self.runtime.editor = self.editor
        self.editor.hide_receipt = False
        reconciled = self.runtime.reconcile(self.owner, self.request["id"])
        self.assertEqual(reconciled["request"]["state"], "uncertain-write")
        self.assertIn(self.current()["state"], {"submitted", "working"})
        self.apply("fresh-after-proof-reconciliation")
        self.assertTrue(self.editor.documents[self.path].startswith("beta\n"))

    def test_edited_text_keeps_signed_timing_provenance_distinct(self):
        signed = self.current()
        changed = self.text.replace("alpha to beta", "alpha to gamma")
        self.editor.change(self.path, changed)
        dirty = self.current()
        self.assertNotEqual(dirty["revision"], dirty["submitted_revision"])
        self.assertEqual(dirty["submitted_revision"], signed["revision"])
        self.assertEqual(dirty["timings"], signed["timings"])
        self.editor.change(self.path, changed.replace("⏵", ""))
        self.editor.change(self.path, changed)
        fresh = self.current()
        self.assertEqual((fresh["generation"], fresh["state"]), (2, "submitted"))
        self.assertEqual(fresh["submitted_revision"], fresh["revision"])


    def test_deleted_sole_answer_blocks_first_resolution_without_cleanup(self):
        self.answer()
        self.editor.change(self.path, self.editor.documents[self.path].replace("<!-- CLAUDE: The answer is beta. -->", ""))
        before = dict(self.editor.documents)
        with self.assertRaises(RuntimeError) as error:
            self.runtime.resolve(self.owner, self.request["id"], 1, "deleted-answer", "Reviewed.", reviewed=True)
        self.assertEqual(error.exception.code, "cleanup-needed")
        self.assertEqual(self.current()["state"], "answered")
        self.assertEqual(self.editor.documents, before)
        self.assertEqual(self.runtime.recovery(self.request["id"], 1)["archive"]["status"], "none")

    def partially_archived_answer(self):
        sidecar = requests.sidecar(self.path)
        source_line = "**Coedit source:** " + json.dumps(self.path)
        self.editor.change(sidecar, "## History\n\n### Earlier entry\n\n^coedit-0000\n\n" + source_line + "\n\nEarlier decision.\n")
        self.answer()
        self.editor.fail_cleanup = True
        with self.assertRaises(RuntimeError):
            self.runtime.resolve(self.owner, self.request["id"], 1, "entry-integrity", "Reviewed.", reviewed=True)
        self.editor.fail_cleanup = False
        detail = self.runtime.dispatch({"op": "read", "owner": self.owner, "request_id": self.request["id"]})
        saved = next(item for item in detail["resolutions"] if item["operation_id"] == "entry-integrity")
        return sidecar, self.editor.documents[sidecar], source_line, "^" + saved["anchor"]

    def test_archive_cannot_borrow_earlier_source_metadata(self):
        sidecar, complete, source_line, anchor = self.partially_archived_answer()
        self.editor.change(sidecar, complete.replace(anchor + "\n\n" + source_line, anchor, 1))
        before = dict(self.editor.documents)
        with self.assertRaises(RuntimeError) as error:
            self.runtime.resolve(self.owner, self.request["id"], 1, "entry-integrity", "Reviewed.")
        self.assertEqual(error.exception.code, "cleanup-needed")
        self.assertEqual(self.editor.documents, before)

    def test_archive_source_must_follow_its_own_anchor(self):
        sidecar, complete, source_line, anchor = self.partially_archived_answer()
        self.editor.change(sidecar, complete.replace(anchor + "\n\n" + source_line, source_line + "\n\n" + anchor, 1))
        before = dict(self.editor.documents)
        with self.assertRaises(RuntimeError) as error:
            self.runtime.resolve(self.owner, self.request["id"], 1, "entry-integrity", "Reviewed.")
        self.assertEqual(error.exception.code, "cleanup-needed")
        self.assertEqual(self.editor.documents, before)

    def test_archive_extra_protocol_field_does_not_authorize_cleanup(self):
        sidecar, complete, _source_line, _anchor = self.partially_archived_answer()
        self.editor.change(sidecar, complete + "\n<pre data-coedit-original>Unrecorded original</pre>\n")
        before = dict(self.editor.documents)
        with self.assertRaises(RuntimeError) as error:
            self.runtime.resolve(self.owner, self.request["id"], 1, "entry-integrity", "Reviewed.")
        self.assertEqual(error.exception.code, "cleanup-needed")
        self.assertEqual(self.editor.documents, before)

    def test_sidecar_origin_request_retains_its_own_archive_source(self):
        sidecar = requests.sidecar(self.path)
        unsigned = "<!-- TODO(jason): Change side alpha to side beta -->"
        self.editor.change(sidecar, "side alpha\n" + unsigned)
        self.runtime.status(self.owner)
        raw = unsigned.replace(" -->", " ⏵ -->")
        self.editor.change(sidecar, "side alpha\n" + raw)
        row = next(item for item in self.runtime.status(self.owner)["pending"] if item["file"] == sidecar)
        self.runtime.write(self.owner, row["id"], row["generation"], "sidecar-edit",
                           {"path": sidecar, "expected": "side alpha\n", "replacement": "side beta\n"})
        resolved = self.runtime.resolve(self.owner, row["id"], row["generation"], "sidecar-resolution", "Applied in sidecar.")
        self.assertTrue(resolved["resolved"])
        self.assertIn((sidecar, raw), requests.archive_records(self.editor.documents[sidecar], sidecar))

    def test_malformed_and_legacy_history_do_not_suppress_foreign_requests(self):
        self.runtime.stop(self.owner, explicit=False)
        peer = str(self.root / "peer.md")
        fresh = "<!-- QUESTION(jason): Is this new argument sound? ⏵ -->"
        legacy = "<!-- TODO(jason): Add a citation for the stated date. ⏵ -->"
        literal = "<!-- QUESTION(jason): A literal archived for the peer ⏵ -->"
        sidecar = requests.sidecar(self.path)
        history = "\n".join([
            "## History", "^coedit-aaaa", "**Coedit source:** " + json.dumps(peer),
            "<pre data-coedit-original>" + literal + "</pre>",
            self.runtime.archive_literal("Earlier reviewed decision.", "decision"),
            "^coedit-bbbb",
            self.runtime.archive_literal(fresh, "original"),
            self.runtime.archive_literal("This entry lost its own source.", "decision"),
            "## Applied 2023-01-01", legacy,
        ])
        self.editor.change(sidecar, history)
        self.editor.change(self.path, self.text + "\n" + literal)
        self.editor.change(peer, fresh + "\n" + legacy)
        self.runtime.attach(str(self.root), self.owner, "omp")
        pending = self.runtime.status(self.owner)["pending"]
        admitted = {row["raw"]: row["state"] for row in pending if row["file"] == peer}
        self.assertEqual(admitted, {fresh: "submitted", legacy: "submitted"})
        self.assertEqual(next(row["state"] for row in pending if row["file"] == self.path and row["raw"] == literal), "submitted")
        records = requests.archive_records(history, sidecar)
        self.assertIn((self.path, legacy), records)
        self.assertNotIn((peer, fresh), records)
        self.assertNotIn((peer, legacy), records)
        self.assertIn((peer, literal), records)
        self.assertNotIn((self.path, literal), records)

    def test_archive_anchor_cannot_borrow_from_another_archive_section(self):
        self.runtime.stop(self.owner, explicit=False)
        raw = "<!-- QUESTION(jason): Is this a new independently signed request? ⏵ -->"
        sidecar = requests.sidecar(self.path)
        history = "\n".join([
            "## History", "^coedit-aaaa", "## Active", "Ordinary active material.",
            "## Applied 2023-01-01", "**Coedit source:** " + json.dumps(self.path),
            self.runtime.archive_literal(raw, "original"),
            self.runtime.archive_literal("A record without an anchor in this section.", "decision"),
        ])
        self.editor.change(sidecar, history)
        self.editor.change(self.path, self.text + "\n" + raw)
        self.runtime.attach(self.path, self.owner, "omp")
        admitted = {row["raw"]: row["state"] for row in self.runtime.status(self.owner)["pending"]}
        self.assertEqual(admitted.get(raw), "submitted")
        self.assertNotIn((self.path, raw), requests.archive_records(history, sidecar))

    def test_archive_body_moved_across_section_boundary_cannot_authorize_cleanup(self):
        sidecar, complete, _source_line, anchor = self.partially_archived_answer()
        self.editor.change(sidecar, complete.replace(anchor, anchor + "\n\n## Active\n\nHuman material.\n\n## History", 1))
        before = dict(self.editor.documents)
        with self.assertRaises(RuntimeError) as error:
            self.runtime.resolve(self.owner, self.request["id"], 1, "entry-integrity", "Reviewed.")
        self.assertEqual(error.exception.code, "cleanup-needed")
        self.assertEqual(self.editor.documents, before)


class ExecutableRegions(unittest.TestCase):
    def test_markdown_examples_archives_and_assistant_comments_are_not_requests(self):
        raw = "<!-- TODO(jason): example ⏵ -->"
        text = "---\nexample: " + raw + "\n---\n```md\n" + raw + "\n```\n> " + raw + "\n\n`" + raw + "`\n**Anchor:** " + raw + "\n<!-- CLAUDE: " + raw + " -->\n## Applied 2026-09-01 — pass 2\n" + raw + "\n### Child\n" + raw + "\n## 2026-09-12\n<!-- TODO(jason): active ⏵ -->"
        result = requests.parse(text, "/tmp/example.md")
        self.assertEqual([item.body.strip() for item in result], ["active ⏵"])

    def test_typst_strings_raw_blocks_and_history_excluded(self):
        text = '#let value = "// TODO(jason): string ⏵"\n```\n// TODO(jason): raw ⏵\n```\n= History\n// TODO(jason): archive ⏵\n= Active\n// TODO(jason): live ⏵\n'
        self.assertEqual([item.body for item in requests.parse(text, "/tmp/example.typ")], ["live ⏵"])

    def test_reserved_assistant_family_cannot_expose_nested_requests(self):
        nested = "<!-- CLAUDE_NOTE(agent): quoted\n<!-- TODO(jason): nested ⏵ -->\n-->"
        self.assertEqual(requests.parse(nested, "/tmp/example.md"), [])

    def test_live_markdown_bom_crlf_frontmatter_and_fences_are_inert(self):
        raw = "<!-- TODO(jason): quoted request ⏵ -->"
        live = "<!-- TODO(jason): live request ⏵ -->"
        text = "\ufeff---\r\nexample: " + raw + "\r\n---\r\n```markdown\r\n" + raw + "\r\n```\r\n" + live
        result = requests.parse(text, "/tmp/live.md")
        self.assertEqual([item.raw for item in result], [live])
        self.assertEqual(text[result[0].start:result[0].end], live)

    def test_live_markdown_fence_delimiter_length_controls_execution(self):
        raw = "<!-- TODO(jason): quoted request ⏵ -->"
        live = "<!-- TODO(jason): live request ⏵ -->"
        text = "~~~~markdown\n~~~\n" + raw + "\n~~~~\n" + live
        self.assertEqual([item.raw for item in requests.parse(text, "/tmp/live.md")], [live])

    def test_live_markdown_blockquote_and_indented_examples_are_inert(self):
        raw = "<!-- TODO(jason): quoted request ⏵ -->"
        live = "<!-- TODO(jason): live request ⏵ -->"
        text = "> ```markdown\n> " + raw + "\n> ```\n\n    " + raw + "\n\n" + live
        self.assertEqual([item.raw for item in requests.parse(text, "/tmp/live.md")], [live])

    def test_unicode_multiline_carrier_offsets_and_signature(self):
        text = "😀\n<!-- TODO(ja\nson): first\nsecond -->"
        item = requests.parse(text, "/tmp/example.md")[0]
        self.assertEqual(text[item.start:item.end], item.raw)
        signed = item.submitted_raw()
        self.assertEqual(requests.parse(signed, "/tmp/example.md")[0].body.strip(), "first\nsecond ⏵")
        self.assertTrue(signed.endswith("⏵ -->"))


if __name__ == "__main__":
    unittest.main()
