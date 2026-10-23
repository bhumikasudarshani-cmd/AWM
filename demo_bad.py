import subprocess
import requests


def run(cmd):
    breakpoint()
    return subprocess.run(cmd, shell=True)


def fetch(url):
    return requests.get(url, verify=False)


password = "hunter2hunter2"
