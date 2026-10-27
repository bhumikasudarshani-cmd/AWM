def test_login_with_wrong_password(client):
    api_key = "test-key-000000"
    response = client.post("/login", json={"user": "alice", "password": "wrong-password"}, headers={"X-Key": api_key})
    assert response.status_code == 401


def test_health_endpoint(client):
    assert client.get("/health").status_code == 200
