from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run(events: list[dict], last_message: str = "", tmp_path: Path | None = None) -> dict:
    assert tmp_path is not None
    events_file = tmp_path / "events.jsonl"
    last_file = tmp_path / "last.txt"

    with events_file.open("w") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")
    last_file.write_text(last_message)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bot.agent_logs",
            "summarize",
            str(events_file),
            str(last_file),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(result.stdout)


def test_uses_last_message_file(tmp_path: Path) -> None:
    summary = run([], last_message="Applied the fix.", tmp_path=tmp_path)

    assert summary["backend"] == "codex"
    assert summary["result"] == "Applied the fix."
    assert summary["events"] == 0


def test_falls_back_to_last_text_event(tmp_path: Path) -> None:
    events = [
        {
            "type": "response.output_item.done",
            "payload": {
                "type": "response.output_item.done",
                "item": {"content": [{"type": "text", "text": "Ran tests successfully."}]},
            },
        }
    ]

    summary = run(events, tmp_path=tmp_path)
    assert summary["result"] == "Ran tests successfully."
    assert summary["num_turns"] == 1


def test_counts_multiple_turns(tmp_path: Path) -> None:
    events = [
        {"type": "assistant", "payload": {"type": "assistant", "content": "Inspecting fixtures."}},
        {
            "type": "response.output_item.done",
            "payload": {
                "type": "response.output_item.done",
                "item": {"content": [{"type": "function_call", "name": "shell"}]},
            },
        },
    ]

    summary = run(events, tmp_path=tmp_path)
    assert summary["events"] == 2
    assert summary["num_turns"] == 2


def test_handles_current_codex_item_events(tmp_path: Path) -> None:
    events = [
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "Working through the fix."},
        },
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 100, "output_tokens": 25},
        },
    ]

    summary = run(events, tmp_path=tmp_path)
    assert summary["result"] == "Working through the fix."
    assert summary["num_turns"] == 1
