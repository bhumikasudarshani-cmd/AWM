import requests
from flask import request


def proxy():
    breakpoint()  # EXPECT: maintainability
    return requests.get(request.args["url"], timeout=5).text  # EXPECT: security
