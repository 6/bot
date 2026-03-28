from __future__ import annotations

import json
from pathlib import Path

from bot import adapt_action_output


def test_sdk_message_array(tmp_path: Path) -> None:
    messages = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "I completed the requested change."},
                ],
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "num_turns": 12,
            "total_cost_usd": 0.85,
            "duration_ms": 120000,
            "is_error": False,
        },
    ]
    execution_file = tmp_path / "execution.json"
    output_file = tmp_path / "result.json"
    execution_file.write_text(json.dumps(messages))

    adapt_action_output.adapt(execution_file, output_file)

    result = json.loads(output_file.read_text())
    assert result["total_cost_usd"] == 0.85
    assert result["num_turns"] == 12
    assert result["result"] == "I completed the requested change."
    assert result["duration_ms"] == 120000


def test_dict_format(tmp_path: Path) -> None:
    data = {
        "total_cost_usd": 1.5,
        "num_turns": 8,
        "result": "Done.",
        "duration_ms": 60000,
    }
    execution_file = tmp_path / "execution.json"
    output_file = tmp_path / "result.json"
    execution_file.write_text(json.dumps(data))

    adapt_action_output.adapt(execution_file, output_file)

    result = json.loads(output_file.read_text())
    assert result["total_cost_usd"] == 1.5
    assert result["num_turns"] == 8
    assert result["result"] == "Done."


def test_empty_file(tmp_path: Path) -> None:
    execution_file = tmp_path / "execution.json"
    output_file = tmp_path / "result.json"
    execution_file.write_text("")

    adapt_action_output.adapt(execution_file, output_file)

    result = json.loads(output_file.read_text())
    assert result["result"] == "no result"


def test_multiple_assistant_messages(tmp_path: Path) -> None:
    messages = [
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "First message."}]},
        },
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Final summary."}]},
        },
        {
            "type": "result",
            "num_turns": 5,
            "total_cost_usd": 0.3,
        },
    ]
    execution_file = tmp_path / "execution.json"
    output_file = tmp_path / "result.json"
    execution_file.write_text(json.dumps(messages))

    adapt_action_output.adapt(execution_file, output_file)

    result = json.loads(output_file.read_text())
    assert result["result"] == "Final summary."
