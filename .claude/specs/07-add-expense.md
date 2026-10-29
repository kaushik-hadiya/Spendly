# Spec: Add Expense

## Overview
Up to Step 6, every expense on the profile page comes from seed data —
users can view and filter their spending but cannot record anything new.
This step replaces the `/expenses/add` stub with a real form so a signed-in
user can record an expense: amount (₹), category, date and an optional
description. On success the expense is saved against the session user,
a success flash is shown and the user is redirected to `/profile`, where
the new expense immediately appears in the stats, recent-transactions table
and category breakdown (inside whatever date range is selected). Invalid
input re-renders the form with an inline error and the user's values kept.
This is the first write path for expenses and the foundation for Step 8
(edit) and Step 9 (delete).

## Depends on
- **Step 1 — Database setup:** the `expenses` table and the `CATEGORIES`
  tuple in `database/db.py`.
- **Step 3 — Login and Logout:** `session["user_id"]`.
- **Step 4 — Profile Page Design:** `profile.html` / `profile.css` (gets an
  "Add expense" link) and the `auth-error` / `auth-success` flash styles.
- **Step 5 — Backend Routes for Profile Page:** profile stats helpers, so a
  new expense shows up on `/profile`.
- **Step 6 — Date Filter for Profile Page:** `DATE_FORMAT` and
  `_parse_iso_date()` in `app.py`, reused for date validation.

## Routes
- `GET /expenses/add` — render the add-expense form; the date field
  defaults to today — logged-in
- `POST /expenses/add` — validate the form, insert the expense for the
  session user, flash "Expense added.", redirect (302) to `/profile`; on
  invalid input re-render the form with an error and status 200 — logged-in

Both methods share the existing `add_expense` endpoint
(`@app.route("/expenses/add", methods=["GET", "POST"])`), replacing the raw
string stub. Signed-out users on either method are flashed "Please sign in
to add an expense." and redirected (302) to `/login`. A session whose user
no longer exists is cleared and redirected to `/login` (same guard as
`/profile` and `/analytics`).

Do not touch the `/expenses/<id>/edit` or `/expenses/<id>/delete` stubs.

## Database changes
No schema changes — the existing `expenses` table already has `user_id`,
`amount`, `category`, `date` and `description`.

Add one helper to `database/db.py`:

- `create_expense(user_id, amount, category, expense_date, description=None)`
  — inserts one row with a parameterised `INSERT`, inside `with conn:`, and
  returns `cur.lastrowid`. Mirrors the style of `create_user()`.
  `description` is stored as `NULL` when empty.

## Templates
- **Create:**
  - `templates/add_expense.html` — extends `base.html`, loads
    `expense_form.css` in `{% block head %}`. Contains:
    - A heading ("Add expense") and short subtitle.
    - Inline error block (`auth-error`) when `error` is set.
    - A `POST` form with `action="{{ url_for('add_expense') }}"`:
      - `amount` — `<input type="number" step="0.01" min="0.01">`, labelled
        "Amount (₹)", required.
      - `category` — `<select>` with one `<option>` per entry in
        `categories` (passed from the route, sourced from `CATEGORIES`),
        required, the submitted value re-selected on error.
      - `date` — `<input type="date">`, required, defaults to today,
        `max` set to today.
      - `description` — `<input type="text" maxlength="200">`, optional.
      - Submit button "Add expense" and a "Cancel" link to
        `url_for('profile')`.
    - All fields re-filled with the submitted values when re-rendered after
      an error.
- **Modify:**
  - `templates/profile.html` — add an "Add expense" link
    (`url_for('add_expense')`, styled as a primary button) near the filter
    bar / stat grid. All existing class names stay.

## Files to change
- `app.py`:
  - Import `create_expense` and `CATEGORIES` from `database.db`.
  - Add a module-level helper `validate_expense(form)` that returns
    `(expense, error)`, where `expense` is a dict with `amount` (float),
    `category`, `date` (ISO string) and `description` (str or `None`).
    Rules:
    - `amount` — required, parses as a finite number, `> 0`, at most
      `MAX_EXPENSE_AMOUNT` (module constant, `10_000_000`), rounded to 2
      decimal places. `nan` / `inf` are rejected.
    - `category` — must be exactly one of `CATEGORIES`.
    - `date` — required, a real `YYYY-MM-DD` date (reuse
      `_parse_iso_date()`), not in the future.
    - `description` — stripped; empty → `None`; longer than
      `MAX_DESCRIPTION_LENGTH` (`200`) is an error.
    - First failing rule wins; return a human-readable message.
  - Replace the `add_expense` stub with a GET/POST route that follows
    "guard, validate, save/render": login guard → on GET render the form →
    on POST call `validate_expense(request.form)`, on error re-render with
    `error` and the submitted values, on success call `create_expense()`
    with `user["id"]` from the session-backed user row, flash, redirect.
