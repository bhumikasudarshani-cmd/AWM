import requests

BASE_URL = "https://api.internal.example.com"
AUTH_TOKEN = "ghp_1A2b3C4d5E6f7G8h9I0jKlMnOpQrStUvWxYz"  # EXPECT: security


def get_orders(customer_id):
    url = f"{BASE_URL}/customers/{customer_id}/orders"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    response = requests.get(url, headers=headers, timeout=10, verify=False)  # EXPECT: security
    response.raise_for_status()
    return response.json()


def get_profile(customer_id):
    url = f"{BASE_URL}/customers/{customer_id}"
    return requests.get(url, timeout=10).json()
