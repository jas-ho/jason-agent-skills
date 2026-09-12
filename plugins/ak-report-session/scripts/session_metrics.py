#!/usr/bin/env python3
"""Summarize one selected transcript without exporting its private content."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import TypeGuard


def seconds(value):
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.timestamp() if parsed.tzinfo else None
        except ValueError:
            return None
    return None


def numeric(value) -> TypeGuard[int | float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0 <= value < float("inf")
    )


def milliseconds(obj):
    for key in ("duration_ms", "durationMs"):
        if numeric(obj.get(key)):
            return obj[key]
    return None


def record_harness(record):
    kind = record.get("type")
    if kind in ("session_meta", "response_item", "event_msg", "turn_context"):
        return "codex"
    if kind == "session" or (
        kind == "message" and isinstance(record.get("message"), dict)
    ):
        return "omp"
    if kind in ("assistant", "user") and isinstance(record.get("message"), dict):
        return "cc"
    return None


def structured_error(output):
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except ValueError:
            return False
    return isinstance(output, dict) and (
        output.get("isError") is True or output.get("is_error") is True
    )


def summarize(path: Path, harness="auto"):
    records, malformed, nonobjects = [], 0, 0
    # Snapshot exactly this file. No globbing, recursive child reads, or latest lookup.
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if not isinstance(record, dict):
            nonobjects += 1
            continue
        records.append(record)
    formats = {kind for record in records if (kind := record_harness(record))}
    if harness == "auto":
        if len(formats) != 1:
            raise ValueError(
                f"cannot identify one harness (found {sorted(formats)}); select --harness explicitly"
            )
        harness = next(iter(formats))
    elif formats and harness not in formats:
        raise ValueError(
            f"selected harness {harness} does not match detected formats {sorted(formats)}"
        )

    calls: dict[str, dict] = {}
    results: dict[str, dict] = {}
    completions = {}
    session_ids, times = set(), []
    duplicates: Counter[str] = Counter()
    conflicts = 0
    timestamp_missing = 0
    unidentified: Counter[str] = Counter()

    def add_call(identifier, name, stamp, index):
        nonlocal conflicts
        if not isinstance(name, str) or not name:
            name = "unknown"
        if not isinstance(identifier, str) or not identifier:
            unidentified["calls"] += 1
            identifier = f"unidentified-call-{index}"
        if identifier in calls:
            duplicates["calls"] += 1
            conflicts += calls[identifier]["name"] != name
        else:
            calls[identifier] = {"name": name, "timestamp": stamp}

    def add_result(identifier, stamp, error, duration, index):
        if not isinstance(identifier, str) or not identifier:
            unidentified["results"] += 1
            identifier = f"unidentified-result-{index}"
        if identifier in results:
            duplicates["results"] += 1
            # Preserve an explicit error seen in any replay, but do not replace first timing.
            results[identifier]["error"] |= error
        else:
            results[identifier] = {
                "timestamp": stamp,
                "error": error,
                "duration_ms": duration,
            }

    for index, record in enumerate(records):
        stamp = seconds(record.get("timestamp"))
        if stamp is None:
            timestamp_missing += 1
        else:
            times.append(stamp)
        kind = record.get("type")
        message = record.get("message", {})
        message = message if isinstance(message, dict) else {}
        payload = record.get("payload", {})
        payload = payload if isinstance(payload, dict) else {}
        if harness == "cc":
            sid = record.get("sessionId")
        elif harness == "omp":
            sid = record.get("id") if kind == "session" else None
        else:
            sid = (
                (payload.get("session_id") or payload.get("id"))
                if kind == "session_meta"
                else None
            )
        if isinstance(sid, str):
            session_ids.add(sid)

        if harness in ("cc", "omp"):
            allowed = (
                kind in ("assistant", "user") if harness == "cc" else kind == "message"
            )
            if not allowed:
                continue
            content = message.get("content", [])
            for offset, block in enumerate(
                content if isinstance(content, list) else []
            ):
                if not isinstance(block, dict):
                    continue
                marker = block.get("type")
                loc = f"{index}-{offset}"
                if message.get("role") == "assistant" and marker == (
                    "tool_use" if harness == "cc" else "toolCall"
                ):
                    add_call(block.get("id"), block.get("name"), stamp, loc)
                elif (
                    harness == "cc"
                    and message.get("role") == "user"
                    and marker == "tool_result"
                ):
                    add_result(
                        block.get("tool_use_id"),
                        stamp,
                        block.get("is_error") is True,
                        milliseconds(block),
                        loc,
                    )
            if harness == "omp" and message.get("role") == "toolResult":
                add_result(
                    message.get("toolCallId"),
                    stamp,
                    message.get("isError") is True,
                    milliseconds(message),
                    str(index),
                )
        elif kind == "response_item":
            marker = payload.get("type")
            if marker in ("function_call", "custom_tool_call"):
                name = payload.get("name", "unknown")
                namespace = payload.get("namespace")
                if (
                    isinstance(namespace, str)
                    and isinstance(name, str)
                    and not name.startswith(namespace + ".")
                ):
                    name = namespace + "." + name
                add_call(
                    payload.get("call_id") or payload.get("id"), name, stamp, str(index)
                )
            elif marker in ("function_call_output", "custom_tool_call_output"):
                add_result(
                    payload.get("call_id"),
                    stamp,
                    structured_error(payload.get("output")),
                    milliseconds(payload),
                    str(index),
                )
        elif kind == "event_msg" and payload.get("type") == "item_completed":
            item = payload.get("item", {})
            if not isinstance(item, dict) or item.get("type") not in {
                "CommandExecution",
                "McpToolCall",
                "DynamicToolCall",
                "CollabAgentToolCall",
            }:
                continue
            identifier = item.get("id")
            if not isinstance(identifier, str) or not identifier:
                unidentified["completed_items"] += 1
                identifier = f"unidentified-item-{index}"
            if identifier in completions:
                duplicates["completed_items"] += 1
                continue
            duration, basis = None, None
            value = item.get("duration")
            if (
                isinstance(value, dict)
                and numeric(value.get("secs"))
                and numeric(value.get("nanos"))
                and value["nanos"] < 1_000_000_000
            ):
                duration, basis = (
                    value["secs"] * 1000 + value["nanos"] / 1_000_000,
                    "recorded_duration",
                )
            else:
                start, end = (
                    payload.get("started_at_ms"),
                    payload.get("completed_at_ms"),
                )
                if numeric(start) and numeric(end) and end >= start:
                    duration, basis = end - start, "event_elapsed"
            failed = str(item.get("status", "")).lower() in {"failed", "error"}
            exit_code = item.get("exit_code")
            failed |= (
                isinstance(exit_code, int)
                and not isinstance(exit_code, bool)
                and exit_code != 0
            )
            completions[identifier] = {
                "type": item["type"],
                "duration_ms": duration,
                "timing_basis": basis,
                "failure_signal": failed,
            }

    elapsed, explicit, negative = [], [], 0
    for identifier, call in calls.items():
        result = results.get(identifier)
        if not result:
            continue
        if result["duration_ms"] is not None:
            explicit.append(
                {
                    "id": identifier,
                    "name": call["name"],
                    "milliseconds": result["duration_ms"],
                }
            )
        start, end = call["timestamp"], result["timestamp"]
        if start is not None and end is not None:
            if end >= start:
                elapsed.append(
                    {
                        "id": identifier,
                        "name": call["name"],
                        "seconds": round(end - start, 6),
                    }
                )
            else:
                negative += 1
    counts = Counter(call["name"] for call in calls.values())
    launch_names = {"agent", "task", "spawn_agent"}
    launch_count = sum(
        count
        for name, count in counts.items()
        if name.split(".")[-1].split("__")[-1].lower() in launch_names
    )
    return {
        "harness": harness,
        "session_ids": sorted(session_ids),
        "records": len(records),
        "malformed_lines": malformed,
        "nonobject_lines": nonobjects,
        "detected_formats": sorted(formats),
        "records_missing_timestamp": timestamp_missing,
        "file_span_seconds": round(max(times) - min(times), 6)
        if len(times) >= 2
        else None,
        "tool_calls": {
            "total": len(calls),
            "by_name": dict(sorted(counts.items())),
            "visible_subagent_launch_operations": launch_count,
        },
        "tool_results": {
            "total": len(results),
            "explicit_error_flags": sum(result["error"] for result in results.values()),
        },
        "unmatched_call_count": len(calls.keys() - results.keys()),
        "unmatched_result_count": len(results.keys() - calls.keys()),
        "call_result_elapsed": {
            "timed_pairs": len(elapsed),
            "negative_pairs": negative,
            "untimed_calls": len(calls) - len(elapsed),
            "longest": sorted(elapsed, key=lambda row: row["seconds"], reverse=True)[
                :10
            ],
        },
        "explicit_result_durations": {
            "timed_calls": len(explicit),
            "untimed_calls": len(calls) - len(explicit),
            "longest": sorted(
                explicit, key=lambda row: row["milliseconds"], reverse=True
            )[:10],
        },
        "completed_tool_items": {
            "total": len(completions),
            "by_type": dict(Counter(item["type"] for item in completions.values())),
            "failure_signals": sum(
                item["failure_signal"] for item in completions.values()
            ),
            "timing_basis_counts": dict(
                Counter(
                    item["timing_basis"] or "missing" for item in completions.values()
                )
            ),
            "items": [
                {"id": identifier, **item} for identifier, item in completions.items()
            ],
        },
        "duplicate_records": dict(duplicates),
        "conflicting_call_names": conflicts,
        "unidentified_records": dict(unidentified),
        "limitations": [
            "Counts describe the selected physical log, including any copied history or sibling branches.",
            "File span and call-result elapsed include idle/scheduling time; they are not execution durations.",
            "Completion items are separate evidence and must not be added to tool-call totals.",
            "Child transcripts and nested function bodies are not traversed; missing error flags do not prove success.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    parser.add_argument(
        "--harness", choices=("auto", "cc", "codex", "omp"), default="auto"
    )
    args = parser.parse_args()
    try:
        result = summarize(args.transcript, args.harness)
    except (OSError, UnicodeError, ValueError) as error:
        # Do not echo input contents on parsing errors.
        print(f"Session metrics failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
