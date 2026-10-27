import sqlite3


class OrderStore:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)

    def by_customer(self, customer_id):
        cur = self.conn.execute("SELECT * FROM orders WHERE customer_id = ?", (customer_id,))
        return cur.fetchall()

    def add(self, customer_id, total):
        self.conn.execute("INSERT INTO orders (customer_id, total) VALUES (?, ?)", (customer_id, total))
        self.conn.commit()

    def totals_between(self, low, high):
        sql = "SELECT SUM(total) FROM orders WHERE total BETWEEN ? AND ?"
        return self.conn.execute(sql, (low, high)).fetchone()[0]
