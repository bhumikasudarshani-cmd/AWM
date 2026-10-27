import os
import subprocess


def git_status(repo):
    result = subprocess.run(["git", "-C", repo, "status", "--short"], check=True, capture_output=True, text=True)
    return result.stdout


def default_shell():
    shell = os.environ.get("SHELL", "/bin/sh")
    return shell


def run_tests():
    return subprocess.run(["pytest", "-q"], check=False).returncode
