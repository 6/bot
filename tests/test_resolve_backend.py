from __future__ import annotations

import os
import subprocess
import sys

from bot import resolve_backend


def _run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "bot.resolve_backend", *args],
        capture_output=True,
        text=True,
        env=merged_env,
    )


def test_all_backends_resolve() -> None:
    for name in resolve_backend.BACKENDS:
        config = resolve_backend.resolve(name)
        assert config["cli"] in ("claude", "codex", "claude-action")
        assert config["log_format"] in ("claude", "codex")
        assert config["setup_cmd"]
        if not config.get("action"):
            assert config["run_cmd"]
        assert config["log_pattern"]


def test_codex_normal_uses_project_modules() -> None:
    config = resolve_backend.resolve("codex-normal")

    assert config["cli"] == "codex"
    assert config["log_format"] == "codex"
    assert "bot.guard_backend_secrets" in config["setup_cmd"]
    assert "bot.validate_codex_auth" in config["setup_cmd"]
    assert "CODEX_AUTH_JSON" in config["setup_cmd"]
    assert "-m gpt-5.4" in config["run_cmd"]
    assert "model_reasoning_effort=high" in config["run_cmd"]
    assert "bot.agent_logs summarize" in config["run_cmd"]


def test_minimax_uses_claude() -> None:
    config = resolve_backend.resolve("minimax")

    assert config["cli"] == "claude"
    assert config["log_format"] == "claude"
    assert "ANTHROPIC_BASE_URL" in config["env"]
    assert "bot.guard_backend_secrets" in config["setup_cmd"]
    assert "ANTHROPIC_AUTH_TOKEN" in config["setup_cmd"]
    assert "claude.ai/install.sh" in config["setup_cmd"]


def test_choose_backend_outputs_family_strength_and_labels() -> None:
    result = _run_cli("choose", "codex", "normal")

    assert result.returncode == 0
    fields = dict(line.split("=", 1) for line in result.stdout.strip().splitlines())
    assert fields["backend"] == "codex-normal"
    assert fields["family"] == "codex"
    assert fields["strength"] == "normal"
    assert fields["display_label"] == "codex / normal"
    assert fields["model_label"] == "gpt-5.4 (high)"


def test_claude_normal_uses_api_key_install_path() -> None:
    config = resolve_backend.resolve("claude-normal")

    assert config["cli"] == "claude"
    assert config["log_format"] == "claude"
    assert "ANTHROPIC_BASE_URL" not in config["env"]
    assert "bot.guard_backend_secrets" in config["setup_cmd"]
    assert "ANTHROPIC_API_KEY" in config["setup_cmd"]
    assert "claude.ai/install.sh" in config["setup_cmd"]


def test_claude_oauth_normal() -> None:
    config = resolve_backend.resolve("claude-oauth-normal")

    assert config["cli"] == "claude-action"
    assert config["action"] is True
    assert config["log_format"] == "claude"
    assert config["run_cmd"] == ""
    assert "CLAUDE_CODE_OAUTH_TOKEN" in config["setup_cmd"]
    assert "ANTHROPIC_API_KEY" not in config["setup_cmd"]
    assert "claude.ai/install.sh" not in config["setup_cmd"]
    assert config["env"]["ANTHROPIC_MODEL"] == "claude-opus-4-6"
    assert config["reasoning_effort"] == "medium"
    assert "CLAUDE_CODE_OAUTH_TOKEN" in config["secrets"]


def test_choose_claude_oauth_prefers_oauth_when_present(monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-token")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    backend, strength, reason = resolve_backend.choose_backend("claude", "normal")

    assert backend == "claude-oauth-normal"
    assert strength == "normal"
    assert "oauth" in reason


def test_cli_output_includes_action_flag() -> None:
    oauth_result = _run_cli("claude-oauth-normal")
    assert oauth_result.returncode == 0
    oauth_fields = dict(line.split("=", 1) for line in oauth_result.stdout.strip().splitlines())
    assert oauth_fields["action"] == "true"

    normal_result = _run_cli("claude-normal")
    assert normal_result.returncode == 0
    normal_fields = dict(line.split("=", 1) for line in normal_result.stdout.strip().splitlines())
    assert normal_fields["action"] == "false"


def test_unknown_backend_exits() -> None:
    result = _run_cli("unknown")

    assert result.returncode != 0
    assert "Unknown backend" in result.stderr


def test_no_args_exits() -> None:
    result = _run_cli()
    assert result.returncode != 0
