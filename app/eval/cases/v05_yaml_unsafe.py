import yaml


def read_config(text):
    return yaml.load(text, Loader=yaml.Loader)  # EXPECT: security
