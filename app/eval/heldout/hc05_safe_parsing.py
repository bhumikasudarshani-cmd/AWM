import ast
import json

import yaml


def read_settings(text):
    return yaml.safe_load(text)


def read_payload(raw):
    return json.loads(raw)


def read_literal(text):
    return ast.literal_eval(text)


def merge(base, extra):
    merged = dict(base)
    merged.update(extra)
    return merged
