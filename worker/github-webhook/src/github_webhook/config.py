from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


def _read_env(env: object, name: str) -> str | None:
    if isinstance(env, Mapping):
        value = env.get(name)
    else:
        value = getattr(env, name, None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    allowed_associations: tuple[str, ...]
    allowed_commands: tuple[str, ...]
    allowed_repositories: tuple[str, ...]
    bot_control_repo: str
    dispatch_workflow: str
    github_api_base: str
    remote_bot_workflow_token: str
    webhook_secret: str
    workflow_ref: str


def load_settings(env: object) -> Settings:
    required = {
        "BOT_CONTROL_REPO": _read_env(env, "BOT_CONTROL_REPO"),
        "DISPATCH_WORKFLOW": _read_env(env, "DISPATCH_WORKFLOW"),
        "WORKFLOW_REF": _read_env(env, "WORKFLOW_REF"),
        "GITHUB_API_BASE": _read_env(env, "GITHUB_API_BASE"),
        "ALLOWED_REPOSITORIES": _read_env(env, "ALLOWED_REPOSITORIES"),
        "ALLOWED_ASSOCIATIONS": _read_env(env, "ALLOWED_ASSOCIATIONS"),
        "ALLOWED_COMMANDS": _read_env(env, "ALLOWED_COMMANDS"),
        "GITHUB_WEBHOOK_SECRET": _read_env(env, "GITHUB_WEBHOOK_SECRET"),
        "REMOTE_BOT_WORKFLOW_TOKEN": _read_env(env, "REMOTE_BOT_WORKFLOW_TOKEN"),
    }
    missing = sorted(name for name, value in required.items() if value is None)
    if missing:
        raise ValueError(f"missing required worker configuration: {', '.join(missing)}")

    return Settings(
        allowed_associations=tuple(
            value.upper() for value in _split_csv(required["ALLOWED_ASSOCIATIONS"] or "")
        ),
        allowed_commands=_split_csv(required["ALLOWED_COMMANDS"] or ""),
        allowed_repositories=_split_csv(required["ALLOWED_REPOSITORIES"] or ""),
        bot_control_repo=required["BOT_CONTROL_REPO"] or "",
        dispatch_workflow=required["DISPATCH_WORKFLOW"] or "",
        github_api_base=required["GITHUB_API_BASE"] or "",
        remote_bot_workflow_token=required["REMOTE_BOT_WORKFLOW_TOKEN"] or "",
        webhook_secret=required["GITHUB_WEBHOOK_SECRET"] or "",
        workflow_ref=required["WORKFLOW_REF"] or "",
    )
