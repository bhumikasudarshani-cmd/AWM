import pickle


def load_session(payload):
    obj = pickle.loads(payload)  # EXPECT: security
    return obj
