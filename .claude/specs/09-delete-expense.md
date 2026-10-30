# Spec: Delete Expense

## Overview
Steps 7 and 8 let a signed-in user add and correct expenses, but there is
still no way to remove one that was recorded by mistake or is a duplicate.
This step replaces the `/expenses/<id>/delete` raw-string stub with a real
two-step delete: `GET` shows a confirmation page summarising the expense
(amount in ₹, category, date, description), and `POST` (CSRF-protected)
permanently deletes it, flashes "Expense deleted." and redirects to
`/profile`, where the stats, recent-transactions table and category
breakdown reflect the removal. The delete happens only on `POST` so that a
link prefetch, crawler or forged cross-site `<img>` can never destroy data.
Each row in the profile's recent-transactions table gets a "Delete" link
next to the existing "Edit" link. Users can only ever see or delete their
own expenses — any other id is a 404. This completes the expense CRUD
cycle on the Spendly roadmap.

## Depends on
- **Step 1 — Database setup:** the `expenses` table.
- **Step 3 — Login and Logout:** `session["user_id"]`.
- **Step 4 — Profile Page Design:** `profile.html` / `profile.css`
  (recent-transactions table and its `txn-actions` cell).
- **Step 5 — Backend Routes for Profile Page:** `get_recent_expenses()`
  returns `id`, used to build the Delete links.
- **Step 7 — Add Expense:** `csrf_token()` / `csrf_token_valid()`,
  `expense_form.css` (auth-card / form-actions / `btn-ghost` styles).
- **Step 8 — Edit Expense:** `get_expense_by_id(expense_id, user_id)`,
  the ownership-404 pattern, and the Edit link in the `txn-actions` cell.

## Routes
- `GET /expenses/<int:id>/delete` — render a confirmation page showing the
  expense's amount (`|inr`), category, date (`|short_date`) and
  description, with a "Cancel" link and a "Delete expense" submit button —
  logged-in
- `POST /expenses/<int:id>/delete` — delete the expense, flash
  "Expense deleted.", redirect (302) to `/profile` — logged-in

Both methods share the existing `delete_expense` endpoint
(`@app.route("/expenses/<int:id>/delete", methods=["GET", "POST"])`),
replacing the raw string stub. Request handling order (mirrors
`edit_expense`):

1. Login guard — signed out (or a session whose user no longer exists) on
   either method: flash "Please sign in to delete an expense." and redirect
   (302) to `/login`.
2. POST only: invalid/missing CSRF token → `abort(400)` before touching the
   DB.
3. Load the expense via `get_expense_by_id(id, user["id"])` — if it doesn't
   exist **or** belongs to another user, `abort(404)` (same response for
   both, so other users' ids aren't revealed).
4. GET: render `delete_expense.html` with the expense.
5. POST: `delete_expense_by_id(id, user["id"])`; if it returns 0 (row
   vanished between read and write, e.g. deleted in another tab) →
   `abort(404)`; otherwise flash "Expense deleted." and redirect to
   `/profile`.

Note: the route function is already named `delete_expense`, so the DB
helper must use a different name (`delete_expense_by_id`) to avoid
shadowing the import in `app.py`.

## Database changes
No schema changes.

Add one helper to `database/db.py` (mirroring the style of
`update_expense()`):

- `delete_expense_by_id(expense_id, user_id)` — parameterised
  `DELETE FROM expenses WHERE id = ? AND user_id = ?` inside `with conn:`;
  returns `cur.rowcount` (1 on success, 0 if no matching owned row).
  Ownership is enforced in the query, not in the route.

## Templates
- **Create:**
  - `templates/delete_expense.html` — extends `base.html`, loads
    `expense_form.css` (and `delete_expense.css` if extra styles are
    needed) in `{% block head %}`. Title "Delete expense — Spendly",
    heading "Delete expense", subtitle "This can't be undone." Inside the
    `auth-card`: a summary of the expense (amount via `|inr`, category
    pill, date via `|short_date`, description or "—"), then a `POST` form
    with `action="{{ url_for('delete_expense', id=expense.id) }}"`
    containing the hidden `csrf_token` input, a "Cancel" link
    (`btn-ghost`) to `url_for('profile')` and a "Delete expense" submit
    button styled as a danger button.
