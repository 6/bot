from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        text=True,
        capture_output=True,
        check=check,
    )
    return result.stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Test Bot")
    git(repo, "config", "user.email", "test@example.com")
    (repo / "file.txt").write_text("one\n")
    git(repo, "add", "file.txt")
    git(repo, "commit", "-m", "init")
    return repo


def run_capture(repo: Path, output: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "bot.git_activity_snapshot",
            "capture",
            "--repo-root",
            str(repo),
            "--output",
            str(output),
        ],
        cwd=str(repo),
        text=True,
        capture_output=True,
        check=True,
    )


def run_report(before: Path, after: Path, out_dir: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "bot.git_activity_snapshot",
            "report",
            "--before",
            str(before),
            "--after",
            str(after),
            "--out-dir",
            str(out_dir),
        ],
        text=True,
        capture_output=True,
        check=True,
    )


def test_capture_records_main_worktree_and_refs(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    output = repo / "snapshot.json"
    run_capture(repo, output)

    snapshot = json.loads(output.read_text())
    assert snapshot["head"]
    assert snapshot["head_ref"]
    assert snapshot["refs"][snapshot["head_ref"]] == snapshot["head"]
    assert any(item["path"] == str(repo.resolve()) for item in snapshot["worktrees"])


def test_report_captures_extra_worktree_and_branch_artifacts(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    before = repo / "before.json"
    after = repo / "after.json"
    out_dir = repo / "artifacts"
    run_capture(repo, before)

    git(repo, "branch", "side")
    worktree_dir = tmp_path / "side-worktree"
    git(repo, "worktree", "add", str(worktree_dir), "side")
    (worktree_dir / "file.txt").write_text("one\ntwo\n")
    git(worktree_dir, "add", "file.txt")
    git(worktree_dir, "commit", "-m", "side change")

    run_capture(repo, after)
    run_report(before, after, out_dir)

    report = (out_dir / "report.md").read_text()
    assert "## Extra Local Refs" in report
    assert "refs/heads/side" in report
    assert "## Extra Worktrees" in report
    assert str(worktree_dir) in report

    artifact_files = {path.name for path in out_dir.iterdir()}
    assert "report.json" in artifact_files
    assert "report.md" in artifact_files
    assert any(name.startswith("ref-side") for name in artifact_files)
    assert any(name.startswith("worktree_") for name in artifact_files)
