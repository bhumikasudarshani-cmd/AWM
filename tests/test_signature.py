import hashlib
import hmac

from app.github.signature import verify_signature

SECRET = "s3cret"
BODY = b'{"zen":"Keep it logically awesome."}'


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature():
    assert verify_signature(SECRET, BODY, sign(SECRET, BODY))


def test_wrong_secret():
    assert not verify_signature(SECRET, BODY, sign("other", BODY))


def test_tampered_body():
    assert not verify_signature(SECRET, BODY + b" ", sign(SECRET, BODY))


def test_missing_or_malformed_header():
    assert not verify_signature(SECRET, BODY, None)
    assert not verify_signature(SECRET, BODY, "md5=abc")


def test_empty_secret_rejected():
    assert not verify_signature("", BODY, sign("", BODY))
