"""Recorded-format fixtures with synthetic content; no real session or provider calls."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "session_metrics.py"
spec = importlib.util.spec_from_file_location("session_metrics", SCRIPT)
assert spec is not None and spec.loader is not None
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)
T0 = "2026-09-12T09:00:00Z"
T1 = "2026-09-12T09:00:02Z"


class MetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = SCRIPT.parents[3] / "tmp"
        scratch.mkdir(exist_ok=True)
        cls.work = Path(tempfile.mkdtemp(prefix="session-metrics-", dir=scratch))

    def summary(self, records, harness="auto", tail=""):
        self.path = self.work / (self._testMethodName + ".jsonl")
        self.path.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n" + tail
        )
        return metrics.summarize(self.path, harness)

    def cc(self, kind, content, stamp=T0):
        return {
            "type": kind,
            "timestamp": stamp,
            "sessionId": "cc-explicit-id",
            "message": {"role": kind, "content": content},
        }

    def codex(self, payload, stamp=T0, kind="response_item"):
        return {"type": kind, "timestamp": stamp, "payload": payload}

    def test_cc_deduplicates_streamed_calls_and_counts_error_flags(self):
        call = self.cc(
            "assistant",
            [
                {
                    "type": "tool_use",
                    "id": "call1",
                    "name": "Bash",
                    "input": {"command": "PRIVATE-CONTENT"},
                }
            ],
        )
        result = self.cc(
            "user",
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "call1",
                    "is_error": True,
                    "content": "PRIVATE-OUTPUT",
                }
            ],
            T1,
        )
        report = self.summary([call, call, result])
        self.assertEqual(report["tool_calls"]["total"], 1)
        self.assertEqual(report["duplicate_records"]["calls"], 1)
        self.assertEqual(report["tool_results"]["explicit_error_flags"], 1)
        self.assertEqual(report["call_result_elapsed"]["longest"][0]["seconds"], 2)
        self.assertEqual(report["explicit_result_durations"]["timed_calls"], 0)
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_omp_actual_message_shapes_and_launch_count(self):
        records = [
            {"type": "session", "id": "omp-explicit-id", "timestamp": T0},
            {
                "type": "message",
                "timestamp": T0,
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "toolCall",
                            "id": "a",
                            "name": "task",
                            "arguments": {"tasks": [1, 2]},
                        }
                    ],
                },
            },
            {
                "type": "message",
                "timestamp": T1,
                "message": {
                    "role": "toolResult",
                    "toolCallId": "a",
                    "toolName": "task",
                    "isError": False,
                    "content": [],
                },
            },
        ]
        report = self.summary(records)
        self.assertEqual(report["harness"], "omp")
        self.assertEqual(report["session_ids"], ["omp-explicit-id"])
        self.assertEqual(report["tool_calls"]["visible_subagent_launch_operations"], 1)
        self.assertEqual(report["explicit_result_durations"]["untimed_calls"], 1)

    def test_codex_custom_wrapper_and_function_calls_not_js_regex(self):
        report = self.summary(
            [
                self.codex(
                    {
                        "type": "custom_tool_call",
                        "call_id": "outer",
                        "name": "functions.exec",
                        "input": "await tools.exec_command({cmd:'secret'}); await tools.exec_command({cmd:'secret2'})",
                    }
                ),
                self.codex(
                    {
                        "type": "custom_tool_call_output",
                        "call_id": "outer",
                        "output": "normal error discussion",
                    },
                    T1,
                ),
                self.codex(
                    {
                        "type": "function_call",
                        "call_id": "child",
                        "namespace": "collaboration",
                        "name": "spawn_agent",
                        "arguments": "{}",
                    }
                ),
            ]
        )
        self.assertEqual(report["tool_calls"]["total"], 2)
        self.assertEqual(
            report["tool_calls"]["by_name"],
            {"collaboration.spawn_agent": 1, "functions.exec": 1},
        )
        self.assertEqual(report["tool_results"]["explicit_error_flags"], 0)
        self.assertEqual(report["unmatched_call_count"], 1)

    def test_codex_completion_is_separate_and_duration_units_explicit(self):
        event = self.codex(
            {
                "type": "item_completed",
                "started_at_ms": 1000,
                "completed_at_ms": 4000,
                "item": {
                    "type": "CommandExecution",
                    "id": "native1",
                    "duration": {"secs": 2, "nanos": 500000000},
                    "exit_code": 1,
                    "command": "SECRET-COMMAND",
                    "stdout": "SECRET-OUTPUT",
                },
            },
            kind="event_msg",
        )
        report = self.summary(
            [
                self.codex(
                    {
                        "type": "function_call",
                        "call_id": "native1",
                        "name": "exec_command",
                    }
                ),
                event,
                event,
            ]
        )
        self.assertEqual(report["tool_calls"]["total"], 1)
        self.assertEqual(report["completed_tool_items"]["total"], 1)
        self.assertEqual(
            report["completed_tool_items"]["items"][0]["duration_ms"], 2500
        )
        self.assertEqual(
            report["completed_tool_items"]["timing_basis_counts"],
            {"recorded_duration": 1},
        )
        self.assertEqual(report["completed_tool_items"]["failure_signals"], 1)
        self.assertNotIn("SECRET", json.dumps(report))

    def test_missing_and_unknown_duration_never_assumed_zero(self):
        records = [
            self.codex(
                {
                    "type": "item_completed",
                    "item": {"type": "McpToolCall", "id": "a", "duration": 4},
                },
                kind="event_msg",
            ),
            self.codex(
                {
                    "type": "item_completed",
                    "started_at_ms": 1000,
                    "completed_at_ms": 1300,
                    "item": {"type": "McpToolCall", "id": "b"},
                },
                kind="event_msg",
            ),
        ]
        items = self.summary(records)["completed_tool_items"]["items"]
        self.assertIsNone(items[0]["duration_ms"])
        self.assertEqual(items[1]["duration_ms"], 300)
        self.assertEqual(items[1]["timing_basis"], "event_elapsed")

    def test_malformed_nonobject_and_unmatched_output(self):
        result = self.codex(
            {
                "type": "function_call_output",
                "call_id": "missing",
                "output": '{"isError": true}',
            }
        )
        report = self.summary([result, []], tail='{"truncated":')
        self.assertEqual(report["malformed_lines"], 1)
        self.assertEqual(report["nonobject_lines"], 1)
        self.assertEqual(report["unmatched_result_count"], 1)
        self.assertEqual(report["tool_calls"]["total"], 0)
        self.assertEqual(report["tool_results"]["explicit_error_flags"], 1)

    def test_mixed_formats_require_explicit_override(self):
        records = [
            self.cc("user", "hello"),
            self.codex({"type": "message", "role": "user"}),
        ]
        with self.assertRaises(ValueError):
            self.summary(records)
        self.assertEqual(
            self.summary(records, "cc")["detected_formats"], ["cc", "codex"]
        )

    def test_wrong_explicit_format_cannot_report_false_zero_calls(self):
        with self.assertRaises(ValueError):
            self.summary(
                [
                    self.cc(
                        "assistant", [{"type": "tool_use", "id": "a", "name": "Read"}]
                    )
                ],
                "codex",
            )

    def test_repeated_outputs_count_once_and_preserve_error_evidence(self):
        first = self.cc(
            "user", [{"type": "tool_result", "tool_use_id": "a", "is_error": False}], T1
        )
        second = self.cc(
            "user", [{"type": "tool_result", "tool_use_id": "a", "is_error": True}], T1
        )
        report = self.summary([first, second])
        self.assertEqual(report["tool_results"]["total"], 1)
        self.assertEqual(report["tool_results"]["explicit_error_flags"], 1)
        self.assertEqual(report["duplicate_records"]["results"], 1)

    def test_negative_or_missing_timestamps_are_not_execution_time(self):
        records = [
            self.cc("assistant", [{"type": "tool_use", "id": "a", "name": "Read"}], T1),
            self.cc("user", [{"type": "tool_result", "tool_use_id": "a"}], T0),
            self.cc(
                "assistant", [{"type": "tool_use", "id": "b", "name": "Read"}], None
            ),
        ]
        report = self.summary(records)
        self.assertEqual(report["call_result_elapsed"]["negative_pairs"], 1)
        self.assertEqual(report["call_result_elapsed"]["timed_pairs"], 0)
        self.assertEqual(report["records_missing_timestamp"], 1)

    def test_explicit_result_ms_and_unknown_names(self):
        report = self.summary(
            [
                self.cc("assistant", [{"type": "tool_use", "id": "a"}]),
                self.cc(
                    "user",
                    [{"type": "tool_result", "tool_use_id": "a", "duration_ms": 123}],
                    T1,
                ),
            ]
        )
        self.assertEqual(
            report["explicit_result_durations"]["longest"][0]["milliseconds"], 123
        )
        self.assertEqual(report["tool_calls"]["by_name"], {"unknown": 1})

    def test_cli_outputs_json_without_private_content(self):
        self.summary([self.cc("user", "PRIVATE-PROMPT")])
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.path)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["harness"], "cc")
        self.assertNotIn("PRIVATE", result.stdout)


if __name__ == "__main__":
    unittest.main()
