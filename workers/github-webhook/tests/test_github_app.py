import base64
import json

import rsa

from github_webhook.config import Settings
from github_webhook.github_app import build_app_jwt, build_installation_token_request


def _decode_segment(segment: str) -> dict[str, object]:
    padding = "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(f"{segment}{padding}"))


def test_build_app_jwt_signs_expected_claims() -> None:
    public_key, private_key = rsa.newkeys(512)
    pem = private_key.save_pkcs1().decode("utf-8")

    token = build_app_jwt("12345", pem, now=1_700_000_000)
    header_segment, payload_segment, signature_segment = token.split(".")
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")

    assert _decode_segment(header_segment) == {"alg": "RS256", "typ": "JWT"}
    assert _decode_segment(payload_segment) == {
        "exp": 1_700_000_540,
        "iat": 1_699_999_940,
        "iss": "12345",
    }

    padding = "=" * (-len(signature_segment) % 4)
    signature = base64.urlsafe_b64decode(f"{signature_segment}{padding}")
    rsa.verify(signing_input, signature, public_key)


def test_build_installation_token_request_uses_app_jwt() -> None:
    _, private_key = rsa.newkeys(512)
    settings = Settings(
        allowed_associations=("OWNER",),
        allowed_commands=("/6bot repair",),
        allowed_repositories=("6/nitrocop",),
        bot_control_repo="6/bot",
        dispatch_workflow="webhook-command.yml",
        github_app_id="12345",
        github_app_private_key=private_key.save_pkcs1().decode("utf-8"),
        github_api_base="https://api.github.com",
        webhook_secret="secret",
        workflow_ref="main",
    )

    request = build_installation_token_request(settings, installation_id=987, now=1_700_000_000)

    assert request.url == "https://api.github.com/app/installations/987/access_tokens"
    assert request.body == "{}"
    assert request.headers["Authorization"].startswith("Bearer ")
