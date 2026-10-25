import requests


def post_data(url, data):
    return requests.post(url, data=data, verify=False)  # EXPECT: security
