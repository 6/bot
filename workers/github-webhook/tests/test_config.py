import pytest

from github_webhook.config import load_settings


def test_load_settings_reads_csv_fields() -> None:
    settings = load_settings(
        {
            "BOT_CONTROL_REPO": "6/bot",
            "GH_APP_ID": "12345",
            "GH_APP_PRIVATE_KEY": "pem",
            "ALLOWED_REPOSITORIES": "6/nitrocop,6/another",
            "ALLOWED_ASSOCIATIONS": "owner,member",
            "ALLOWED_COMMANDS": "/6bot repair,/6bot fix",
            "GITHUB_WEBHOOK_SECRET": "secret",
        }
    )

    assert settings.allowed_repositories == ("6/nitrocop", "6/another")
    assert settings.allowed_associations == ("OWNER", "MEMBER")
    assert settings.allowed_commands == ("/6bot repair", "/6bot fix")
    assert settings.github_app_id == "12345"


def test_load_settings_requires_secrets() -> None:
    with pytest.raises(ValueError, match="GH_APP_ID"):
        load_settings({})
