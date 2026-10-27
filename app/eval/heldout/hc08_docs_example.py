"""Helpers for reading AWS settings.

Example of the format used in the documentation (AWS's public example key, not a real one):

    access_key_id = AKIAIOSFODNN7EXAMPLE
"""
import os


def access_key_id():
    return os.environ["AWS_ACCESS_KEY_ID"]


def region():
    return os.environ.get("AWS_REGION", "us-east-1")
