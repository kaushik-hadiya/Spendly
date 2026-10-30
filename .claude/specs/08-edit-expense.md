# Spec: Edit Expense

## Overview
Step 7 gave signed-in users a way to record expenses, but a mistake — wrong
amount, wrong category, a typo in the description — is permanent. This step
replaces the `/expenses/<id>/edit` stub with a real edit form so a signed-in
user can correct one of their own expenses. The form is pre-filled with the
expense's current values, validated with the same `validate_expense()` rules
as Step 7, and on success the row is updated, a success flash is shown and
the user is redirected to `/profile`, where the stats, recent-transactions
table and category breakdown reflect the change. Each row in the profile's
recent-transactions table gets an "Edit" link. Users can only ever see or
change their own expenses — any other id is a 404. Delete stays a stub until
Step 9.

## Depends on
- **Step 1 — Database setup:** the `expenses` table and `CATEGORIES`.
- **Step 3 — Login and Logout:** `session["user_id"]`.
- **Step 4 — Profile Page Design:** `profile.html` / `profile.css` (the
  recent-transactions table gets an Edit column).
- **Step 5 — Backend Routes for Profile Page:** `get_recent_expenses()`
  already returns `id`, used to build the Edit links.
- **Step 7 — Add Expense:** `validate_expense()`, `EXPENSE_FIELDS`,
  `MAX_DESCRIPTION_LENGTH`, `csrf_token()` / `csrf_token_valid()`,
  `render_expense_form()`, `add_expense.html` and `expense_form.css`.

## Routes
- `GET /expenses/<int:id>/edit` — render the edit form pre-filled with the
  expense's current amount, category, date and description — logged-in
- `POST /expenses/<int:id>/edit` — validate the form, update the expense,
  flash "Expense updated.", redirect (302) to `/profile`; on invalid input
  re-render the form with an inline error, the submitted values and status
  200 — logged-in

Both methods share the existing `edit_expense` endpoint
(`@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])`),
replacing the raw string stub. Request handling order:

1. Login guard — signed out (or a session whose user no longer exists) on
   either method: flash "Please sign in to edit an expense." and redirect
   (302) to `/login`.
2. Load the expense scoped to the session user — if it doesn't exist **or**
   belongs to another user, `abort(404)` (same response for both, so ids of
   other users' expenses aren't revealed).
3. POST only: invalid/missing CSRF token → `abort(400)`.
4. POST only: `validate_expense(request.form)` → re-render on error, else
   update + flash + redirect.

Do not touch the `/expenses/<id>/delete` stub.

## Database changes
No schema changes.

Add two helpers to `database/db.py` (mirroring the style of
`create_expense()`):

- `get_expense_by_id(expense_id, user_id)` — `SELECT id, amount, category,
  date, description FROM expenses WHERE id = ? AND user_id = ?`; returns the
  row or `None`. Ownership is enforced in the query, not in the route.
- `update_expense(expense_id, user_id, amount, category, expense_date,
  description=None)` — parameterised `UPDATE ... WHERE id = ? AND user_id = ?`
  inside `with conn:`; `description` stored as `NULL` when empty; returns
  `cur.rowcount` (1 on success, 0 if no matching owned row).

## Templates
- **Create:**
  - `templates/_expense_form_fields.html` — partial containing the hidden
    CSRF input and the four field groups (amount, category, date,
    description) currently in `add_expense.html`, driven by `values`,
    `categories`, `today` and `max_description_length`. Not a page; it does
    not extend `base.html`.
  - `templates/edit_expense.html` — extends `base.html`, loads
    `expense_form.css` in `{% block head %}`. Heading "Edit expense",
    subtitle "Update this expense in ₹", inline `auth-error` block when
    `error` is set, a `POST` form with
    `action="{{ url_for('edit_expense', id=expense_id) }}"` that
    `{% include %}`s the partial, a "Cancel" link to `url_for('profile')`
    and a "Save changes" submit button.
- **Modify:**
  - `templates/add_expense.html` — replace the inline field markup with
    `{% include "_expense_form_fields.html" %}`. Rendered output and
    behaviour must be unchanged (existing Step 7 tests must still pass).
    `autofocus` on the amount field may stay add-only or apply to both.
  - `templates/profile.html` — add an empty-header actions column to the
    recent-transactions table; each row gets an "Edit" link to
    `url_for('edit_expense', id=e.id)`. Update the empty-state row's
    `colspan` from 4 to 5. All existing class names stay.

