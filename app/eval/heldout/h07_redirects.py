from flask import redirect, request


def default_page(user):
    return "/admin" if user.is_admin else "/home"


def after_login():
    target = request.args.get("next", "/")
    return redirect(request.args.get("next", target))  # EXPECT: security


def after_logout():
    return redirect("/login")
