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


GROCERIES = "Groceries at local market"


def fetch_row(expense_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, user_id, amount, category, date, description "
            "FROM expenses WHERE id = ?",
            (expense_id,),
        ).fetchone()
    finally:
        conn.close()


def snapshot(expense_id):
    row = fetch_row(expense_id)
    return tuple(row) if row is not None else None


def expense_count(user_id=None):
    conn = get_db()
    try:
        if user_id is None:
            row = conn.execute("SELECT COUNT(*) AS n FROM expenses").fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return row["n"]
    finally:
        conn.close()


def groceries_id():
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM expenses WHERE description = ? AND user_id = ?",
            (GROCERIES, DEMO_USER_ID),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "Seeded groceries expense missing"
    return row["id"]


def csrf_token_for(client):
    # Mirrors what the form pages do: one token per session.
    with client.session_transaction() as sess:
        return sess.setdefault("csrf_token", "test-csrf-token")


def input_tag(html, name):
    match = re.search(r'<input\b[^>]*\bname="%s"[^>]*>' % re.escape(name), html)
    assert match, f"No <input name={name}> found in page"
    return match.group(0)


def attr(tag, attribute):
    match = re.search(r'\b%s="([^"]*)"' % re.escape(attribute), tag)
    return match.group(1) if match else None
