import ast


def parse_value(text):
    return ast.literal_eval(text)
