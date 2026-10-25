import os


def read_upload(filename):
    path = os.path.join("/srv/uploads", filename)
    with open(path) as handle:  # EXPECT: security
        return handle.read()
