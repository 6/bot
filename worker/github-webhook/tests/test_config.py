import pytest

from github_webhook.config import load_settings


def test_load_settings_reads_csv_fields() -> None:
    settings = load_settings(
        {
            "BOT_CONTROL_REPO": "6/bot",
            "DISPATCH_WORKFLOW": "webhook-command.yml",
            "WORKFLOW_REF": "main",
            "GITHUB_API_BASE": "https://api.github.com",
            "ALLOWED_REPOSITORIES": "6/nitrocop,6/another",
            "ALLOWED_ASSOCIATIONS": "owner,member",
            "ALLOWED_COMMANDS": "/6bot repair,/6bot fix",
            "GITHUB_WEBHOOK_SECRET": "secret",
            "REMOTE_BOT_WORKFLOW_TOKEN": "token",
        }
    )

    assert settings.allowed_repositories == ("6/nitrocop", "6/another")
    assert settings.allowed_associations == ("OWNER", "MEMBER")
    assert settings.allowed_commands == ("/6bot repair", "/6bot fix")


def test_load_settings_requires_secrets() -> None:
    with pytest.raises(ValueError, match="GITHUB_WEBHOOK_SECRET"):
        load_settings({})
