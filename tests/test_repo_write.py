from __future__ import annotations

import json
import subprocess
from pathlib import Path

from bot import repo_write


def test_render_template_replaces_known_placeholders() -> None:
    rendered = repo_write._render_template(  # noqa: SLF001
        "signed={{SIGNED_SHA}} target={{TARGET_REF}} keep={{UNKNOWN}}",
        {"SIGNED_SHA": "abc123", "TARGET_REF": "refs/heads/main"},
    )
    assert rendered == "signed=abc123 target=refs/heads/main keep={{UNKNOWN}}"


def test_load_request_rejects_unknown_operation_type(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"operations": [{"type": "nope"}]}))

    try:
        repo_write._load_request(request_path)  # noqa: SLF001
    except ValueError as exc:
        assert "unknown type" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown operation type")


def test_load_request_defaults_match_mode(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"operations": [{"type": "comment_pr", "pr_number": 1, "body_file": "body.md"}]}))

    loaded = repo_write._load_request(request_path)  # noqa: SLF001
    assert loaded["match_mode"] == "current_head"


def test_has_worktree_changes_detects_untracked_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True, text=True)

    (repo / "tracked.txt").write_text("base\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True, text=True)

    assert repo_write._has_worktree_changes(repo) is False  # noqa: SLF001

    (repo / "new.txt").write_text("new\n")

    assert repo_write._has_worktree_changes(repo) is True  # noqa: SLF001
