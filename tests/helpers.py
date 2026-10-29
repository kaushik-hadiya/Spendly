import re

from database.db import get_db

DEMO_USER_ID = 1


def add_expense(user_id, amount, category, date, description=None):
    conn = get_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, amount, category, date, description),
            )
    finally:
        conn.close()


def register_and_login(client, name, email, password="securepass1"):
    client.post(
        "/register",
        data={
            "name": name,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )
    client.post("/login", data={"email": email, "password": password})
    with client.session_transaction() as sess:
        return sess["user_id"]


def sign_in_as_demo(client):
    with client.session_transaction() as sess:
        sess["user_id"] = DEMO_USER_ID
        sess["user_name"] = "Demo User"


def txn_rows(html):
    return re.findall(r'<td class="txn-date">', html)
