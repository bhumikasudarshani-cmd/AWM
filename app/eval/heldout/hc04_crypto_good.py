import hashlib
import hmac
import secrets


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return salt, digest


def verify_password(password, salt, expected):
    _, digest = hash_password(password, salt)
    return hmac.compare_digest(digest, expected)


def new_session_id():
    return secrets.token_urlsafe(32)
