from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

GITHUB_API_BASE = "https://api.github.com"


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
    github_app_id: str
    github_app_private_key: str
    webhook_secret: str
    workflow_ref: str


def load_settings(env: object) -> Settings:
    required = {
        "BOT_CONTROL_REPO": _read_env(env, "BOT_CONTROL_REPO"),
        "DISPATCH_WORKFLOW": _read_env(env, "DISPATCH_WORKFLOW"),
        "WORKFLOW_REF": _read_env(env, "WORKFLOW_REF"),
        "GH_APP_ID": _read_env(env, "GH_APP_ID"),
        "GH_APP_PRIVATE_KEY": _read_env(env, "GH_APP_PRIVATE_KEY"),
        "ALLOWED_REPOSITORIES": _read_env(env, "ALLOWED_REPOSITORIES"),
        "ALLOWED_ASSOCIATIONS": _read_env(env, "ALLOWED_ASSOCIATIONS"),
        "ALLOWED_COMMANDS": _read_env(env, "ALLOWED_COMMANDS"),
        "GITHUB_WEBHOOK_SECRET": _read_env(env, "GITHUB_WEBHOOK_SECRET"),
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
        github_app_id=required["GH_APP_ID"] or "",
        github_app_private_key=required["GH_APP_PRIVATE_KEY"] or "",
        webhook_secret=required["GITHUB_WEBHOOK_SECRET"] or "",
        workflow_ref=required["WORKFLOW_REF"] or "",
    )
