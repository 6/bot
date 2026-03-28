from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from github_webhook.config import Settings
from github_webhook.triggers import parse_bot_mention

AUTOMATION_ACTORS = {"github-actions[bot]"}


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


def _extract_common_fields(
    *,
    payload: dict[str, Any],
    settings: Settings,
) -> tuple[str, str, dict[str, Any], int, int, str, str]:
    repository = _require_mapping(payload.get("repository"), field="repository")
    source_repo = str(repository.get("full_name", "")).strip()
    if not source_repo:
        raise ValueError("repository.full_name is required")
    if source_repo not in settings.allowed_repositories:
        raise IgnoreWebhook(f"repository is not allowlisted: {source_repo}")

    source_owner, _, _ = source_repo.partition("/")

    issue = _require_mapping(payload.get("issue"), field="issue")
    issue_number = issue.get("number")
    if issue_number is None:
        raise ValueError("issue.number is required")
    if not isinstance(issue_number, int):
        raise ValueError("issue.number must be an integer")

    sender = _require_mapping(payload.get("sender"), field="sender")
    requested_by = str(sender.get("login", "")).strip()
    if not requested_by:
        raise ValueError("sender.login is required")

    installation = payload.get("installation") or {}
    installation_id = installation.get("id")
    if not isinstance(installation_id, int):
        raise ValueError("installation.id is required")

    issue_url = str(issue.get("html_url", "")).strip()

    return (
        source_repo,
        source_owner,
        issue,
        issue_number,
        installation_id,
        requested_by,
        issue_url,
    )


def _extract_comment_request(
    *,
    action: str,
    delivery_id: str | None,
    payload: dict[str, Any],
    settings: Settings,
) -> DispatchRequest:
    if action not in {"created", "edited"}:
        raise IgnoreWebhook(f"unsupported issue_comment action: {action}")

    (
        source_repo,
        source_owner,
        issue,
        issue_number,
        installation_id,
        requested_by,
        issue_url,
    ) = _extract_common_fields(payload=payload, settings=settings)

    subject_kind = "pull_request" if "pull_request" in issue else "issue"

    comment = _require_mapping(payload.get("comment"), field="comment")
    comment_body = str(comment.get("body", ""))
    mention = parse_bot_mention(comment_body, bot_login=source_owner)
    if mention is None:
        raise IgnoreWebhook("comment does not begin with a bot mention trigger")

    association = str(comment.get("author_association", "")).upper()
    if requested_by not in AUTOMATION_ACTORS and association not in settings.allowed_associations:
        raise IgnoreWebhook(
            f"comment author association is not allowed: {association or 'UNKNOWN'}"
        )

    comment_id = comment.get("id")
    if comment_id is None:
        raise ValueError("comment.id is required")
    if not isinstance(comment_id, int):
        raise ValueError("comment.id must be an integer")

    request_id = (
        f"webhook-{delivery_id}"
        if delivery_id
        else f"webhook-comment-{comment_id}"
    )

    request_payload = {
        "request_id": request_id,
        "source_repo": source_repo,
        "event_name": "issue_comment",
        "event_action": action,
        "delivery_id": delivery_id or "",
        "installation_id": installation_id,
        "requested_by": requested_by,
        "requested_by_association": association,
        "trigger_kind": "mention",
        "subject_kind": subject_kind,
        "prompt_text": mention.prompt,
        "request_url": str(comment.get("html_url", "")).strip(),
        "issue_number": issue_number,
        "issue_url": issue_url,
    }
    if subject_kind == "pull_request":
        request_payload["pr_number"] = issue_number

    return DispatchRequest(
        installation_id=installation_id,
        request_id=request_id,
        source_repo=source_repo,
        payload_json=json.dumps(request_payload, separators=(",", ":"), sort_keys=True),
    )


def _extract_issue_assignment_request(
    *,
    action: str,
    delivery_id: str | None,
    payload: dict[str, Any],
    settings: Settings,
) -> DispatchRequest:
    if action != "assigned":
        raise IgnoreWebhook(f"unsupported issues action: {action}")

    (
        source_repo,
        source_owner,
        issue,
        issue_number,
        installation_id,
        requested_by,
        issue_url,
    ) = _extract_common_fields(payload=payload, settings=settings)

    if "pull_request" in issue:
        raise IgnoreWebhook("pull request assignments are not handled by the webhook")

    assignee = _require_mapping(payload.get("assignee"), field="assignee")
    assigned_to = str(assignee.get("login", "")).strip()
    if not assigned_to:
        raise ValueError("assignee.login is required")
    if assigned_to != source_owner:
        raise IgnoreWebhook("issue assignment trigger requires assignment to the repo owner")
    if requested_by not in {source_owner, *AUTOMATION_ACTORS}:
        raise IgnoreWebhook(
            "issue assignment trigger requires self-assignment to the repo owner"
        )

    request_id = (
        f"webhook-{delivery_id}"
        if delivery_id
        else f"webhook-assignment-{issue_number}"
    )

    request_payload = {
        "request_id": request_id,
        "source_repo": source_repo,
        "event_name": "issues",
        "event_action": action,
        "delivery_id": delivery_id or "",
        "installation_id": installation_id,
        "requested_by": requested_by,
        "requested_by_association": "OWNER",
        "trigger_kind": "assignment",
        "subject_kind": "issue",
        "prompt_text": "",
        "request_url": issue_url,
        "issue_number": issue_number,
        "issue_url": issue_url,
        "issue_title": str(issue.get("title", "")).strip(),
        "issue_body": str(issue.get("body", "")),
        "assigned_to": assigned_to,
    }

    return DispatchRequest(
        installation_id=installation_id,
        request_id=request_id,
        source_repo=source_repo,
        payload_json=json.dumps(request_payload, separators=(",", ":"), sort_keys=True),
    )


def extract_dispatch_request(
    *,
    event_name: str,
    delivery_id: str | None,
    payload: dict[str, Any],
    settings: Settings,
) -> DispatchRequest:
    action = str(payload.get("action", "")).strip()
    if event_name == "issue_comment":
        return _extract_comment_request(
            action=action,
            delivery_id=delivery_id,
            payload=payload,
            settings=settings,
        )
    if event_name == "issues":
        return _extract_issue_assignment_request(
            action=action,
            delivery_id=delivery_id,
            payload=payload,
            settings=settings,
        )
    raise IgnoreWebhook(f"unsupported event: {event_name}")
