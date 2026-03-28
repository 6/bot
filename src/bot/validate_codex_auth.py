#!/usr/bin/env python3
"""Validate a Codex auth secret without leaking sensitive token values.

This is intentionally permissive. It validates the fields the current Codex
workflow depends on while allowing the serialized auth.json shape to evolve
across CLI versions.
"""

import argparse
import base64
import binascii
import json
import os
import sys
from datetime import datetime, timedelta, timezone


def _fail(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1


def _warn(msg: str) -> None:
    print(f"WARNING: {msg}", file=sys.stderr)


def _nonempty_string(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _parse_timestamp(raw: str) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("last_refresh is missing or empty")

    normalized = raw.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"last_refresh is not a valid ISO-8601 timestamp: {raw}") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_access_token_expiry(raw: str) -> datetime | None:
    if not _nonempty_string(raw):
        return None

    parts = raw.strip().split(".")
    if len(parts) != 3:
        return None

    payload = parts[1]
    payload += "=" * (-len(payload) % 4)

    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        claims = json.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None

    exp = claims.get("exp")
    if exp is None:
        return None
    if not isinstance(exp, (int, float)):
        raise ValueError("tokens.access_token exp claim is not numeric")

    return datetime.fromtimestamp(exp, tz=timezone.utc)


def _load_env(var_name: str):
    raw = os.environ.get(var_name, "")
    if not raw.strip():
        raise ValueError(f"{var_name} is missing or empty")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{var_name} is not valid JSON: {exc}") from exc


def validate_auth(data: dict, max_age_days: int) -> str:
    if not isinstance(data, dict):
        raise ValueError("auth payload must be a JSON object")

    api_key = data.get("OPENAI_API_KEY")
    tokens = data.get("tokens")
    last_refresh = data.get("last_refresh")

    if _nonempty_string(api_key):
        if last_refresh is not None and not isinstance(last_refresh, str):
            _warn("last_refresh is present but not a string")
        return "api_key"

    if not isinstance(tokens, dict):
        raise ValueError("expected tokens object for managed ChatGPT auth")

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    account_id = tokens.get("account_id")

    if not _nonempty_string(access_token):
        raise ValueError("tokens.access_token is missing or empty")
    if not _nonempty_string(refresh_token):
        raise ValueError("tokens.refresh_token is missing or empty")
    if not _nonempty_string(account_id):
        _warn("tokens.account_id is missing or empty")

    now = datetime.now(timezone.utc)
    expires_at = _parse_access_token_expiry(access_token)
    if expires_at is not None:
        if now >= expires_at:
            raise ValueError(f"tokens.access_token appears expired at {_format_timestamp(expires_at)}")
        if expires_at - now <= timedelta(hours=1):
            _warn(f"tokens.access_token expires soon at {_format_timestamp(expires_at)}")

    refreshed_at = _parse_timestamp(last_refresh)
    age = now - refreshed_at
    max_age = timedelta(days=max_age_days)
    if age > max_age:
        age_days = age.total_seconds() / 86400
        raise ValueError(
            f"last_refresh is stale ({age_days:.1f} days old; limit is {max_age_days} days)"
        )

    return "chatgpt"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from-env",
        default="CODEX_AUTH_JSON",
        help="Environment variable holding the auth JSON (default: CODEX_AUTH_JSON)",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=7,
        help="Maximum allowed age for managed-auth last_refresh (default: 7 days)",
    )
    args = parser.parse_args()

    try:
        data = _load_env(args.from_env)
        mode = validate_auth(data, args.max_age_days)
    except ValueError as exc:
        return _fail(str(exc))

    if mode == "api_key":
        print("Codex auth secret validated: API key auth payload")
    else:
        account_id = data.get("tokens", {}).get("account_id", "")
        last_refresh = data.get("last_refresh", "(missing)")
        account_status = "account_id present" if _nonempty_string(account_id) else "account_id missing"
        print(
            "Codex auth secret validated: managed auth payload "
            f"({account_status}, last_refresh={last_refresh})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
