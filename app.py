import os
import re
import sqlite3
from datetime import date, datetime, timedelta

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    create_user,
    get_category_totals,
    get_db,
    get_expense_summary,
    get_recent_expenses,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8
DATE_FORMAT = "%Y-%m-%d"
INVALID_RANGE_MESSAGE = "Invalid date range — showing all time."

# Checked against when the email is unknown, so a miss takes as long as a
# wrong password and response timing doesn't reveal which emails exist.
DUMMY_PASSWORD_HASH = generate_password_hash("not-a-real-password")

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


def _parse_iso_date(value):
    value = (value or "").strip()
    if not value:
        return None
    return datetime.strptime(value, DATE_FORMAT).date()


def parse_date_range(args):
    # Any bad value drops the whole filter — the page falls back to all time.
    try:
        start = _parse_iso_date(args.get("start"))
        end = _parse_iso_date(args.get("end"))
    except ValueError:
        return None, None, INVALID_RANGE_MESSAGE
    if start and end and start > end:
        return None, None, INVALID_RANGE_MESSAGE
    return (
        start.isoformat() if start else None,
        end.isoformat() if end else None,
        None,
    )


def build_date_presets(today):
    today_iso = today.isoformat()
    return [
        {
            "label": "This month",
            "start": today.replace(day=1).isoformat(),
            "end": today_iso,
        },
        {
            "label": "Last 30 days",
            "start": (today - timedelta(days=29)).isoformat(),
            "end": today_iso,
        },
        {"label": "All time", "start": None, "end": None},
    ]


def describe_date_range(start_date, end_date):
    if start_date and end_date:
        return f"Showing {short_date(start_date)} – {short_date(end_date)}"
    if start_date:
        return f"Showing from {short_date(start_date)}"
    if end_date:
        return f"Showing up to {short_date(end_date)}"
    return "Showing all time"


def build_profile_stats(user_id, start_date=None, end_date=None):
    summary = get_expense_summary(user_id, start_date=start_date, end_date=end_date)
    total = summary["total"]

    categories = [
        {
            "name": row["category"],
            "amount": row["amount"],
            "percent": round(row["amount"] / total * 100, 1) if total else 0,
        }
        for row in get_category_totals(user_id, start_date=start_date, end_date=end_date)
    ]

    recent = [
        dict(row)
        for row in get_recent_expenses(user_id, start_date=start_date, end_date=end_date)
    ]

    return {
        "total": total,
        "count": summary["count"],
        "top_category": categories[0]["name"] if categories else None,
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
        parsed = datetime.strptime(iso_date, DATE_FORMAT)
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

    start_date, end_date, filter_error = parse_date_range(request.args)
    return render_template(
        "profile.html",
        user=user,
        start_date=start_date,
        end_date=end_date,
        filter_error=filter_error,
        range_caption=describe_date_range(start_date, end_date),
        presets=build_date_presets(date.today()),
        **build_profile_stats(user["id"], start_date, end_date),
    )


@app.route("/analytics")
def analytics():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please sign in to view analytics.", "error")
        return redirect(url_for("login"))

    if get_user_by_id(user_id) is None:
        session.clear()
        return redirect(url_for("login"))

    return render_template("analytics.html")


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
