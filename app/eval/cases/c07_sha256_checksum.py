import hashlib


def file_checksum(data):
    return hashlib.sha256(data).hexdigest()
