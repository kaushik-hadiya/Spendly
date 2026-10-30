import hmac
import math
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    CATEGORIES,
    create_expense,
    create_user,
    get_category_totals,
    get_db,
    get_expense_by_id,
    get_expense_summary,
    get_recent_expenses,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
    update_expense,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
# Lax keeps the session cookie off cross-site POSTs — first line of CSRF defence.
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8
DATE_FORMAT = "%Y-%m-%d"
INVALID_RANGE_MESSAGE = "Invalid date range — showing all time."
MAX_EXPENSE_AMOUNT = 10_000_000
MAX_DESCRIPTION_LENGTH = 200
EXPENSE_FIELDS = ("amount", "category", "date", "description")

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


def validate_expense(form):
    raw_amount = (form.get("amount") or "").strip()
    if not raw_amount:
        return None, "Please enter an amount."
    try:
        amount = float(raw_amount)
    except ValueError:
        return None, "Amount must be a number."
    if not math.isfinite(amount):
        return None, "Amount must be a number."
    # Bounds are checked after rounding, so 0.004 is rejected and 99.999 → 100.0.
    amount = round(amount, 2)
    if amount <= 0:
        return None, "Amount must be greater than ₹0."
    if amount > MAX_EXPENSE_AMOUNT:
        return None, f"Amount cannot exceed {format_inr(MAX_EXPENSE_AMOUNT)}."

    category = form.get("category") or ""
    if category not in CATEGORIES:
        return None, "Please choose a valid category."

    try:
        expense_date = _parse_iso_date(form.get("date"))
    except ValueError:
        return None, "Please enter a valid date."
    if expense_date is None:
        return None, "Please enter a date."
    if expense_date > date.today():
        return None, "Date cannot be in the future."

    description = (form.get("description") or "").strip() or None
    if description and len(description) > MAX_DESCRIPTION_LENGTH:
        return None, f"Description must be {MAX_DESCRIPTION_LENGTH} characters or fewer."

    return {
        "amount": amount,
        "category": category,
        "date": expense_date.isoformat(),
        "description": description,
    }, None


def render_expense_form(values, error=None, template="add_expense.html", **context):
    # values: dict keyed by EXPENSE_FIELDS — defaults on GET, submitted input on error.
    # template / **context let the add and edit pages share this; context is
    # passed through to the template (e.g. expense_id for the edit form action).
    return render_template(
        template,
        categories=CATEGORIES,
        today=date.today().isoformat(),
        max_description_length=MAX_DESCRIPTION_LENGTH,
        values=values,
        error=error,
        **context,
    )


def expense_form_values(expense):
    # Dict keyed by EXPENSE_FIELDS from a DB row. Plain number for the
    # type="number" input — no ₹ or digit grouping.
    return {
        "amount": f"{expense['amount']:.2f}",
        "category": expense["category"],
        "date": expense["date"],
        "description": expense["description"] or "",
    }


def submitted_expense_values(form):
    # Raw form input keyed by EXPENSE_FIELDS, echoed back when validation fails.
    return {field: form.get(field, "") for field in EXPENSE_FIELDS}


def render_edit_expense_form(expense_id, values, error=None):
    return render_expense_form(
        values, error, template="edit_expense.html", expense_id=expense_id
    )


def get_current_user():
    # The signed-in user's row, or None. A session pointing at a deleted
    # user is cleared so it can't linger.
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
    return user


@app.template_global()
def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def csrf_token_valid(form):
    # Compared as bytes — compare_digest raises TypeError on non-ASCII str.
    expected = session.get("csrf_token")
    supplied = form.get("csrf_token", "")
    return bool(expected) and hmac.compare_digest(
        supplied.encode("utf-8"), expected.encode("utf-8")
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
    user = get_current_user()
    if user is None:
        flash("Please sign in to view your profile.", "error")
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
    if get_current_user() is None:
        flash("Please sign in to view analytics.", "error")
        return redirect(url_for("login"))

    return render_template("analytics.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    user = get_current_user()
    if user is None:
        flash("Please sign in to add an expense.", "error")
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_expense_form({"date": date.today().isoformat()})

    if not csrf_token_valid(request.form):
        abort(400)

    expense, error = validate_expense(request.form)
    if error is not None:
        return render_expense_form(submitted_expense_values(request.form), error)

    create_expense(
        user["id"],
        expense["amount"],
        expense["category"],
        expense["date"],
        expense["description"],
    )
    flash("Expense added.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    user = get_current_user()
    if user is None:
        flash("Please sign in to edit an expense.", "error")
        return redirect(url_for("login"))

    # Reject forged POSTs before touching the DB.
    if request.method == "POST" and not csrf_token_valid(request.form):
        abort(400)

    # Missing and not-yours look the same, so other users' ids aren't revealed.
    expense = get_expense_by_id(id, user["id"])
    if expense is None:
        abort(404)

    if request.method == "GET":
        return render_edit_expense_form(id, expense_form_values(expense))

    updated, error = validate_expense(request.form)
    if error is not None:
        return render_edit_expense_form(id, submitted_expense_values(request.form), error)

    changed = update_expense(
        id,
        user["id"],
        updated["amount"],
        updated["category"],
        updated["date"],
        updated["description"],
    )
    # The row can vanish between the read and the write (e.g. deleted in another tab).
    if changed == 0:
        abort(404)
    flash("Expense updated.", "success")
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