## Files to change
- `app.py`:
  - Import `get_expense_by_id` and `update_expense` from `database.db`.
  - Generalise `render_expense_form(values, error=None)` so it can render
    either template (e.g. add a `template="add_expense.html"` parameter and
    pass through extra context such as `expense_id`), rather than writing a
    second near-identical helper.
  - Replace the `edit_expense` stub with the GET/POST route described above.
    On GET, build `values` from the expense row (amount formatted as a plain
    number string like `450.00` — no ₹ or grouping commas, since it fills a
    `type="number"` input; description `None` → empty string). On POST
    error, re-render with `{field: request.form.get(field, "")}` for
    `EXPENSE_FIELDS`. On success call `update_expense()` with `user["id"]`
    from the session-backed user row.
- `database/db.py` — add `get_expense_by_id()` and `update_expense()`.
- `templates/add_expense.html` — use the shared partial.
- `templates/profile.html` — Edit links column.
- `static/css/profile.css` — style for the Edit link / actions cell (small,
  right-aligned, CSS variables only).
- `CLAUDE.md` — routes table: `GET /expenses/<id>/edit` → Implemented (and
  add `POST /expenses/<id>/edit`); add `get_expense_by_id()` and
  `update_expense()` to the list of existing `db.py` helpers.

## Files to create
- `templates/edit_expense.html` — the edit-expense page.
- `templates/_expense_form_fields.html` — shared form-fields partial.
- `tests/test_edit_expense.py` — pytest tests using the existing
  `conftest.py` fixtures and `tests/helpers.py`; DB assertions via
  `get_db()` with parameterised queries.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs.
- Parameterised queries only (`?` placeholders) — never f-strings, `%`,
  `+` or `.format()` in SQL.
- Passwords hashed with werkzeug. This step never reads or renders
  `password_hash`.
- Use CSS variables — never hardcode hex values.
- All page templates extend `base.html` (the `_expense_form_fields.html`
  partial is included, not rendered on its own).
- All SQL lives in `database/db.py`; validation reuses `validate_expense()`
  — do not duplicate the rules.
- Ownership is enforced in SQL (`WHERE id = ? AND user_id = ?`) for both
  the read and the update. `user_id` always comes from the session-backed
  user row, never from the form, query string or the expense row's id.
- Another user's expense and a nonexistent expense both return 404 via
  `abort(404)` — never 403, never a redirect that reveals existence.
- CSRF token required on POST (`csrf_token_valid()`); failure → `abort(400)`.
- Every internal link and form action uses `url_for()`.
- Currency is INR (₹) everywhere — labels, flash messages, tests. Never `$`.
- No JavaScript required; the form is a plain `POST` form.
- Do not implement or link to `/expenses/<id>/delete`.

## Definition of done
- [ ] Signed out, `GET` and `POST /expenses/1/edit` both redirect (302) to `/login` and the row is unchanged.
- [ ] Signed in as `demo@spendly.com` / `demo123`, every row in the profile's recent-transactions table has an "Edit" link to `/expenses/<id>/edit`.
- [ ] `GET /expenses/<id>/edit` for one of the demo user's expenses returns 200 with heading "Edit expense", the amount, category (selected), date and description pre-filled, and a "Save changes" button.
- [ ] Editing the seeded "Groceries at local market" expense from ₹450 to `500` redirects to `/profile`, shows "Expense updated.", and the profile shows `₹6,399.00` total with `8` transactions (count unchanged).
- [ ] Changing category, date and description persists all three; clearing the description stores `NULL`.
- [ ] Each invalid input from Step 7 (amount blank/`0`/`-5`/`abc`/`nan`/`inf`/over ₹1,00,00,000; category blank or `Crypto`; date blank/`2026-02-30`/`abc`/tomorrow; description over 200 chars) re-renders the edit form (200) with an inline error and the submitted values, and leaves the row unchanged.
- [ ] `GET` or `POST` to `/expenses/<id>/edit` for another user's expense returns 404 and the row is unchanged.
- [ ] `GET` or `POST` to `/expenses/99999/edit` returns 404.
- [ ] `POST` without a valid `csrf_token` returns 400 and the row is unchanged.
- [ ] Posting a `user_id` form field has no effect — the expense stays with its owner.
- [ ] An edited expense moves in/out of Step 6 date-filter ranges according to its new date.
- [ ] `/expenses/add` still works exactly as in Step 7 (all `tests/test_add_expense.py` tests pass).
- [ ] No `$` appears on the edit page, and no hex colour appears in new CSS rules.
- [ ] `get_expense_by_id()` and `update_expense()` use `?` placeholders only.
- [ ] `/expenses/<id>/delete` stub is unchanged.
- [ ] `pytest` passes, including all earlier test files and `tests/test_edit_expense.py`.
- [ ] `python app.py` starts on port 5001 without errors.
