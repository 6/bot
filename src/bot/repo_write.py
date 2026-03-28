#!/usr/bin/env python3
"""Execute generic write-side GitHub operations for an allowlisted source repo."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

BOT_NAME = "6[bot]"
BOT_EMAIL = "129682364+6[bot]@users.noreply.github.com"
EXTRAHEADER_KEY = "http.https://github.com/.extraheader"
MAX_OPERATIONS = 100
ALLOWED_OPERATION_TYPES = {
    "comment_pr",
    "comment_issue",
    "close_pr",
    "edit_issue_labels",
    "push_patch",
}


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=check,
    )


def _git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], cwd=repo_root, check=check)


def _gh(*args: str) -> str:
    return _run(["gh", *args]).stdout


def _gh_json(*args: str) -> dict:
    return json.loads(_gh(*args))


def _branch_from_ref(target_ref: str) -> str:
    prefix = "refs/heads/"
    if not target_ref.startswith(prefix):
        raise ValueError(f"push_patch requires a branch ref, got {target_ref}")
    return target_ref[len(prefix):]


def _resolve_request_file(request_path: Path, relative_path: str, *, field: str) -> Path:
    base = request_path.parent.resolve()
    path = (base / relative_path).resolve()
    if not path.is_relative_to(base):
        raise ValueError(f"{field} escapes request directory: {relative_path}")
    if not path.is_file():
        raise ValueError(f"{field} file not found: {relative_path}")
    return path


def _configure_git(repo_root: Path, repo: str) -> None:
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        raise ValueError("GH_TOKEN is required for repo write operations")

    _git(repo_root, "config", "user.name", BOT_NAME)
    _git(repo_root, "config", "user.email", BOT_EMAIL)
    _git(repo_root, "config", "--local", "--unset-all", EXTRAHEADER_KEY, check=False)
    remote = f"https://x-access-token:{token}@github.com/{repo}.git"
    _git(repo_root, "remote", "set-url", "origin", remote)


def _promote(repo: str, branch: str, message: str) -> dict[str, str]:
    for attempt in range(5):
        try:
            ref = _gh_json(f"repos/{repo}/git/ref/heads/{branch}")
            break
        except subprocess.CalledProcessError:
            if attempt == 4:
                raise
            time.sleep(2**attempt)
    else:
        ref = _gh_json(f"repos/{repo}/git/ref/heads/{branch}")

    unsigned_sha = ref["object"]["sha"]
    commit = _gh_json(f"repos/{repo}/git/commits/{unsigned_sha}")
    tree_sha = commit["tree"]["sha"]
    parent_shas = [parent["sha"] for parent in commit.get("parents", [])]

    create_args = [
        f"repos/{repo}/git/commits",
        "-f",
        f"message={message}",
        "-f",
        f"tree={tree_sha}",
    ]
    for parent_sha in parent_shas:
        create_args.extend(["-f", f"parents[]={parent_sha}"])

    signed = _gh_json(*create_args)
    signed_sha = signed["sha"]
    _gh(
        f"repos/{repo}/git/refs/heads/{branch}",
        "-X",
        "PATCH",
        "-f",
        f"sha={signed_sha}",
        "-F",
        "force=true",
    )

    result = {
        "unsigned_sha": unsigned_sha,
        "signed_sha": signed_sha,
        "tree_sha": tree_sha,
    }
    if parent_shas:
        result["parent_sha"] = parent_shas[0]
    return result


def _render_template(text: str, context: dict[str, str]) -> str:
    rendered = text
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _load_request(request_path: Path) -> dict:
    data = json.loads(request_path.read_text())
    if not isinstance(data, dict):
        raise ValueError("request must be a JSON object")

    operations = data.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError("request.operations must be a non-empty list")
    if len(operations) > MAX_OPERATIONS:
        raise ValueError(f"too many operations ({len(operations)} > {MAX_OPERATIONS})")

    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise ValueError(f"operation #{index + 1} must be a JSON object")
        op_type = operation.get("type")
        if op_type not in ALLOWED_OPERATION_TYPES:
            raise ValueError(f"operation #{index + 1} has unknown type: {op_type}")

    match_mode = data.get("match_mode", "current_head")
    if match_mode not in {"current_head", "contained"}:
        raise ValueError(f"unknown match_mode: {match_mode}")
    data["match_mode"] = match_mode
    return data


def _validate_target_ref(repo_root: Path, target_ref: str, target_sha: str, match_mode: str) -> None:
    _git(repo_root, "fetch", "--no-tags", "origin", target_ref)
    fetched_sha = _git(repo_root, "rev-parse", "FETCH_HEAD").stdout.strip()

    if match_mode == "current_head":
        if fetched_sha != target_sha:
            raise ValueError(f"{target_ref} moved to {fetched_sha}; expected {target_sha}")
        return

    ancestor = _git(repo_root, "merge-base", "--is-ancestor", target_sha, "FETCH_HEAD", check=False)
    if ancestor.returncode != 0:
        raise ValueError(f"{target_sha} is not contained in {target_ref}")


def _body_from_file(request_path: Path, relative_path: str, context: dict[str, str]) -> str:
    path = _resolve_request_file(request_path, relative_path, field="body_file")
    return _render_template(path.read_text(), context)


def _has_worktree_changes(repo_root: Path) -> bool:
    return bool(_git(repo_root, "status", "--porcelain").stdout.strip())


def _comment_pr(repo: str, pr_number: int, body: str) -> None:
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        handle.write(body)
        temp_path = handle.name
    try:
        _run(["gh", "pr", "comment", str(pr_number), "--repo", repo, "--body-file", temp_path])
    finally:
        Path(temp_path).unlink(missing_ok=True)


def _comment_issue(repo: str, issue_number: int, body: str) -> None:
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        handle.write(body)
        temp_path = handle.name
    try:
        _run(["gh", "issue", "comment", str(issue_number), "--repo", repo, "--body-file", temp_path])
    finally:
        Path(temp_path).unlink(missing_ok=True)


def _close_pr(repo: str, pr_target: str, *, comment: str = "", delete_branch: bool = False) -> None:
    cmd = ["gh", "pr", "close", pr_target, "--repo", repo]
    if comment:
        cmd.extend(["--comment", comment])
    if delete_branch:
        cmd.append("--delete-branch")
    _run(cmd)


def _edit_issue_labels(repo: str, issue_number: int, operation: dict) -> None:
    cmd = ["gh", "issue", "edit", str(issue_number), "--repo", repo]
    add_labels = operation.get("add_labels", [])
    remove_labels = operation.get("remove_labels", [])
    if add_labels:
        cmd.extend(["--add-label", ",".join(add_labels)])
    if remove_labels:
        cmd.extend(["--remove-label", ",".join(remove_labels)])
    _run(cmd, check=not operation.get("ignore_failure", False))


def _push_patch(
    repo_root: Path,
    repo: str,
    target_ref: str,
    request_path: Path,
    operation: dict,
    context: dict[str, str],
) -> dict[str, str]:
    patch_file = _resolve_request_file(request_path, operation["patch_file"], field="patch_file")
    _configure_git(repo_root, repo)
    _git(repo_root, "apply", "--binary", str(patch_file))

    if not _has_worktree_changes(repo_root):
        return {"pushed": "false"}

    commit_message = operation["commit_message"]
    promote_message = operation.get("promote_message") or commit_message
    branch = _branch_from_ref(target_ref)

    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-m", commit_message)
    _git(repo_root, "push", "origin", f"HEAD:{branch}", "--force")

    promotion = _promote(repo, branch, promote_message)
    context["UNSIGNED_SHA"] = promotion["unsigned_sha"]
    context["SIGNED_SHA"] = promotion["signed_sha"]
    return {"pushed": "true", **promotion}


def execute_request(
    *,
    request_path: Path,
    repo_root: Path,
    repo: str,
    target_ref: str,
    target_sha: str,
) -> dict[str, object]:
    request = _load_request(request_path)
    context = {
        "TARGET_REF": target_ref,
        "TARGET_SHA": target_sha,
    }

    _validate_target_ref(repo_root, target_ref, target_sha, request["match_mode"])

    results: list[dict[str, object]] = []
    for operation in request["operations"]:
        op_type = operation["type"]
        if op_type == "push_patch":
            result = _push_patch(repo_root, repo, target_ref, request_path, operation, context)
        elif op_type == "comment_pr":
            body = _body_from_file(request_path, operation["body_file"], context)
            _comment_pr(repo, int(operation["pr_number"]), body)
            result = {"posted": "true"}
        elif op_type == "comment_issue":
            body = _body_from_file(request_path, operation["body_file"], context)
            _comment_issue(repo, int(operation["issue_number"]), body)
            result = {"posted": "true"}
        elif op_type == "close_pr":
            comment = ""
            if "comment_file" in operation:
                comment = _body_from_file(request_path, operation["comment_file"], context)
            elif "comment" in operation:
                comment = _render_template(str(operation["comment"]), context)
            pr_target = str(operation.get("pr") or operation.get("pr_url") or operation.get("pr_number") or "")
            if not pr_target:
                raise ValueError("close_pr requires pr, pr_url, or pr_number")
            _close_pr(
                repo,
                pr_target,
                comment=comment,
                delete_branch=bool(operation.get("delete_branch", False)),
            )
            result = {"closed": "true"}
        elif op_type == "edit_issue_labels":
            _edit_issue_labels(repo, int(operation["issue_number"]), operation)
            result = {"edited": "true"}
        else:
            raise ValueError(f"unsupported operation type: {op_type}")

        results.append({"type": op_type, **result})

    metadata: dict[str, object] = {
        "repo": repo,
        "target_ref": target_ref,
        "target_sha": target_sha,
        "operations": results,
    }
    if "SIGNED_SHA" in context:
        metadata["signed_sha"] = context["SIGNED_SHA"]
    if "UNSIGNED_SHA" in context:
        metadata["unsigned_sha"] = context["UNSIGNED_SHA"]
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    execute = subparsers.add_parser("execute")
    execute.add_argument("--request-file", type=Path, required=True)
    execute.add_argument("--repo-root", type=Path, required=True)
    execute.add_argument("--repo", required=True)
    execute.add_argument("--target-ref", required=True)
    execute.add_argument("--target-sha", required=True)
    execute.add_argument("--metadata-file", type=Path, required=True)

    args = parser.parse_args()

    if args.command == "execute":
        metadata = execute_request(
            request_path=args.request_file.resolve(),
            repo_root=args.repo_root.resolve(),
            repo=args.repo,
            target_ref=args.target_ref,
            target_sha=args.target_sha,
        )
        args.metadata_file.write_text(json.dumps(metadata, indent=2) + "\n")
        for key in ("signed_sha", "unsigned_sha"):
            if key in metadata:
                print(f"{key}={metadata[key]}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
