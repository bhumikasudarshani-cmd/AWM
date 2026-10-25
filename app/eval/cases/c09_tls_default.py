import requests


def get_page(url):
    return requests.get(url, timeout=10).text
