from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from bot import agent_runtime


def test_build_paths_for_named_profile() -> None:
    runner_temp = Path("/tmp/runner")
    paths = agent_runtime.build_paths("example-task", runner_temp)

    assert paths["AGENT_RUNTIME_ROOT"] == "/tmp/runner/example-task"
    assert paths["TASK_FILE"].endswith("/example-task/context/task.md")
    assert paths["FINAL_TASK_FILE"].endswith("/example-task/context/final-task.md")
    assert paths["AGENT_SCOPE_REPORT_FILE"].endswith("/example-task/recovery/scope.md")


def test_current_paths_uses_centralized_runtime_defaults(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_RUNTIME_ROOT", raising=False)
    paths = agent_runtime.current_paths("example-task")

    assert paths["AGENT_ARTIFACT_MANIFEST_FILE"].endswith("/example-task/recovery/artifacts.txt")


def test_runtime_root_uses_override_when_set(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_ROOT", str(tmp_path / "custom-root"))
    assert agent_runtime.runtime_root("ignored-name") == (tmp_path / "custom-root").resolve()


def test_cli_emits_env_assignments_and_creates_directories(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bot.agent_runtime",
            "example-task",
            "--runner-temp",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    lines = dict(line.split("=", 1) for line in result.stdout.strip().splitlines())
    assert Path(lines["AGENT_RUNTIME_ROOT"]).is_dir()
    assert Path(lines["AGENT_AGENT_DIR"]).is_dir()
    assert Path(lines["AGENT_CONTEXT_DIR"]).is_dir()
    assert Path(lines["AGENT_RECOVERY_DIR"]).is_dir()


def test_profile_name_only_changes_root_directory() -> None:
    runner_temp = Path("/tmp/runner")
    alpha = agent_runtime.build_paths("alpha", runner_temp)
    beta = agent_runtime.build_paths("beta", runner_temp)

    assert alpha["TASK_FILE"].replace("/alpha/", "/profile/") == beta["TASK_FILE"].replace("/beta/", "/profile/")
    assert alpha["AGENT_RUNTIME_ROOT"].endswith("/alpha")
    assert beta["AGENT_RUNTIME_ROOT"].endswith("/beta")
