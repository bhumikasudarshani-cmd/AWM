import secrets


def make_reset_token():
    return secrets.token_urlsafe(32)
