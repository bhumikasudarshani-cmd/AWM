import jwt


def current_user(token, key):
    claims = jwt.decode(token, key, options={"verify_signature": False})  # EXPECT: security
    return claims.get("sub")


def issue_token(user_id, key):
    return jwt.encode({"sub": user_id}, key, algorithm="HS256")


def token_subject(token, key):
    return jwt.decode(token, key, algorithms=["HS256"]).get("sub")
