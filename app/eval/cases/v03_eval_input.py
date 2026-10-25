def calculate(user_expr):
    result = eval(user_expr)  # EXPECT: security
    return result
