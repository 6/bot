import json

from github_webhook.config import Settings
from github_webhook.dispatch import build_workflow_dispatch_request
from github_webhook.intake import DispatchRequest


def test_build_workflow_dispatch_request_uses_expected_contract() -> None:
    settings = Settings(
        allowed_associations=("OWNER",),
        allowed_commands=("/6bot",),
        allowed_repositories=("6/nitrocop",),
        bot_control_repo="6/bot",
        dispatch_workflow="webhook-command.yml",
        github_api_base="https://api.github.com",
        remote_bot_workflow_token="token",
        webhook_secret="secret",
        workflow_ref="main",
    )
    request = DispatchRequest(
        request_id="webhook-123",
        source_repo="6/nitrocop",
        payload_json='{"hello":"world"}',
    )

    built = build_workflow_dispatch_request(settings, request)

    assert built.url.endswith("/repos/6/bot/actions/workflows/webhook-command.yml/dispatches")
    assert built.headers["Authorization"] == "Bearer token"
    assert json.loads(built.body) == {
        "ref": "main",
        "inputs": {
            "request_id": "webhook-123",
            "source_repo": "6/nitrocop",
            "payload": '{"hello":"world"}',
        },
    }
