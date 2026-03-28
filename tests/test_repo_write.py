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


def test_load_request_accepts_close_pr_operation(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"operations": [{"type": "close_pr", "pr": "123"}]}))

    loaded = repo_write._load_request(request_path)  # noqa: SLF001
    assert loaded["operations"][0]["type"] == "close_pr"


def test_load_request_accepts_claim_flow_operations(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "operations": [
                    {"type": "ensure_labels", "labels": [{"name": "type:cop-fix", "color": "0e8a16"}]},
                    {"type": "create_branch", "branch": "fix/style-negated_while-1", "commit_message": "start"},
                    {
                        "type": "create_pr",
                        "base": "main",
                        "head": "fix/style-negated_while-1",
                        "title": "title",
                        "body_file": "body.md",
                    },
                    {"type": "edit_pr", "pr": "{{PR_URL}}", "body_file": "body.md"},
                    {"type": "ready_pr", "pr": "{{PR_URL}}"},
                    {"type": "merge_pr", "pr": "{{PR_URL}}", "auto": True, "squash": True, "delete_branch": True},
                ]
            }
        )
    )

    loaded = repo_write._load_request(request_path)  # noqa: SLF001
    assert [operation["type"] for operation in loaded["operations"]] == [
        "ensure_labels",
        "create_branch",
        "create_pr",
        "edit_pr",
        "ready_pr",
        "merge_pr",
    ]


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


def test_close_pr_uses_repo_comment_and_delete_branch(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, cwd=None, check: bool = True):  # noqa: ANN001
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(repo_write, "_run", fake_run)

    repo_write._close_pr(  # noqa: SLF001
        "6/nitrocop",
        "https://github.com/6/nitrocop/pull/123",
        comment="Agent produced no changes.",
        delete_branch=True,
    )

    assert calls == [
        [
            "gh",
            "pr",
            "close",
            "https://github.com/6/nitrocop/pull/123",
            "--repo",
            "6/nitrocop",
            "--comment",
            "Agent produced no changes.",
            "--delete-branch",
        ]
    ]


def test_ensure_labels_uses_force_create(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, cwd=None, check: bool = True):  # noqa: ANN001
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(repo_write, "_run", fake_run)

    repo_write._ensure_labels(  # noqa: SLF001
        "6/nitrocop",
        [{"name": "type:cop-fix", "color": "0e8a16", "description": "cop fix"}],
    )

    assert calls == [
        [
            "gh",
            "label",
            "create",
            "type:cop-fix",
            "--repo",
            "6/nitrocop",
            "--color",
            "0e8a16",
            "--force",
            "--description",
            "cop fix",
        ]
    ]


def test_create_pr_sets_pr_url_context(monkeypatch, tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text("{}")
    body = tmp_path / "body.md"
    body.write_text("hello")

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, cwd=None, check: bool = True):  # noqa: ANN001
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "https://github.com/6/nitrocop/pull/123\n", "")

    monkeypatch.setattr(repo_write, "_run", fake_run)
    context = {}
    result = repo_write._create_pr(  # noqa: SLF001
        request_path,
        "6/nitrocop",
        {
            "base": "main",
            "head": "fix/style-negated_while-1",
            "title": "Fix Style/NegatedWhile",
            "body_file": "body.md",
            "draft": True,
            "labels": ["type:cop-fix", "model:claude-normal"],
        },
        context,
    )

    assert result == {"pr_url": "https://github.com/6/nitrocop/pull/123"}
    assert context["PR_URL"] == "https://github.com/6/nitrocop/pull/123"
    assert calls[0][:12] == [
        "gh",
        "pr",
        "create",
        "--repo",
        "6/nitrocop",
        "--base",
        "main",
        "--head",
        "fix/style-negated_while-1",
        "--title",
        "Fix Style/NegatedWhile",
        "--draft",
    ]


def test_execute_request_surfaces_branch_and_pr_metadata(monkeypatch, tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "match_mode": "current_head",
                "operations": [
                    {"type": "create_branch", "branch": "fix/style-foo-1", "commit_message": "start"},
                    {
                        "type": "create_pr",
                        "base": "main",
                        "head": "fix/style-foo-1",
                        "title": "Fix Style/Foo",
                        "body_file": "body.md",
                    },
                ],
            }
        )
    )
    (tmp_path / "body.md").write_text("body\n")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    monkeypatch.setattr(repo_write, "_validate_target_ref", lambda *args, **kwargs: None)

    def fake_create_branch(repo_root_arg, repo, target_sha, operation, context):  # noqa: ANN001
        context["BRANCH"] = operation["branch"]
        context["SIGNED_SHA"] = "signed123"
        context["UNSIGNED_SHA"] = "unsigned123"
        return {"signed_sha": "signed123", "unsigned_sha": "unsigned123"}

    def fake_create_pr(request_path_arg, repo, operation, context):  # noqa: ANN001
        context["PR_URL"] = "https://github.com/6/nitrocop/pull/123"
        return {"pr_url": "https://github.com/6/nitrocop/pull/123"}

    monkeypatch.setattr(repo_write, "_create_branch", fake_create_branch)
    monkeypatch.setattr(repo_write, "_create_pr", fake_create_pr)

    metadata = repo_write.execute_request(
        request_path=request_path,
        repo_root=repo_root,
        repo="6/nitrocop",
        target_ref="refs/heads/main",
        target_sha="abc123",
    )

    assert metadata["branch"] == "fix/style-foo-1"
    assert metadata["pr_url"] == "https://github.com/6/nitrocop/pull/123"
    assert metadata["signed_sha"] == "signed123"
    assert metadata["unsigned_sha"] == "unsigned123"


def test_edit_pr_renders_pr_url_from_context(monkeypatch, tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text("{}")
    body = tmp_path / "body.md"
    body.write_text("hello")

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, cwd=None, check: bool = True):  # noqa: ANN001
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(repo_write, "_run", fake_run)

    repo_write._edit_pr(  # noqa: SLF001
        request_path,
        "6/nitrocop",
        {"pr": "{{PR_URL}}", "body_file": "body.md"},
        {"PR_URL": "https://github.com/6/nitrocop/pull/123"},
    )

    assert calls[0][:6] == [
        "gh",
        "pr",
        "edit",
        "https://github.com/6/nitrocop/pull/123",
        "--repo",
        "6/nitrocop",
    ]


def test_ready_pr_uses_repo(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, cwd=None, check: bool = True):  # noqa: ANN001
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(repo_write, "_run", fake_run)

    repo_write._ready_pr("6/nitrocop", "https://github.com/6/nitrocop/pull/123")  # noqa: SLF001

    assert calls == [
        ["gh", "pr", "ready", "https://github.com/6/nitrocop/pull/123", "--repo", "6/nitrocop"]
    ]


def test_merge_pr_supports_auto_squash_delete(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, cwd=None, check: bool = True):  # noqa: ANN001
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(repo_write, "_run", fake_run)

    repo_write._merge_pr(  # noqa: SLF001
        "6/nitrocop",
        "https://github.com/6/nitrocop/pull/123",
        auto=True,
        squash=True,
        delete_branch=True,
    )

    assert calls == [
        [
            "gh",
            "pr",
            "merge",
            "https://github.com/6/nitrocop/pull/123",
            "--repo",
            "6/nitrocop",
            "--auto",
            "--squash",
            "--delete-branch",
        ]
    ]
