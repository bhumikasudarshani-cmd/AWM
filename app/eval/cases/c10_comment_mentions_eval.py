import json


def parse(text):
    # Never use eval(text) here; parse the data with json instead.
    return json.loads(text)
