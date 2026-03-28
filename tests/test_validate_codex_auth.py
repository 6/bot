from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone


def iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def make_jwt(exp_delta_seconds: int) -> str:
    header = {"alg": "none", "typ": "JWT"}
    payload = {
        "sub": "test-user",
        "exp": int((datetime.now(timezone.utc) + timedelta(seconds=exp_delta_seconds)).timestamp()),
    }

    def encode(data: dict) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{encode(header)}.{encode(payload)}.signature"


def run(payload: dict | None = None, max_age_days: int = 7) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if payload is None:
        env.pop("CODEX_AUTH_JSON", None)
    else:
        env["CODEX_AUTH_JSON"] = json.dumps(payload)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "bot.validate_codex_auth",
            "--max-age-days",
            str(max_age_days),
        ],
        capture_output=True,
        text=True,
        env=env,
    )


def test_accepts_managed_auth() -> None:
    result = run(
        {
            "OPENAI_API_KEY": None,
            "tokens": {
                "access_token": "eyJ-access",
                "refresh_token": "rt-refresh",
                "id_token": "eyJ-id",
                "account_id": "e7-account",
            },
            "last_refresh": iso_days_ago(1),
        }
    )

    assert result.returncode == 0
    assert "managed auth payload" in result.stdout
    assert "account_id present" in result.stdout


def test_accepts_api_key_auth() -> None:
    result = run(
        {
            "OPENAI_API_KEY": "sk-test",
            "tokens": None,
            "last_refresh": None,
        }
    )

    assert result.returncode == 0
    assert "API key auth payload" in result.stdout


def test_rejects_missing_secret() -> None:
    result = run(None)
    assert result.returncode != 0
    assert "missing or empty" in result.stderr


def test_rejects_invalid_shape() -> None:
    result = run(
        {
            "OPENAI_API_KEY": None,
            "tokens": {
                "access_token": "",
                "refresh_token": "rt-refresh",
            },
        }
    )

    assert result.returncode != 0
    assert "tokens.access_token is missing or empty" in result.stderr


def test_warns_on_missing_account_id() -> None:
    result = run(
        {
            "OPENAI_API_KEY": None,
            "tokens": {
                "access_token": "eyJ-access",
                "refresh_token": "rt-refresh",
            },
            "last_refresh": iso_days_ago(1),
        }
    )

    assert result.returncode == 0
    assert "WARNING: tokens.account_id is missing or empty" in result.stderr


def test_rejects_missing_last_refresh() -> None:
    result = run(
        {
            "OPENAI_API_KEY": None,
            "tokens": {
                "access_token": "eyJ-access",
                "refresh_token": "rt-refresh",
                "account_id": "e7-account",
            },
        }
    )

    assert result.returncode != 0
    assert "last_refresh is missing or empty" in result.stderr


def test_rejects_stale_last_refresh() -> None:
    result = run(
        {
            "OPENAI_API_KEY": None,
            "tokens": {
                "access_token": "eyJ-access",
                "refresh_token": "rt-refresh",
                "account_id": "e7-account",
            },
            "last_refresh": iso_days_ago(9),
        }
    )

    assert result.returncode != 0
    assert "last_refresh is stale" in result.stderr


def test_rejects_expired_access_token() -> None:
    result = run(
        {
            "OPENAI_API_KEY": None,
            "tokens": {
                "access_token": make_jwt(-60),
                "refresh_token": "rt-refresh",
                "account_id": "e7-account",
            },
            "last_refresh": iso_days_ago(1),
        }
    )

    assert result.returncode != 0
    assert "tokens.access_token appears expired" in result.stderr
