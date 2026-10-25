import os

API_KEY = os.environ["API_KEY"]


def headers():
    return {"Authorization": API_KEY}
