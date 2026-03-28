from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass

import rsa

from github_webhook.config import GITHUB_API_BASE, Settings


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def build_app_jwt(app_id: str, private_key_pem: str, *, now: int | None = None) -> str:
    now_ts = now if now is not None else int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iat": now_ts - 60,
        "exp": now_ts + 540,
        "iss": app_id,
    }

    signing_input = ".".join(
        [
            _base64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode()),
            _base64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()),
        ]
    ).encode("ascii")

    try:
        private_key = rsa.PrivateKey.load_pkcs1(private_key_pem.encode("utf-8"))
    except ValueError as exc:
        raise ValueError("GH_APP_PRIVATE_KEY must be a PKCS#1 RSA private key PEM") from exc

    signature = rsa.sign(signing_input, private_key, "SHA-256")
    return f"{signing_input.decode('ascii')}.{_base64url_encode(signature)}"


@dataclass(frozen=True)
class InstallationTokenRequest:
    url: str
    headers: dict[str, str]
    body: str


def build_installation_token_request(
    settings: Settings,
    *,
    installation_id: int,
    now: int | None = None,
) -> InstallationTokenRequest:
    app_jwt = build_app_jwt(settings.github_app_id, settings.github_app_private_key, now=now)
    return InstallationTokenRequest(
        url=f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {app_jwt}",
            "Content-Type": "application/json",
            "User-Agent": "6-bot-github-webhook",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        body="{}",
    )
