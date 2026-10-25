def test_login_rejects_bad_password():
    password = "test-password-123"
    assert not login("alice", password)
