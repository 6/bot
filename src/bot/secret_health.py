#!/usr/bin/env python3
"""Validate the 6/bot secret set without leaking secret values."""

from __future__ import annotations

import argparse
import json
import os
import sys

from bot.validate_codex_auth import validate_auth

REQUIRED_STRING_SECRETS = (
    "MINIMAX_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
)
OPTIONAL_STRING_SECRETS = (
    "ANTHROPIC_API_KEY",
)


def _fail(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1


def _warn(msg: str) -> None:
    print(f"WARNING: {msg}", file=sys.stderr)


def _require_nonempty(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise ValueError(f"{name} is missing or empty")
    return value


def _load_json_env(name: str) -> dict:
    raw = _require_nonempty(name)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{name} must decode to a JSON object")
    return data


def validate_secret_health(max_codex_age_days: int) -> None:
    for name in REQUIRED_STRING_SECRETS:
        _require_nonempty(name)
        print(f"Validated required secret presence: {name}")

    gh_app_id = _require_nonempty("GH_APP_ID")
    try:
        if int(gh_app_id) <= 0:
            raise ValueError
    except ValueError as exc:
        raise ValueError("GH_APP_ID must be a positive integer") from exc

    gh_app_private_key = _require_nonempty("GH_APP_PRIVATE_KEY")
    if "BEGIN" not in gh_app_private_key or "PRIVATE KEY" not in gh_app_private_key or "END" not in gh_app_private_key:
        raise ValueError("GH_APP_PRIVATE_KEY does not look like a PEM private key")
    print("Validated GitHub App credentials: GH_APP_ID, GH_APP_PRIVATE_KEY")

    for name in OPTIONAL_STRING_SECRETS:
        if os.environ.get(name, "").strip():
            print(f"Validated optional secret presence: {name}")
        else:
            _warn(f"Optional secret is missing or empty: {name}")

    mode = validate_auth(_load_json_env("CODEX_AUTH_JSON"), max_codex_age_days)
    print(f"Validated Codex auth secret: {mode}")
    print("Secret health check passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-codex-age-days",
        type=int,
        default=7,
        help="Maximum allowed age for CODEX_AUTH_JSON last_refresh (default: 7 days)",
    )
    args = parser.parse_args()

    try:
        validate_secret_health(args.max_codex_age_days)
    except ValueError as exc:
        return _fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
