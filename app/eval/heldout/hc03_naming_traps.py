PASSWORD_FIELD = "password"
TOKEN_HEADER = "X-Auth-Token"


def evaluate_model(model, rows):
    scores = [model.predict(row) for row in rows]
    return sum(scores) / len(scores)


def describe_error(kind):
    if kind == "bad_password":
        return "invalid password supplied"
    return "unknown error"


def form_values(form):
    return {name: form.get(name) for name in (PASSWORD_FIELD, "email")}
