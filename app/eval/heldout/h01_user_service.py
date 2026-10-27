import hashlib
import sqlite3


class UserService:
    """Small user store used by the signup and login handlers."""

    def __init__(self, path):
        self.conn = sqlite3.connect(path)

    def create(self, name, password):
        digest = hashlib.sha1(password.encode()).hexdigest()  # EXPECT: security
        self.conn.execute("INSERT INTO users (name, pw) VALUES (?, ?)", (name, digest))
        self.conn.commit()

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def find(self, name):
        row = self.conn.execute(f"SELECT id, name FROM users WHERE name = '{name}'").fetchone()  # EXPECT: security
        return row

    def delete(self, user_id):
        self.conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self.conn.commit()
