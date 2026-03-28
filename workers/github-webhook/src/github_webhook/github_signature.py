from __future__ import annotations

import hashlib
import hmac


def verify_signature(secret: str, signature_header: str | None, body: bytes) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", signature_header)
