"""Opt-in real Obsidian regression; ordinary discovery never contacts the GUI.

Run from the co-edit root:
    COEDIT_NATIVE_TESTS=1 python3 -m unittest discover -s tests -p test_editor_native.py -v

Uses one UUID-named note in the running vault and private temporary state. Failed
runs retain that note/state (including evidence.json); unexpected edits or a
user-claimed leaf are never discarded. No model or real writing trial is used.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import editor
from scripts.runtime import Runtime, RuntimeError as CoeditError


@unittest.skipUnless(os.environ.get("COEDIT_NATIVE_TESTS") == "1" and sys.platform == "darwin",
                     "requires COEDIT_NATIVE_TESTS=1 and macOS with running Obsidian")
class NativePreparedFence(unittest.TestCase):
    def evaluate(self, body, **values):
        token = "NATIVE_" + uuid.uuid4().hex + ":"
        args = {"key": self.key, "owner": self.owner, "relative": self.relative, "vault": self.vault, **values}
        code = """(async()=>{const token=TOKEN;try{const a=ARGS;
            if(a.vault && require('fs').realpathSync(app.vault.adapter.getBasePath())!==a.vault)
                throw Error('Running vault changed; refusing fixture access');
            const p=app[a.key];const value=await(async()=>{BODY})();
            return token+JSON.stringify({ok:true,value});
        }catch(e){return token+JSON.stringify({ok:false,error:String(e.stack||e)});}})()"""
        code = code.replace("TOKEN", json.dumps(token)).replace("ARGS", json.dumps(args)).replace("BODY", body)
        read_fd, write_fd = os.pipe()
        try:
            result = subprocess.run([self.executable, "eval", "code=" + code], stdin=read_fd,
                                    capture_output=True, text=True, timeout=45)
        finally:
            os.close(read_fd)
            os.close(write_fd)
        envelopes = []
        for suffix in result.stdout.split(token)[1:]:
            try:
                value, _ = json.JSONDecoder().raw_decode(suffix)
            except ValueError:
                continue
            if isinstance(value, dict) and isinstance(value.get("ok"), bool):
                envelopes.append(value)
        self.assertEqual(len(envelopes), 1, (result.returncode, result.stdout, result.stderr))
        self.assertTrue(envelopes[0]["ok"], envelopes[0].get("error"))
        return envelopes[0]["value"]

    def setUp(self):
        executable = shutil.which("obsidian")
        if not executable:
            self.skipTest("obsidian CLI is not on PATH")
        self.executable = str(Path(executable).resolve())
        running = subprocess.run(["pgrep", "-f", "/Obsidian.app/Contents/MacOS/[Oo]bsidian"],
                                 capture_output=True, timeout=5)
        if running.returncode != 0:
            self.skipTest("Obsidian must already be running; this test will not launch it")
        self.owner = str(uuid.uuid4())
        self.key = "__coeditNativeFence_" + self.owner.replace("-", "")
        self.relative = "coedit-native-fence-" + self.owner + ".md"
        self.vault = None
        try:
            capability = self.evaluate("""
                return {base:require('fs').realpathSync(app.vault.adapter.getBasePath()),
                    ready:!!app.workspace.activeLeaf?.parent && !!app.workspace.layoutReady};
            """)
        except (AssertionError, OSError, subprocess.TimeoutExpired) as exc:
            self.skipTest("Obsidian eval unavailable: " + str(exc))
        if not capability["ready"]:
            self.skipTest("Obsidian needs a ready workspace with an existing pane")
        self.vault = capability["base"]
        self.absolute = str(Path(self.vault) / self.relative)
        self.state = Path(tempfile.mkdtemp(prefix="coedit-native-fence-")).resolve()
        if self.state.is_relative_to(Path(self.vault)):
            self.state.rmdir()
            self.skipTest("Temporary state must be outside the running vault")
        self.runtime = None
        self.attached = False
        self.passed = False
        self.evidence = {"owner": self.owner, "path": self.absolute, "state": str(self.state), "cases": []}
        self.addCleanup(self.cleanup)
        text = ("# Native fence regression\n\nalpha\ntheta\n\n"
                "<!-- TODO(jason): Change alpha to beta -->\n"
                "<!-- FIXME(jason): Change theta to kappa -->\n")
        self.evaluate("""
            if(p || app.vault.getAbstractFileByPath(a.relative)) throw Error('Fixture collision');
            const f=app[a.key]={owner:a.owner,last:a.text,texts:new Set([a.text]),claimed:false};
            f.file=await app.vault.create(a.relative,a.text);
            const active=app.workspace.activeLeaf,focused=document.activeElement;
            if(!active?.parent) throw Error('No existing pane');
            const parents=new Map();app.workspace.iterateAllLeaves(l=>parents.set(l,l.parent));
            const leaf=app.workspace.getLeaf('tab');
            if(parents.has(leaf)) throw Error('Refusing existing leaf reuse');
            f.leaf=leaf;f.parent=active.parent;f.parents=parents;
            // Restore only getLeaf's synchronous activation, never focus after await.
            if(app.workspace.activeLeaf===leaf){
                app.workspace.setActiveLeaf(active,{focus:false});
                if(focused?.isConnected && typeof focused.focus==='function') focused.focus({preventScroll:true});
            }
            f.activation=app.workspace.on('active-leaf-change',l=>{if(l===leaf)f.claimed=true;});
            await leaf.openFile(f.file,{active:false});
            if(!leaf.view.editor || app.workspace.activeLeaf!==active || leaf.parent!==f.parent ||
                [...parents].some(([l,parent])=>l.parent!==parent)) throw Error('Inactive editor verification failed');
            f.replace=(before,after)=>{
                const e=f.leaf.view.editor,t=e.getValue(),i=t.indexOf(before);
                if(f.claimed || f.leaf.view.file!==f.file || t!==f.last || i<0 || t.indexOf(before,i+1)>=0)
                    throw Error('Preserving unexpected fixture edits or user-owned leaf');
                e.replaceRange(after,e.offsetToPos(i),e.offsetToPos(i+before.length));
                const expected=t.slice(0,i)+after+t.slice(i+before.length);
                if(e.getValue()!==expected) throw Error('Unexpected editor replacement');
                f.last=expected;f.texts.add(expected);return expected;
            };
            return {path:f.file.path};
        """, text=text)
        self.runtime = Runtime(self.state, editor_call=editor.call)
        self.runtime.attach(self.absolute, self.owner, "omp")
        self.attached = True

    def cleanup(self):
        errors = []
        # Restore first, even when stop, assertions, or fixture creation failed.
        try:
            self.evaluate("if(p?.owner===a.owner && p.restore)p.restore();return true;")
        except Exception as exc:
            errors.append(str(exc))
        if self.runtime:
            try:
                if self.attached:
                    self.runtime.stop(self.owner)
            except Exception as exc:
                errors.append(str(exc))
            finally:
                try:
                    self.runtime.close()
                except Exception as exc:
                    errors.append(str(exc))
        try:
            self.evidence["cleanup"] = self.evaluate("""
                if(!p || p.owner!==a.owner)return {absent:true};
                if(p.restore)p.restore();
                if(p.activation)app.workspace.offref(p.activation);
                const observed=p.leaf?.view.editor?.getValue();
                const preserve=reason=>({preserved:reason,expected:p.last,observed});
                if(!a.passed)return preserve('failed regression; retained evidence');
                if(!p.file || app.vault.getAbstractFileByPath(a.relative)!==p.file || p.file.path!==a.relative)
                    return preserve('fixture identity changed');
                const disk=await app.vault.read(p.file);
                const others=[];app.workspace.iterateAllLeaves(l=>{if(l!==p.leaf && l.view?.file===p.file)others.push(l);});
                if(!p.texts.has(disk) || (p.leaf && (p.leaf.view.file!==p.file ||
                    p.leaf.view.editor?.getValue()!==p.last || p.claimed || others.length ||
                    app.workspace.activeLeaf===p.leaf || p.leaf.parent!==p.parent ||
                    [...p.parents].some(([l,parent])=>l.parent!==parent))))
                    return preserve('unexpected edits or user-owned leaf/layout');
                if(p.leaf)p.leaf.detach();
                await app.vault.delete(p.file);delete app[a.key];return {deleted:true};
            """, passed=self.passed and not errors)
        except Exception as exc:
            errors.append(str(exc))
        clean = self.evidence.get("cleanup", {}).get("deleted", False)
        if self.passed and clean and not errors:
            shutil.rmtree(self.state)
        else:
            self.evidence["cleanup_errors"] = errors
            (self.state / "evidence.json").write_text(json.dumps(self.evidence, indent=2))
            print("Native fence evidence retained: " + str(self.state / "evidence.json"), file=sys.stderr)
        if errors or (self.passed and not clean):
            self.fail("Native cleanup preserved fixture/state: " + repr(errors or self.evidence["cleanup"]))

    def test_prepared_target_drift_rejects_without_replay_and_recovers(self):
        for kind, before, after, late_proof in [("TODO", "alpha", "beta", False), ("FIXME", "theta", "kappa", True)]:
            self.exercise_rejection(kind, before, after, late_proof)
        self.passed = True

    def exercise_rejection(self, kind, before, after, late_proof):
        unsigned = "<!-- " + kind + "(jason): Change " + before + " to " + after + " -->"
        signed = unsigned.replace(" -->", " ⏵ -->")
        text = self.evaluate("return p.replace(a.before,a.after);", before=unsigned, after=signed)
        row = next(item for item in self.runtime.status(self.owner)["pending"] if item["raw"] == signed)
        self.assertEqual(row["generation"], 1)
        operation = "native-rejected-" + uuid.uuid4().hex
        case = {"operation": operation, "request": row["id"], "late_proof": late_proof}
        self.evidence["cases"].append(case)
        self.evaluate("""
            const fs=require('fs'),original=fs.writeFileSync; p.fired=false;
            p.restore=()=>{fs.writeFileSync=original;clearTimeout(p.timer);};
            // App-side failsafe also restores if Python or its transport disappears.
            p.timer=setTimeout(p.restore,60000);
            fs.writeFileSync=function(fd,data,...rest){
                const result=original.call(this,fd,data,...rest);
                let record;try{if(typeof data==='string')record=JSON.parse(data);}catch(_){}
                if(record?.operation_id===a.operation && record.status==='prepared' && record.owner===a.owner){
                    p.restore();p.fired=true;p.replace(a.before,a.after);
                }
                return result;
            };
            return true;
        """, operation=operation, owner=self.owner, before=before + "\n", after=before + " human\n")
        bridge = self.runtime.editor

        def lossy(action, payload):
            if payload.get("operation_id") == operation:
                if action == "receipt" and late_proof:
                    raise OSError("Injected temporarily unavailable proof")
                if action == "write":
                    try:
                        return bridge(action, payload)
                    except Exception as exc:
                        raise OSError("Injected lost response after real native rejection") from exc
            return bridge(action, payload)

        target = {"path": self.absolute, "expected": before + "\n", "replacement": after + "\n"}
        self.runtime.editor = lossy
        try:
            with self.assertRaises(CoeditError) as raised:
                self.runtime.write(self.owner, row["id"], 1, operation, target)
            case["error"] = raised.exception.code
            self.assertEqual(raised.exception.code, "uncertain-write" if late_proof else "operation-rejected")
        finally:
            self.runtime.editor = bridge
            case["native"] = self.evaluate("p.restore();return {fired:p.fired,text:p.leaf.view.editor.getValue()};")
        self.assertTrue(case["native"]["fired"])
        human = text.replace(before + "\n", before + " human\n", 1)
        self.assertEqual(case["native"]["text"], human)
        # Read the actual durable receipt, not a cached bridge response.
        proofs = [json.loads(path.read_text()) for path in (self.state / "editor-receipts").rglob("*.json")]
        proof = next(item for item in proofs if item["operation_id"] == operation)
        case["proof"] = proof
        self.assertEqual(proof["status"], "rejected")
        self.assertIs(proof["attempted"], False)
        if late_proof:
            reconciled = self.runtime.reconcile(self.owner, row["id"])
            case["readonly_state"] = reconciled["request"]["state"]
            self.assertEqual(case["readonly_state"], "uncertain-write")
            self.assertEqual(self.evaluate("return p.leaf.view.editor.getValue();"), human)
        normal = next(item for item in self.runtime.status(self.owner)["pending"] if item["id"] == row["id"])
        self.assertIn(normal["state"], {"submitted", "working"})
        self.evaluate("return p.replace(a.before,a.after);", before=before + " human\n", after=before + "\n")
        # The original target now matches again; replay would visibly mutate it.
        with self.assertRaises(CoeditError) as raised:
            self.runtime.write(self.owner, row["id"], 1, operation, target)
        self.assertEqual(raised.exception.code, "operation-rejected")
        self.assertEqual(self.evaluate("return p.leaf.view.editor.getValue();"), text)
        fresh = self.runtime.write(self.owner, row["id"], 1, operation + "-fresh", target)
        self.assertEqual(fresh["receipt"]["status"], "committed")
        expected = text.replace(before + "\n", after + "\n", 1)
        self.evaluate("""
            if(p.leaf.view.editor.getValue()!==a.expected)throw Error('Fresh guarded edit mismatch');
            p.last=a.expected;p.texts.add(a.expected);return p.last;
        """, expected=expected)
        case["passed"] = True


if __name__ == "__main__":
    unittest.main()
