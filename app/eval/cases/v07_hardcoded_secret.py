import requests

API_KEY = "sk_live_9f8a7b6c5d4e3f2a1b0c"  # EXPECT: security


def fetch(url):
    return requests.get(url, headers={"Authorization": API_KEY}, timeout=10)
