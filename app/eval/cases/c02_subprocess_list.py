import subprocess


def list_dir(path):
    return subprocess.run(["ls", "-l", path], check=True, capture_output=True)
