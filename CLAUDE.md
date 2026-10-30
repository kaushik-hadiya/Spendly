# CLAUDE.md

## Project overview

Spendly is a lightweight personal expense tracker built with Flask and SQLite.

---

## Architecture
```
spendly/
├── app.py              # All routes — single file, no blueprints
├── database/
│   └── db.py           # SQLite helpers: get_db(), init_db(), seed_db()
├── templates/
│   ├── base.html       # Shared layout — all templates must extend this
│   └── *.html          # One template per page
├── static/
│   ├── css/
│   │   ├── style.css       # Global styles
│   │   ├── landing.css     # Landing-page-only styles
│   │   ├── expense_form.css # Add/edit expense form styles
│   │   └── delete_expense.css # Delete confirmation page styles
│   └── js/
│       └── main.js         # Vanilla JS only
└── requirements.txt
```

**Where things belong:**
- New routes → `app.py` only, no blueprints
- DB logic → `database/db.py` only, never inline in routes
- New pages → new `.html` file extending `base.html`
- Page-specific styles → new `.css` file, not inline `<style>` tags

---

## Code style

- Python: PEP 8, snake_case for all variables and functions
- Templates: Jinja2 with `url_for()` for every internal link — never hardcode URLs
- Route functions: one responsibility only — fetch data, render template, done
- DB queries: always use parameterized queries (`?` placeholders) — never f-strings in SQL
- Error handling: use `abort()` for HTTP errors, not bare `return "error string"`
- Currency: always INR (₹), never USD ($) — in UI copy, formatting, seed data, and tests

---

## Tech constraints

- **Flask only** — no FastAPI, no Django, no other web frameworks
- **SQLite only** — no PostgreSQL, no SQLAlchemy ORM, no external DB
- **Vanilla JS only** — no React, no jQuery, no npm packages
- **No new pip packages** — work within `requirements.txt` as-is unless explicitly told otherwise
- Python 3.10+ assumed — f-strings and `match` statements are fine

---

## Subagent Policy
- Always use a builtin explore subagent for codebase exploration 
  before implementing any new feature
- Always use a subagent to verify test results 
  after any implementation
- When asked to plan, delegate codebase research 
  to a subagent before presenting the plan
- always use a builtin plan subagent in plan mode

---

## Commands
```bash
# Setup
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run dev server (port 5001)
python app.py

# Run all tests
pytest

# Run a specific test file
pytest tests/test_foo.py

# Run a specific test by name
pytest -k "test_name"

# Run tests with output visible
pytest -s
```

---

## Implemented vs stub routes

| Route | Status |
|---|---|
| `GET /` | Implemented — renders `landing.html` |
| `GET /register` | Implemented — renders `register.html`; redirects signed-in users to `/profile` |
| `GET /login` | Implemented — renders `login.html`; redirects signed-in users to `/profile` |
| `POST /login` | Implemented — session sign-in, redirects to `/profile` |
| `GET /logout` | Implemented — clears session, redirects to `/login` |
| `GET /profile` | Implemented — renders `profile.html` with the signed-in user's real expense stats; supports optional `?start=` / `?end=` (YYYY-MM-DD, inclusive) date filter, invalid ranges fall back to all time with an inline error; preset links also carry `?preset=this-month|last-30-days` so the clicked preset stays highlighted when two presets share a range; redirects signed-out users to `/login` |
| `GET /analytics` | Implemented — renders `analytics.html` (Coming Soon page); navbar link shown only to signed-in users, highlighted via `request.endpoint`; redirects signed-out users to `/login` |
| `GET /expenses/add` | Implemented — renders `add_expense.html` (date defaults to today); redirects signed-out users to `/login` |
| `POST /expenses/add` | Implemented — validated by `validate_expense()` in `app.py`, saved via `create_expense()` for the session user, flashes "Expense added.", redirects to `/profile`; invalid input re-renders the form with an inline error (200) |
| `GET /expenses/<id>/edit` | Implemented — renders `edit_expense.html` pre-filled with the expense (form fields shared with add via `_expense_form_fields.html`); 404 if the expense is missing or not the session user's; redirects signed-out users to `/login` |
| `POST /expenses/<id>/edit` | Implemented — validated by `validate_expense()`, saved via `update_expense()` scoped to the session user, flashes "Expense updated.", redirects to `/profile`; invalid input re-renders with an inline error (200); bad CSRF → 400 |
| `GET /expenses/<id>/delete` | Implemented — renders `delete_expense.html` confirmation (amount, category, date, description); never modifies the DB; 404 if the expense is missing or not the session user's; redirects signed-out users to `/login` |
| `POST /expenses/<id>/delete` | Implemented — deletes via `delete_expense_by_id()` scoped to the session user, flashes "Expense deleted.", redirects to `/profile`; bad CSRF → 400; missing or not owned → 404 |

**Do not implement a stub route unless the active task explicitly targets that step.**

---

## Warnings and things to avoid

- **Never use raw string returns for stub routes** once a step is implemented — always render a template
- **Never hardcode URLs** in templates — always use `url_for()`
- **Never put DB logic in route functions** — it belongs in `database/db.py`
- **Never install new packages** mid-feature without flagging it — keep `requirements.txt` in sync
- **Never use JS frameworks** — the frontend is intentionally vanilla
- **Check `database/db.py` before adding DB helpers** — it already has `get_db()`, `init_db()`, `seed_db()`, `get_user_by_email()`, `get_user_by_id()`, `create_user()`, `create_expense()`, `get_expense_by_id()`, `update_expense()`, `delete_expense_by_id()` (all scoped by `user_id`), `get_expense_summary()`, `get_recent_expenses()` and `get_category_totals()` (the last three accept optional `start_date` / `end_date` ISO-string kwargs, validated first by `parse_date_range()` in `app.py`); reuse these rather than writing duplicates, and don't assume any other helper exists until the step that implements it
- **FK enforcement is manual** — SQLite foreign keys are off by default; `get_db()` must run `PRAGMA foreign_keys = ON` on every connection
- The app runs on **port 5001**, not the Flask default 5000 — don't change this