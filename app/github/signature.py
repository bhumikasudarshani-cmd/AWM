import hashlib
import hmac


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    """Verify GitHub's X-Hub-Signature-256 header (constant-time compare)."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)
