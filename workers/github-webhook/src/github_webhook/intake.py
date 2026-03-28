from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from github_webhook.commands import parse_command
from github_webhook.config import Settings


class IgnoreWebhook(ValueError):
    """Raised when a valid webhook should be ignored without retrying."""


@dataclass(frozen=True)
class DispatchRequest:
    installation_id: int
    request_id: str
    source_repo: str
    payload_json: str


def _require_mapping(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def extract_dispatch_request(
    *,
    event_name: str,
    delivery_id: str | None,
    payload: dict[str, Any],
    settings: Settings,
) -> DispatchRequest:
    if event_name != "issue_comment":
        raise IgnoreWebhook(f"unsupported event: {event_name}")

    action = str(payload.get("action", "")).strip()
    if action not in {"created", "edited"}:
        raise IgnoreWebhook(f"unsupported issue_comment action: {action}")

    repository = _require_mapping(payload.get("repository"), field="repository")
    source_repo = str(repository.get("full_name", "")).strip()
    if not source_repo:
        raise ValueError("repository.full_name is required")
    if source_repo not in settings.allowed_repositories:
        raise IgnoreWebhook(f"repository is not allowlisted: {source_repo}")

    issue = _require_mapping(payload.get("issue"), field="issue")
    subject_kind = "pull_request" if "pull_request" in issue else "issue"

    comment = _require_mapping(payload.get("comment"), field="comment")
    comment_body = str(comment.get("body", ""))
    command = parse_command(comment_body, settings.allowed_commands)
    if command is None:
        raise IgnoreWebhook("comment does not contain a supported command")

    association = str(comment.get("author_association", "")).upper()
    if association not in settings.allowed_associations:
        raise IgnoreWebhook(
            f"comment author association is not allowed: {association or 'UNKNOWN'}"
        )

    sender = _require_mapping(payload.get("sender"), field="sender")
    requested_by = str(sender.get("login", "")).strip()
    if not requested_by:
        raise ValueError("sender.login is required")

    comment_id = comment.get("id")
    issue_number = issue.get("number")
    if comment_id is None:
        raise ValueError("comment.id is required")
    if issue_number is None:
        raise ValueError("issue.number is required")

    installation = payload.get("installation") or {}
    installation_id = installation.get("id")
    if not isinstance(installation_id, int):
        raise ValueError("installation.id is required")

    request_id = (
        f"webhook-{delivery_id}"
        if delivery_id
        else f"webhook-comment-{comment_id}"
    )

    request_payload = {
        "request_id": request_id,
        "source_repo": source_repo,
        "event_name": event_name,
        "event_action": action,
        "delivery_id": delivery_id or "",
        "installation_id": installation_id,
        "requested_by": requested_by,
        "requested_by_association": association,
        "command": command.name,
        "command_args": command.args,
        "subject_kind": subject_kind,
        "comment_id": comment_id,
        "comment_body": comment_body,
        "comment_url": comment.get("html_url", ""),
        "issue_number": issue_number,
        "issue_url": issue.get("html_url", ""),
    }
    if subject_kind == "pull_request":
        request_payload["pr_number"] = issue_number

    return DispatchRequest(
        installation_id=installation_id,
        request_id=request_id,
        source_repo=source_repo,
        payload_json=json.dumps(request_payload, separators=(",", ":"), sort_keys=True),
    )
