import os

import requests


def auth_headers():
    return {"Authorization": "Bearer " + os.environ["SERVICE_TOKEN"]}


def fetch_json(url):
    response = requests.get(url, headers=auth_headers(), timeout=10)
    response.raise_for_status()
    return response.json()


def post_json(url, payload):
    response = requests.post(url, json=payload, headers=auth_headers(), timeout=10)
    response.raise_for_status()
    return response.json()