- `database/db.py` — add `create_expense()`.
- `templates/profile.html` — "Add expense" link.
- `static/css/profile.css` — style/placement for the "Add expense" link if
  the existing `btn-primary` class isn't enough.
- `CLAUDE.md` — routes table: `GET /expenses/add` → Implemented (and add
  `POST /expenses/add`); add `create_expense()` to the list of existing
  `db.py` helpers.

## Files to create
- `templates/add_expense.html` — the add-expense form page.
- `static/css/expense_form.css` — form-page styles (reusable by Step 8's
  edit form), CSS variables only.
- `tests/test_add_expense.py` — pytest tests using the existing
  `conftest.py` fixtures (`app`, `client`, autouse `fresh_db`) and
  `tests/helpers.py`. Assertions read the DB via `get_db()` with
  parameterised queries.

## New dependencies
No new dependencies. Standard library `datetime` and `math` only.

## Rules for implementation
- No SQLAlchemy or ORMs.
- Parameterised queries only (`?` placeholders) — never f-strings, `%`,
  `+` or `.format()` in SQL.
- Passwords hashed with werkzeug. This step never reads or renders
  `password_hash`.
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- All SQL lives in `database/db.py`; validation lives in the
  `validate_expense()` helper in `app.py`, not in the route body or template.
- The expense's `user_id` always comes from the session-backed user row —
  never from a form field or query string. The form has no `user_id` input.
- Categories come from `CATEGORIES` in `database/db.py`; don't duplicate the
  list in `app.py` or hardcode it in the template.
- Server-side validation is authoritative — HTML `required` / `min` / `max`
  attributes are convenience only.
- Every internal link and form action uses `url_for()`.
- Currency is INR (₹) everywhere — labels, flash messages, tests. Never `$`.
- No JavaScript required; the form is a plain `POST` form.
- Use `abort()` for HTTP errors; never return bare error strings.
- Do not implement or link to `/expenses/<id>/edit` or
  `/expenses/<id>/delete`.

## Definition of done
- [ ] Signed out, `GET /expenses/add` and `POST /expenses/add` both redirect (302) to `/login` and no row is inserted.
- [ ] Signed in as `demo@spendly.com` / `demo123`, `GET /expenses/add` returns 200 and shows Amount (₹), Category, Date and Description fields plus an "Add expense" button.
- [ ] The category dropdown lists exactly Food, Transport, Bills, Health, Entertainment, Shopping, Other.
- [ ] The date field defaults to today's date.
- [ ] `/profile` shows an "Add expense" link pointing to `/expenses/add`.
- [ ] Submitting `amount=250`, `category=Food`, today's date, `description=Lunch` redirects to `/profile`, shows "Expense added.", and the profile now shows `₹6,599.00` total and `9` transactions with "Lunch" at the top of the recent table.
- [ ] The new row in `expenses` has the demo user's `user_id`, `amount` 250.0, `category` Food, and the submitted date.
- [ ] Submitting with a blank description stores `NULL`, not an empty string.
- [ ] Each of these re-renders the form (200) with an inline error, keeps the other entered values, and inserts nothing: amount blank, `0`, `-5`, `abc`, `nan`, `inf`, above ₹1,00,00,000; category blank or `Crypto`; date blank, `2026-02-30`, `abc`, or tomorrow; description longer than 200 characters.
- [ ] An amount like `99.999` is stored rounded to `100.0`.
- [ ] Posting a `user_id` form field has no effect — the expense is still saved to the signed-in user.
- [ ] An expense added by one user never appears on another user's profile.
- [ ] A newly added expense respects the Step 6 date filter (appears only in ranges that include its date).
- [ ] No `$` appears on the add-expense page, and no hex colour appears in `expense_form.css` or new `profile.css` rules.
- [ ] `create_expense()` uses `?` placeholders only.
- [ ] `/expenses/<id>/edit` and `/expenses/<id>/delete` stubs are unchanged.
- [ ] `pytest` passes, including all Step 1–6 test files and `tests/test_add_expense.py`.
- [ ] `python app.py` starts on port 5001 without errors.
