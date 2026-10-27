from flask import Flask, session

app = Flask(__name__)
app.secret_key = "9f2c7a1e5b8d4f60a3c1e7d9b2a4f680"  # EXPECT: security


@app.route("/login", methods=["POST"])
def login():
    session["user"] = "demo"
    return "ok"


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return "bye"


@app.route("/health")
def health():
    return "up"
