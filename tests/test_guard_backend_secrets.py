from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def managed_auth_payload() -> dict:
    return {
        "OPENAI_API_KEY": None,
        "tokens": {
            "access_token": "eyJ-access",
            "refresh_token": "rt-refresh",
            "id_token": "eyJ-id",
            "account_id": "e7-account",
        },
        "last_refresh": "2026-03-22T00:00:00Z",
    }


def run(args: list[str], env_vars: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("CODEX_AUTH_JSON", None)
    env.pop("MINIMAX_API_KEY", None)
    env.pop("ANTHROPIC_API_KEY", None)
    if env_vars:
        env.update(env_vars)
    return subprocess.run(
        ["python", "-m", "bot.guard_backend_secrets", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_emit_masks_outputs_commands_for_codex_auth() -> None:
    result = run(
        ["--from-env", "CODEX_AUTH_JSON", "emit-masks"],
        {"CODEX_AUTH_JSON": json.dumps(managed_auth_payload())},
    )

    assert result.returncode == 0
    assert "::add-mask::eyJ-access" in result.stdout
    assert "::add-mask::rt-refresh" in result.stdout
    assert '"access_token": "eyJ-access"' not in result.stdout
    assert json.dumps(managed_auth_payload()) not in result.stdout


def test_emit_masks_outputs_commands_for_api_key() -> None:
    result = run(
        ["--from-env", "MINIMAX_API_KEY", "emit-masks"],
        {"MINIMAX_API_KEY": "mm-secret-key"},
    )

    assert result.returncode == 0
    assert "::add-mask::mm-secret-key" in result.stdout


def test_scan_files_passes_when_clean(tmp_path: Path) -> None:
    output = tmp_path / "clean.log"
    output.write_text("all clear")

    result = run(
        ["--from-env", "CODEX_AUTH_JSON", "scan-files", str(output)],
        {"CODEX_AUTH_JSON": json.dumps(managed_auth_payload())},
    )

    assert result.returncode == 0
    assert "No backend secret leakage" in result.stdout


def test_scan_files_fails_on_codex_leak(tmp_path: Path) -> None:
    output = tmp_path / "leak.log"
    output.write_text("oops rt-refresh leaked")

    result = run(
        ["--from-env", "CODEX_AUTH_JSON", "scan-files", str(output)],
        {"CODEX_AUTH_JSON": json.dumps(managed_auth_payload())},
    )

    assert result.returncode != 0
    assert "potential backend secret leakage" in result.stderr
    assert "CODEX_AUTH_JSON:refresh_token" in result.stderr


def test_scan_manifest_reads_patterns_from_file(tmp_path: Path) -> None:
    output = tmp_path / "clean.log"
    output.write_text("all clear")
    manifest = tmp_path / "paths.txt"
    manifest.write_text(f"{output}\n")

    result = run(
        ["--from-env", "MINIMAX_API_KEY", "scan-manifest", str(manifest)],
        {"MINIMAX_API_KEY": "mm-secret-key"},
    )

    assert result.returncode == 0
    assert "No backend secret leakage" in result.stdout


def test_scan_files_fails_on_base64_encoded_leak(tmp_path: Path) -> None:
    import base64

    secret = "mm-secret-key"
    encoded = base64.b64encode(secret.encode()).decode()
    output = tmp_path / "leak.log"
    output.write_text(f"encoded: {encoded}")

    result = run(
        ["--from-env", "MINIMAX_API_KEY", "scan-files", str(output)],
        {"MINIMAX_API_KEY": secret},
    )

    assert result.returncode != 0
    assert "potential backend secret leakage" in result.stderr


def test_scan_files_fails_on_base64_encoded_json_token_leak(tmp_path: Path) -> None:
    import base64

    payload = managed_auth_payload()
    refresh_token = payload["tokens"]["refresh_token"]
    encoded = base64.b64encode(refresh_token.encode()).decode()
    output = tmp_path / "leak.log"
    output.write_text(f"exfiltrated: {encoded}")

    result = run(
        ["--from-env", "CODEX_AUTH_JSON", "scan-files", str(output)],
        {"CODEX_AUTH_JSON": json.dumps(payload)},
    )

    assert result.returncode != 0
    assert "potential backend secret leakage" in result.stderr


def test_ignore_missing_skips_absent_vars() -> None:
    result = run(
        [
            "--ignore-missing",
            "--from-env",
            "MINIMAX_API_KEY",
            "--from-env",
            "CODEX_AUTH_JSON",
            "emit-masks",
        ],
        {"MINIMAX_API_KEY": "mm-secret-key"},
    )

    assert result.returncode == 0
    assert "::add-mask::mm-secret-key" in result.stdout
