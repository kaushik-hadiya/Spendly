import os
import sqlite3
from datetime import date

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "expense_tracker.db")

CATEGORIES = (
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_user_by_email(email):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, name, email, password_hash, created_at "
            "FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()


def _date_range_params(start_date, end_date):
    # Binds for "(? IS NULL OR date >= ?) AND (? IS NULL OR date <= ?)";
    # a None bound disables that side of the range.
    return (start_date, start_date, end_date, end_date)


def get_expense_summary(user_id, start_date=None, end_date=None):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count "
            "FROM expenses WHERE user_id = ? "
            "AND (? IS NULL OR date >= ?) AND (? IS NULL OR date <= ?)",
            (user_id, *_date_range_params(start_date, end_date)),
        ).fetchone()
    finally:
        conn.close()


def get_recent_expenses(user_id, limit=10, start_date=None, end_date=None):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, date, description, category, amount FROM expenses "
            "WHERE user_id = ? "
            "AND (? IS NULL OR date >= ?) AND (? IS NULL OR date <= ?) "
            "ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, *_date_range_params(start_date, end_date), limit),
        ).fetchall()
    finally:
        conn.close()


def get_category_totals(user_id, start_date=None, end_date=None):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT category, SUM(amount) AS amount FROM expenses "
            "WHERE user_id = ? "
            "AND (? IS NULL OR date >= ?) AND (? IS NULL OR date <= ?) "
            "GROUP BY category ORDER BY amount DESC, category ASC",
            (user_id, *_date_range_params(start_date, end_date)),
        ).fetchall()
    finally:
        conn.close()


def create_user(name, email, password):
    # Raises sqlite3.IntegrityError if the email is already registered.
    conn = get_db()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password)),
            )
        return cur.lastrowid
    finally:
        conn.close()


def create_expense(user_id, amount, category, expense_date, description=None):
    conn = get_db()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, amount, category, expense_date, description or None),
            )
        return cur.lastrowid
    finally:
        conn.close()


def init_db():
    conn = get_db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                amount      REAL NOT NULL,
                category    TEXT NOT NULL,
                date        TEXT NOT NULL,
                description TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            """
        )
    finally:
        conn.close()


def _seed_dates(count=8):
    # Spread dates from the 1st of the month up to today — never future, never invalid.
    today = date.today()
    span = today.day - 1
    return [
        today.replace(day=1 + i * span // (count - 1)).isoformat()
        for i in range(count)
    ]


def seed_db():
    conn = get_db()
    try:
        with conn:
            if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                return

            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
            )
            user_id = cur.lastrowid
            d = _seed_dates()

            expenses = [
                (user_id, 450.00, "Food", d[0], "Groceries at local market"),
                (user_id, 120.00, "Transport", d[1], "Auto rickshaw to office"),
                (user_id, 1850.00, "Bills", d[2], "Electricity bill"),
                (user_id, 600.00, "Health", d[3], "Pharmacy - medicines"),
                (user_id, 350.00, "Entertainment", d[4], "Movie tickets"),
                (user_id, 2499.00, "Shopping", d[5], "New shirt"),
                (user_id, 280.00, "Food", d[6], "Dinner with friends"),
                (user_id, 200.00, "Other", d[7], None),
            ]
            conn.executemany(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                expenses,
            )
    finally:
        conn.close()
