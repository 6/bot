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


def codex_payload(exp_delta_seconds: int = 3600) -> dict:
    return {
        "OPENAI_API_KEY": None,
        "tokens": {
            "access_token": make_jwt(exp_delta_seconds),
            "refresh_token": "rt-refresh",
            "id_token": "eyJ-id",
            "account_id": "acct-123",
        },
        "last_refresh": iso_days_ago(1),
    }


def run(extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "MINIMAX_API_KEY": "minimax-test",
            "CODEX_AUTH_JSON": json.dumps(codex_payload()),
            "CLAUDE_CODE_OAUTH_TOKEN": "claude-oauth-test",
            "GH_APP_ID": "12345",
            "GH_APP_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----",
        }
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "bot.secret_health"],
        capture_output=True,
        text=True,
        env=env,
    )


def test_secret_health_accepts_required_secrets() -> None:
    result = run()

    assert result.returncode == 0
    assert "Validated required secret presence: MINIMAX_API_KEY" in result.stdout
    assert "Validated Codex auth secret" in result.stdout
    assert "Secret health check passed" in result.stdout


def test_secret_health_rejects_missing_required_secret() -> None:
    result = run({"MINIMAX_API_KEY": ""})

    assert result.returncode != 0
    assert "MINIMAX_API_KEY is missing or empty" in result.stderr


def test_secret_health_rejects_invalid_github_app_id() -> None:
    result = run({"GH_APP_ID": "not-a-number"})

    assert result.returncode != 0
    assert "GH_APP_ID must be a positive integer" in result.stderr
