# Spec: Backend Routes for Profile Page

## Overview
Step 4 built the profile page layout, but everything below the user card
still comes from `PLACEHOLDER_EXPENSES`, a hardcoded tuple in `app.py`. Every
user sees the demo user's ₹6,349.00 and eight transactions, including a
newly registered user who has spent nothing. This step wires `GET /profile`
to the database: the summary stats, the recent-transactions table and the
spending-by-category breakdown are all queried from the `expenses` table for
the signed-in user only. The template keeps its Step 4 structure and data
contract (`total`, `count`, `top_category`, `recent`, `categories`), and gains
empty states for users with no expenses. This is the first step that reads
the `expenses` table. Steps 7–9 (add, edit and delete expenses) write to the
same data, so their changes will show up on the profile.

## Depends on
- **Step 1 — Database setup:** the `expenses` table and the seeded demo
  expenses (8 rows, ₹6,349.00 total, dated from the 1st of the current
  month to today by `_seed_dates()`).
- **Step 3 — Login and Logout:** `session["user_id"]`.
- **Step 4 — Profile Page Design:** the guarded `profile()` route,
  `profile.html`, `profile.css`, the `inr` / `short_date` / `initials` /
  `member_since` filters, and `get_user_by_id()`.

## Routes
- `GET /profile` — same access guard as Step 4 (signed-out → flash and
  redirect to `/login`; stale `user_id` → clear session and redirect to
  `/login`). After the guard, fetch the signed-in user's real stats, recent
  transactions and category breakdown from the DB and render `profile.html`
  — logged-in

No new routes. Change only the body of the existing `profile()` view. Do not
touch the `/expenses/*` stubs.

## Database changes
No schema changes. `expenses` already has `user_id`, `amount`, `category`,
`date` and `description`.

New read-only helpers in `database/db.py`. Each one takes `user_id`, filters
with `WHERE user_id = ?`, and uses the same open / `try` / `finally:
conn.close()` pattern as `get_user_by_id()`:

- `get_expense_summary(user_id)` — one query using `COUNT(*)` and
  `COALESCE(SUM(amount), 0)`. Returns a row or dict with `total` (float) and
  `count` (int). A user with no expenses gets `total = 0`, `count = 0`.
- `get_recent_expenses(user_id, limit=10)` — `id, date, description,
  category, amount`, ordered by `date DESC, id DESC`, `LIMIT ?`.
- `get_category_totals(user_id)` — `category, SUM(amount) AS amount`,
  `GROUP BY category`, ordered by `amount DESC, category ASC`. Returns an
  empty list for a user with no expenses.

Do not add any other helpers. Do not add write helpers for expenses. Those
belong to Steps 7–9.

## Templates
- **Create:** none.
- **Modify:**
  - `templates/profile.html`:
    - Recent transactions: when `recent` is empty, render a single
      empty-state message (e.g. "No expenses yet.") in place of the table
      body. Keep the table markup unchanged when there are rows.
    - Spending by category: when `categories` is empty, render an
      empty-state message instead of the bar list.
    - Top category tile: shows "—" when the user has no expenses.
    - No other structural changes. Class names stay the same so
      `profile.css` and the Step 4 tests keep working.
  - `static/css/profile.css`: only add a style for the empty-state message
    if needed, using existing CSS variables.

## Files to change
- `database/db.py` — add the three helpers above.
- `app.py`:
  - Import the three new helpers.
  - Delete `PLACEHOLDER_EXPENSES` and `build_profile_placeholder()`.
  - Add a module-level helper `build_profile_stats(user_id)` that calls the
    three DB helpers and returns the same dict shape the template already
    uses: `total`, `count`, `top_category`, `recent` (list of dicts with
    `date`, `description`, `category`, `amount`), and `categories` (list of
    dicts with `name`, `amount`, `percent`). `percent` is
    `round(amount / total * 100, 1)`, and is only computed when `total > 0`
    (no division by zero). `top_category` is the first category's name, or
    `None` when there are none. This helper only shapes data and runs no SQL.
  - `profile()` calls `build_profile_stats(user["id"])` in place of
    `build_profile_placeholder()`.
