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


def test_load_request_rejects_too_many_operations(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    ops = [{"type": "comment_issue", "issue_number": 1, "body_file": "b.md"}] * 101
    request_path.write_text(json.dumps({"operations": ops}))

    try:
        repo_write._load_request(request_path)  # noqa: SLF001
    except ValueError as exc:
        assert "too many" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError for too many operations")


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


def test_resolve_request_file_rejects_path_traversal(tmp_path: Path) -> None:
    """_resolve_request_file must reject relative paths that escape the request directory."""
    request_dir = tmp_path / "artifact"
    request_dir.mkdir()
    request_path = request_dir / "request.json"
    request_path.write_text("{}")

    # Create a file outside the artifact directory that traversal would reach
    secret = tmp_path / "secret.txt"
    secret.write_text("sensitive data")

    try:
        repo_write._resolve_request_file(request_path, "../secret.txt", field="body_file")  # noqa: SLF001
    except ValueError as exc:
        assert "escapes" in str(exc) or "traversal" in str(exc)
    else:
        raise AssertionError("expected ValueError for path traversal attempt")


def test_resolve_request_file_allows_valid_relative_path(tmp_path: Path) -> None:
    """_resolve_request_file must still work for files inside the request directory."""
    request_dir = tmp_path / "artifact"
    request_dir.mkdir()
    request_path = request_dir / "request.json"
    request_path.write_text("{}")

    body = request_dir / "body.md"
    body.write_text("hello")

    result = repo_write._resolve_request_file(request_path, "body.md", field="body_file")  # noqa: SLF001
    assert result.resolve() == body.resolve()


def test_resolve_request_file_rejects_symlink_escape(tmp_path: Path) -> None:
    """_resolve_request_file must reject symlinks that point outside the request directory."""
    request_dir = tmp_path / "artifact"
    request_dir.mkdir()
    request_path = request_dir / "request.json"
    request_path.write_text("{}")

    secret = tmp_path / "secret.txt"
    secret.write_text("sensitive data")
    (request_dir / "link.txt").symlink_to(secret)

    try:
        repo_write._resolve_request_file(request_path, "link.txt", field="body_file")  # noqa: SLF001
    except ValueError as exc:
        assert "escapes" in str(exc) or "traversal" in str(exc)
    else:
        raise AssertionError("expected ValueError for symlink escape")
