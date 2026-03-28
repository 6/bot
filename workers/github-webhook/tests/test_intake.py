import json

import pytest

from github_webhook.config import Settings
from github_webhook.intake import IgnoreWebhook, extract_dispatch_request


@pytest.fixture
def settings() -> Settings:
    return Settings(
        allowed_associations=("OWNER", "MEMBER", "COLLABORATOR"),
        allowed_commands=("/6bot repair", "/6bot fix"),
        allowed_repositories=("6/nitrocop",),
        bot_control_repo="6/bot",
        github_app_id="12345",
        github_app_private_key="pem",
        webhook_secret="secret",
    )


def test_extract_dispatch_request_from_pull_request_comment(settings: Settings) -> None:
    payload = {
        "action": "created",
        "repository": {"full_name": "6/nitrocop"},
        "issue": {
            "number": 42,
            "html_url": "https://github.com/6/nitrocop/pull/42",
            "pull_request": {"url": "https://api.github.com/repos/6/nitrocop/pulls/42"},
        },
        "comment": {
            "id": 99,
            "body": "/6bot repair --retry",
            "html_url": "https://github.com/6/nitrocop/pull/42#issuecomment-99",
            "author_association": "MEMBER",
        },
        "sender": {"login": "6"},
        "installation": {"id": 123},
    }

    request = extract_dispatch_request(
        event_name="issue_comment",
        delivery_id="abc123",
        payload=payload,
        settings=settings,
    )

    assert request.request_id == "webhook-abc123"
    assert request.installation_id == 123
    dispatched = json.loads(request.payload_json)
    assert dispatched["command"] == "/6bot repair"
    assert dispatched["command_args"] == "--retry"
    assert dispatched["subject_kind"] == "pull_request"
    assert dispatched["source_repo"] == "6/nitrocop"
    assert dispatched["requested_by"] == "6"


def test_extract_dispatch_request_ignores_non_allowlisted_repo(settings: Settings) -> None:
    payload = {
        "action": "created",
        "repository": {"full_name": "6/other"},
        "issue": {"number": 1, "pull_request": {"url": "x"}},
        "comment": {"id": 1, "body": "/6bot repair", "author_association": "OWNER"},
        "sender": {"login": "6"},
    }

    with pytest.raises(IgnoreWebhook, match="allowlisted"):
        extract_dispatch_request(
            event_name="issue_comment",
            delivery_id=None,
            payload=payload,
            settings=settings,
        )


def test_extract_dispatch_request_from_issue_comment(settings: Settings) -> None:
    payload = {
        "action": "created",
        "repository": {"full_name": "6/nitrocop"},
        "issue": {"number": 7, "html_url": "https://github.com/6/nitrocop/issues/7"},
        "comment": {
            "id": 1,
            "body": "/6bot fix",
            "html_url": "https://github.com/6/nitrocop/issues/7#issuecomment-1",
            "author_association": "OWNER",
        },
        "sender": {"login": "6"},
        "installation": {"id": 123},
    }

    request = extract_dispatch_request(
        event_name="issue_comment",
        delivery_id=None,
        payload=payload,
        settings=settings,
    )

    dispatched = json.loads(request.payload_json)
    assert dispatched["subject_kind"] == "issue"
    assert dispatched["issue_number"] == 7
    assert "pr_number" not in dispatched


def test_extract_dispatch_request_requires_installation(settings: Settings) -> None:
    payload = {
        "action": "created",
        "repository": {"full_name": "6/nitrocop"},
        "issue": {"number": 1, "pull_request": {"url": "x"}},
        "comment": {"id": 1, "body": "/6bot repair", "author_association": "OWNER"},
        "sender": {"login": "6"},
    }

    with pytest.raises(ValueError, match="installation.id"):
        extract_dispatch_request(
            event_name="issue_comment",
            delivery_id=None,
            payload=payload,
            settings=settings,
        )
