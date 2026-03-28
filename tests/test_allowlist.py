from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from bot import allowlist


def test_default_allowlist_contains_nitrocop() -> None:
    allowed = allowlist.load_allowlist(allowlist.default_config_path())
    assert allowed == ["6/nitrocop"]


def test_is_allowed_repository_uses_config_file(tmp_path: Path) -> None:
    config = tmp_path / "allowlist.toml"
    config.write_text('allowed_repositories = ["6/example"]\n')

    assert allowlist.is_allowed_repository("6/example", config) is True
    assert allowlist.is_allowed_repository("6/other", config) is False


def test_cli_rejects_unlisted_repo(tmp_path: Path) -> None:
    config = tmp_path / "allowlist.toml"
    config.write_text('allowed_repositories = ["6/nitrocop"]\n')

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bot.allowlist",
            "--config",
            str(config),
            "check-repo",
            "6/not-allowed",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "not allowed" in result.stderr
