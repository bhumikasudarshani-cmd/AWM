import random


def make_reset_token():
    return str(random.randint(100000, 999999))  # EXPECT: security
