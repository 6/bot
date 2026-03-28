from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run(jsonl_content: str, max_lines: int = 500) -> str:
    with Path("agent-log-test.jsonl").open("w") as handle:
        handle.write(jsonl_content)

    path = Path("agent-log-test.jsonl")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "bot.agent_logs",
                "extract",
                str(path),
                "--max-lines",
                str(max_lines),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    finally:
        path.unlink(missing_ok=True)


def make_event(content_blocks: list[dict]) -> str:
    return json.dumps({"type": "assistant", "message": {"content": content_blocks}})


def test_extracts_text() -> None:
    output = run(make_event([{"type": "text", "text": "I found the bug."}]) + "\n")
    assert "I found the bug." in output


def test_extracts_bash_tool() -> None:
    output = run(
        make_event([{"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}}]) + "\n"
    )
    assert "`Bash`" in output
    assert "pytest -q" in output


def test_extracts_codex_response_item_function_call() -> None:
    line = json.dumps(
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": "pytest tests/test_runtime.py -q"}),
            },
        }
    )

    output = run(line + "\n")
    assert "`exec_command`" in output
    assert "pytest tests/test_runtime.py -q" in output


def test_extracts_codex_item_file_change() -> None:
    line = json.dumps(
        {
            "type": "item.completed",
            "item": {
                "type": "file_change",
                "changes": [{"path": "/tmp/src/service/config.py"}],
            },
        }
    )

    output = run(line + "\n")
    assert "`file_change`" in output
    assert "config.py" in output


def test_extract_skips_empty_text() -> None:
    output = run(make_event([{"type": "text", "text": "   "}]) + "\n")
    assert output.strip() == ""
