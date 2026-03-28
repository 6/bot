from __future__ import annotations

import json
from dataclasses import dataclass

from github_webhook.config import DISPATCH_WORKFLOW, GITHUB_API_BASE, Settings, WORKFLOW_REF
from github_webhook.intake import DispatchRequest


@dataclass(frozen=True)
class WorkflowDispatchRequest:
    url: str
    headers: dict[str, str]
    body: str


def build_workflow_dispatch_request(
    settings: Settings, request: DispatchRequest, *, access_token: str
) -> WorkflowDispatchRequest:
    body = json.dumps(
        {
            "ref": WORKFLOW_REF,
            "inputs": {
                "request_id": request.request_id,
                "source_repo": request.source_repo,
                "payload": request.payload_json,
            },
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "6-bot-github-webhook",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    return WorkflowDispatchRequest(
        url=(
            f"{GITHUB_API_BASE}/repos/{settings.bot_control_repo}/actions/workflows/"
            f"{DISPATCH_WORKFLOW}/dispatches"
        ),
        headers=headers,
        body=body,
    )
