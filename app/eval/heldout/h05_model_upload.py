import pickle

from flask import request


def load_uploaded_model():
    return pickle.load(request.files["model"])  # EXPECT: security


def save_model(model, path):
    with open(path, "wb") as handle:
        pickle.dump(model, handle)


def model_name(path):
    return path.rsplit("/", 1)[-1]