- **Modify:**
  - `templates/profile.html` — in each row's existing `txn-actions` cell,
    add a "Delete" link to `url_for('delete_expense', id=e.id)` (class
    `txn-delete`) after the Edit link. The column count stays 5; all
    existing class names stay.

## Files to change
- `app.py`:
  - Import `delete_expense_by_id` from `database.db`.
  - Replace the `delete_expense` stub with the GET/POST route described
    above, and move it out of the "Placeholder routes" section (remove the
    now-empty section header).
- `database/db.py` — add `delete_expense_by_id()`.
- `templates/profile.html` — Delete link in the actions cell.
- `static/css/profile.css` — style for `.txn-delete` (small, uses
  `var(--danger)`; spacing from the Edit link). CSS variables only.
- `CLAUDE.md` — routes table: `GET /expenses/<id>/delete` → Implemented
  (confirmation page) and add `POST /expenses/<id>/delete`; add
  `delete_expense_by_id()` to the list of existing `db.py` helpers.

## Files to create
- `templates/delete_expense.html` — the delete confirmation page.
- `static/css/delete_expense.css` — only if the summary block / danger
  button need styles beyond `expense_form.css` (use `var(--danger)`,
  `var(--danger-light)`, `var(--border)` etc.; no hex values).
- `tests/test_delete_expense.py` — pytest tests using the existing
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
- All templates extend `base.html`.
- All SQL lives in `database/db.py`; reuse `get_expense_by_id()` — do not
  write a second lookup helper.
- The delete only happens on `POST`. `GET` must never modify the DB.
- Ownership is enforced in SQL (`WHERE id = ? AND user_id = ?`) for both
  the read and the delete. `user_id` always comes from the session-backed
  user row, never from the form or query string.
- Another user's expense and a nonexistent expense both return 404 via
  `abort(404)` — never 403, never a redirect that reveals existence.
- CSRF token required on POST (`csrf_token_valid()`); failure →
  `abort(400)`.
- Every internal link and form action uses `url_for()`.
- Currency is INR (₹) everywhere — confirmation page, flash messages,
  tests. Never `$`.
- No JavaScript required (no `confirm()` dialogs) — the confirmation page
  is the confirmation step.
- Route function stays a thin handler: guard, fetch, render or delete,
  redirect.

## Definition of done
- [ ] Signed out, `GET` and `POST /expenses/1/delete` both redirect (302) to `/login` and the row still exists.
- [ ] Signed in as `demo@spendly.com` / `demo123`, every row in the profile's recent-transactions table has both an "Edit" link and a "Delete" link to `/expenses/<id>/delete`.
- [ ] `GET /expenses/<id>/delete` for one of the demo user's expenses returns 200 with heading "Delete expense", the amount in ₹ (e.g. `₹450.00`), category, date and description, a "Cancel" link to `/profile` and a "Delete expense" button — and the row still exists afterwards.
- [ ] Deleting the seeded "Groceries at local market" (₹450) expense via `POST` redirects to `/profile`, shows "Expense deleted.", and the profile shows `₹5,899.00` total with `7` transactions; the row is gone from the DB.
- [ ] Deleting an expense updates the category breakdown (e.g. deleting the only "Other" expense removes that category).
- [ ] `GET` or `POST` to `/expenses/<id>/delete` for another user's expense returns 404 and that row still exists.
- [ ] `GET` or `POST` to `/expenses/99999/delete` returns 404.
- [ ] `POST` a second time to an already-deleted id returns 404.
- [ ] `POST` without a valid `csrf_token` returns 400 and the row still exists.
- [ ] Posting a `user_id` form field has no effect — only the session user's expenses can be deleted.
- [ ] Deleting a user's last expense shows the profile empty state ("No expenses yet.") with ₹0.00 total.
- [ ] Add (`tests/test_add_expense.py`) and edit (`tests/test_edit_expense.py`) still pass unchanged.
- [ ] No `$` appears on the delete page, and no hex colour appears in new CSS rules.
- [ ] `delete_expense_by_id()` uses `?` placeholders only.
- [ ] `pytest` passes, including all earlier test files and `tests/test_delete_expense.py`.
- [ ] `python app.py` starts on port 5001 without errors.