- `templates/profile.html` — the empty states described above.
- `tests/test_profile.py` — the Step 4 tests hardcode the placeholder date
  `29 Oct, 2026`. Change the date assertions to derive from the seeded
  dates (`database.db._seed_dates()` or `date.today()`) so the suite passes
  on any day. The amount assertions (₹6,349.00, 8 transactions, Shopping at
  39.4%) should still hold because the seed uses the same amounts.
- `CLAUDE.md`:
  - Routes table: `GET /profile` → "Implemented — renders `profile.html`
    with the signed-in user's real expense stats; redirects signed-out
    users to `/login`".
  - Warnings section: add `get_expense_summary()`, `get_recent_expenses()`
    and `get_category_totals()` to the list of existing `db.py` helpers.

## Files to create
- `tests/test_profile_stats.py` — pytest tests for the real-data behaviour,
  using the existing `conftest.py` fixtures (`app`, `client`, autouse
  `fresh_db`). Test-only setup may insert rows with `get_db()` and
  parameterised queries.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs.
- Parameterised queries only (`?` placeholders). No f-strings or string
  concatenation in SQL, including for `LIMIT`.
- Passwords hashed with werkzeug. This step never reads, selects or renders
  `password_hash`.
- Use CSS variables. Never hardcode hex values.
- All templates extend `base.html`.
- All SQL lives in `database/db.py`. `app.py` only calls helpers and shapes
  their results.
- Every expense query is scoped by `user_id` taken from the session-backed
  user row. Never accept a user id from the query string or form.
- Aggregation (`SUM`, `COUNT`, `GROUP BY`) happens in SQL, not by loading
  all rows into Python and summing them.
- The `profile()` route stays "guard, fetch, render". All data shaping goes
  in `build_profile_stats()`.
- Currency stays INR (₹) via the existing `inr` filter. Never `$`.
- No JS changes. Vanilla JS only if any is ever needed.
- Do not implement `/expenses/add`, `/expenses/<id>/edit` or
  `/expenses/<id>/delete`. Do not add links or buttons pointing to them.
  Those are Steps 7–9.

## Definition of done
- [ ] `PLACEHOLDER_EXPENSES` and `build_profile_placeholder()` no longer exist in `app.py`.
- [ ] Signing in as `demo@spendly.com` / `demo123` shows Total spent `₹6,349.00`, Transactions `8` and Top category `Shopping`, all read from the DB.
- [ ] The demo user's recent-transactions table shows the 8 seeded expenses, newest first, with dates matching the seeded rows (current month, up to today), and "—" for the expense with no description.
- [ ] The category breakdown shows 7 bars, ordered by amount descending. Shopping is 39.4% and the widths add up to ~100%.
- [ ] Inserting a new expense for the demo user directly in the DB and reloading `/profile` changes the total, count and table without a code change.
- [ ] A freshly registered user sees `₹0.00`, `0` transactions, "—" as top category, and empty-state messages in both panels. No 500 and no division-by-zero error.
- [ ] Expenses belonging to one user never appear on another user's profile (tested with two users who each have expenses).
- [ ] When a user has more than 10 expenses, the table shows only the 10 most recent, but Total spent and Transactions count all of them.
- [ ] Signed-out and stale-session behaviour is unchanged from Step 4 (302 to `/login`).
- [ ] The page HTML contains no `password_hash`, and no `$` appears anywhere.
- [ ] Every new query in `database/db.py` uses `?` placeholders and filters on `user_id`.
- [ ] `/expenses/add`, `/expenses/<id>/edit` and `/expenses/<id>/delete` are still the unchanged stubs.
- [ ] `pytest` passes, including `tests/test_profile.py`, `tests/test_profile_stats.py`, `tests/test_login_logout.py` and `tests/test_registration.py`, on any calendar day, and the run does not modify `expense_tracker.db`.
- [ ] `python app.py` starts on port 5001 without errors.
