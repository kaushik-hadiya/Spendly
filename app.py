import os
import re
import sqlite3
from datetime import datetime

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    create_user,
    get_db,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8

# Checked against when the email is unknown, so a miss takes as long as a
# wrong password and response timing doesn't reveal which emails exist.
DUMMY_PASSWORD_HASH = generate_password_hash("not-a-real-password")

# Placeholder until a later step replaces this with real per-user queries.
# Mirrors the seeded demo expenses: (date, description, category, amount).
PLACEHOLDER_EXPENSES = (
    ("2026-10-01", "Groceries at local market", "Food", 450.00),
    ("2026-10-05", "Auto rickshaw to office", "Transport", 120.00),
    ("2026-10-09", "Electricity bill", "Bills", 1850.00),
    ("2026-10-13", "Pharmacy - medicines", "Health", 600.00),
    ("2026-10-17", "Movie tickets", "Entertainment", 350.00),
    ("2026-10-21", "New shirt", "Shopping", 2499.00),
    ("2026-10-25", "Dinner with friends", "Food", 280.00),
    ("2026-10-29", None, "Other", 200.00),
)

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def validate_registration(name, email, password, confirm_password):
    if not name:
        return "Please enter your name."
    if not EMAIL_PATTERN.match(email):
        return "Please enter a valid email address."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if password != confirm_password:
        return "Passwords do not match."
    return None


def build_profile_placeholder():
    total = sum(e[3] for e in PLACEHOLDER_EXPENSES)

    by_category = {}
    for _, _, category, amount in PLACEHOLDER_EXPENSES:
        by_category[category] = by_category.get(category, 0) + amount
    categories = [
        {"name": name, "amount": amount, "percent": round(amount / total * 100, 1)}
        for name, amount in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
    ]

    recent = [
        {"date": d, "description": desc, "category": cat, "amount": amt}
        for d, desc, cat, amt in sorted(PLACEHOLDER_EXPENSES, key=lambda e: e[0], reverse=True)
    ]

    return {
        "total": total,
        "count": len(PLACEHOLDER_EXPENSES),
        "top_category": categories[0]["name"],
        "recent": recent,
        "categories": categories,
    }


# ------------------------------------------------------------------ #
# Template filters                                                    #
# ------------------------------------------------------------------ #

@app.template_filter("inr")
def format_inr(amount):
    # Indian digit grouping: last three digits, then pairs — ₹1,00,000.00
    sign = "-" if amount < 0 else ""
    whole, fraction = f"{abs(amount):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}₹{whole}.{fraction}"


@app.template_filter("initials")
def initials(name):
    words = (name or "").split()
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][0].upper()
    return (words[0][0] + words[-1][0]).upper()


@app.template_filter("short_date")
def short_date(iso_date):
    try:
        parsed = datetime.strptime(iso_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        return iso_date or ""
    return f"{parsed.day} {parsed:%b}, {parsed.year}"


@app.template_filter("member_since")
def member_since(created_at):
    try:
        return datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").strftime("%b %Y")
    except (TypeError, ValueError):
        return ""


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("profile"))
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    error = validate_registration(name, email, password, confirm_password)
    if error is None and get_user_by_email(email) is not None:
        error = "An account with that email already exists."

    if error is None:
        try:
            create_user(name, email, password)
        except sqlite3.IntegrityError:
            error = "An account with that email already exists."

    if error is not None:
        return render_template("register.html", error=error, name=name, email=email)

    flash("Account created — please sign in.", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("profile"))
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = None
    if not email or not password:
        error = "Please enter your email and password."
    else:
        user = get_user_by_email(email)
        if user is None:
            check_password_hash(DUMMY_PASSWORD_HASH, password)
            error = "Invalid email or password."
        elif not check_password_hash(user["password_hash"], password):
            error = "Invalid email or password."
        else:
            error = None

    if error is not None:
        return render_template("login.html", error=error, email=email)

    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please sign in to view your profile.", "error")
        return redirect(url_for("login"))

    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    return render_template("profile.html", user=user, **build_profile_placeholder())


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
