import hashlib
import hmac

from github_webhook.github_signature import verify_signature


def test_verify_signature_accepts_valid_signature() -> None:
    body = b'{"hello":"world"}'
    secret = "top-secret"
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    assert verify_signature(secret, f"sha256={digest}", body)


def test_verify_signature_rejects_invalid_signature() -> None:
    assert not verify_signature("top-secret", "sha256=deadbeef", b"body")
