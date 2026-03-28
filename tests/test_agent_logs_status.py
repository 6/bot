from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from bot import agent_logs, resolve_backend


def write_jsonl(path: str, events: list[dict]) -> None:
    with open(path, "w") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")


def make_assistant(content_blocks: list[dict]) -> dict:
    return {"type": "assistant", "message": {"content": content_blocks}}


def test_get_status_text() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as handle:
        write_jsonl(handle.name, [make_assistant([{"type": "text", "text": "Investigating the bug."}])])
        status = agent_logs.get_status(handle.name, backend="claude-normal")

    assert status["events"] == 1
    assert status["last_type"] == "assistant"
    assert "Investigating the bug" in status["last_text"]
    assert status["last_tool"] is None


def test_get_status_tool() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as handle:
        write_jsonl(
            handle.name,
            [
                make_assistant(
                    [{"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}}]
                )
            ],
        )
        status = agent_logs.get_status(handle.name, backend="claude-normal")

    assert status["last_tool"] == "Bash"


def test_get_status_handles_current_codex_file_change() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as handle:
        write_jsonl(
            handle.name,
            [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "file_change",
                        "changes": [{"path": "/tmp/src/service/router.py"}],
                    },
                }
            ],
        )
        status = agent_logs.get_status(handle.name, backend="codex-hard")

    assert status["last_type"] == "file_change"
    assert status["last_tool"] == "file_change:router.py"


def test_get_status_looks_past_token_count_noise() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as handle:
        events = [
            {
                "type": "event_msg",
                "payload": {
                    "type": "agent_message",
                    "message": "Useful status before token churn.",
                },
            }
        ]
        for _ in range(20):
            events.append(
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {"total_token_usage": {"input_tokens": 1}},
                    },
                }
            )
        write_jsonl(handle.name, events)
        status = agent_logs.get_status(handle.name, backend="codex-hard")

    assert status["last_type"] == "agent_message"
    assert "Useful status before token churn" in status["last_text"]


def test_find_logfile_uses_backend_family_resolution(tmp_path: Path) -> None:
    ref = tmp_path / "task.md"
    ref.write_text("task\n")
    time.sleep(0.05)
    log = tmp_path / "session.jsonl"
    log.write_text("{}\n")

    original_patterns = dict(agent_logs.LOG_FORMAT_PATTERNS)
    try:
        agent_logs.LOG_FORMAT_PATTERNS["claude"] = str(log)
        found = agent_logs.find_logfile(ref, backend="claude-normal")
    finally:
        agent_logs.LOG_FORMAT_PATTERNS.clear()
        agent_logs.LOG_FORMAT_PATTERNS.update(original_patterns)

    assert found == str(log)


def test_find_logfile_returns_none_when_pattern_has_no_matches(tmp_path: Path) -> None:
    ref = tmp_path / "task.md"
    ref.write_text("task\n")

    original_patterns = dict(agent_logs.LOG_FORMAT_PATTERNS)
    try:
        agent_logs.LOG_FORMAT_PATTERNS["codex"] = str(tmp_path / "missing" / "*.jsonl")
        found = agent_logs.find_logfile(ref, backend="codex")
    finally:
        agent_logs.LOG_FORMAT_PATTERNS.clear()
        agent_logs.LOG_FORMAT_PATTERNS.update(original_patterns)

    assert found is None


def test_agent_log_formats_match_resolve_backend_outputs() -> None:
    expected = {config["log_format"] for config in resolve_backend.BACKENDS.values()}
    assert expected == set(agent_logs.LOG_FORMAT_PATTERNS)
