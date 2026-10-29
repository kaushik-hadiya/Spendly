# Spec: Date Filter for Profile Page

## Overview
After Step 5, `GET /profile` shows real stats, but always for every expense
the user has ever recorded. This step adds a date-range filter to the profile
page so a user can answer "how much did I spend this month?" or "what did I
spend on between two dates?". A small filter bar above the stat tiles offers
preset ranges (This month, Last 30 days, All time) and a custom From / To
date form. The selected range is carried in the query string
(`/profile?start=YYYY-MM-DD&end=YYYY-MM-DD`), so filtered views can be
bookmarked and reloaded. The range applies to everything below the user
card: Total spent, Transactions, Top category, the recent-transactions table
and the spending-by-category breakdown. The page works without JavaScript
because the filter is a plain `GET` form and plain links. Steps 7–9 (add,
edit and delete expenses) will show up inside whatever range is selected,
with no extra work.

## Depends on
- **Step 1 — Database setup:** the `expenses` table, whose `date` column
  stores ISO `YYYY-MM-DD` text, so lexical comparison is chronological.
- **Step 3 — Login and Logout:** `session["user_id"]`.
- **Step 4 — Profile Page Design:** `profile.html`, `profile.css`, the
  `inr` / `short_date` filters.
- **Step 5 — Backend Routes for Profile Page:** `get_expense_summary()`,
  `get_recent_expenses()`, `get_category_totals()` and
  `build_profile_stats()`.

## Routes
- `GET /profile` — same access guard as Steps 4–5. Now also reads the
  optional query parameters `start` and `end` (each `YYYY-MM-DD`). Any of
  these is valid: neither (all time, the default), only `start`, only `end`,
  or both. The stats, table and category breakdown are limited to expenses
  with `start <= date <= end` (both bounds inclusive) — logged-in

No new routes. Do not touch the `/expenses/*` stubs.

**Invalid input never causes a 500 or a 400.** If `start` or `end` is not a
real `YYYY-MM-DD` date (e.g. `2026-13-01`, `abc`, `2026-02-30`), or `start`
is after `end`, ignore the whole filter, show all-time data, and render an
inline error message in the filter bar (e.g. "Invalid date range — showing
all time."). Empty strings (`?start=&end=`, as submitted by a blank form)
count as "not provided", not as invalid.

## Database changes
No schema changes.

Extend the three existing Step 5 helpers in `database/db.py` with optional
keyword arguments `start_date=None, end_date=None` instead of adding new
helpers:

- `get_expense_summary(user_id, start_date=None, end_date=None)`
- `get_recent_expenses(user_id, limit=10, start_date=None, end_date=None)`
- `get_category_totals(user_id, start_date=None, end_date=None)`

Each query gains the same fixed clause, so the SQL text never changes
shape and nothing is concatenated:

```sql
WHERE user_id = ?
  AND (? IS NULL OR date >= ?)
  AND (? IS NULL OR date <= ?)
```

with parameters `(user_id, start_date, start_date, end_date, end_date, ...)`.
Called with no dates, each helper returns exactly what it does today, so
existing callers and the Step 5 tests are unaffected.

## Templates
- **Create:** none.
- **Modify:**
  - `templates/profile.html`:
    - Add a filter bar between the user card and the stat grid:
      - Preset links built with `url_for('profile', start=..., end=...)`:
        **This month** (1st of the current month → today), **Last 30 days**
        (today − 29 days → today), **All time** (`url_for('profile')`, no
        params). The preset matching the current range gets an `active`
        class.
      - A `GET` form with `action="{{ url_for('profile') }}"`, two
        `<input type="date">` fields named `start` and `end` (pre-filled
        with the current range), and an **Apply** button.
      - The inline error message when the range was invalid.
    - Show the active range as a caption under the filter bar, e.g.
      "Showing 1 Oct, 2026 – 29 Oct, 2026" (using `short_date`), or
      "Showing all time" when unfiltered.
    - Empty-state text changes when a filter is active: "No expenses in this
      period." instead of "No expenses yet.".
    - All existing class names stay so `profile.css` and the Step 4–5 tests
      keep working.
  - `static/css/profile.css` — styles for the filter bar, preset links,
    active state, date inputs and error message, using existing CSS
    variables only.

## Files to change
- `database/db.py` — add `start_date` / `end_date` to the three helpers.
- `app.py`:
  - Add a module-level helper `parse_date_range(args)` that takes
    `request.args` and returns `(start_date, end_date, error)`. It parses
    with `datetime.strptime(value, "%Y-%m-%d")`, treats empty strings as
    `None`, and returns `(None, None, "<message>")` for any invalid input or
    `start > end`. Returns ISO strings, not `date` objects, so they pass
    straight into the SQL.
  - Add a helper `build_date_presets(today)` that returns the preset list
    (label, start, end) so the template doesn't do date arithmetic.
  - `build_profile_stats(user_id, start_date=None, end_date=None)` passes the
    range through to the three DB helpers. Its return shape is unchanged.
  - `profile()` stays "guard, fetch, render": parse the range, build stats
    and presets, render. Pass `start_date`, `end_date`, `filter_error` and
    `presets` to the template.
- `templates/profile.html` — filter bar, range caption, empty-state text.
- `static/css/profile.css` — filter bar styles.
- `CLAUDE.md` — routes table: `GET /profile` → add "supports optional
  `?start=` / `?end=` date filter". Note the new keyword arguments on the
  three `db.py` helpers.

## Files to create
- `tests/test_profile_date_filter.py` — pytest tests using the existing
  `conftest.py` fixtures (`app`, `client`, autouse `fresh_db`). Test setup
  inserts expenses with fixed, known dates via `get_db()` and parameterised
  queries so assertions don't depend on today's date (except the preset
  tests, which derive expected dates from `date.today()`).

## New dependencies
No new dependencies. Use the standard library `datetime` only.

## Rules for implementation
- No SQLAlchemy or ORMs.
- Parameterised queries only (`?` placeholders). Never build the `WHERE`
  clause with f-strings, `%`, `+` or `.format()` — use the fixed
  `(? IS NULL OR date >= ?)` form above.
- Passwords hashed with werkzeug. This step never reads or renders
  `password_hash`.
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- All SQL lives in `database/db.py`. Date parsing and preset arithmetic live
  in `app.py` helpers, not in the route body and not in the template.
- Every expense query stays scoped by `user_id` from the session-backed user
  row. Never read a user id from the query string.
- Date values reach SQL only after `parse_date_range()` has validated them.
  Raw `request.args` strings are never passed to a DB helper.
- Both bounds are inclusive.
- Every internal link and form action uses `url_for()`.
- Currency stays INR (₹) via the `inr` filter. Never `$`.
- No JavaScript. The filter is a plain `GET` form plus links.
- Do not implement `/expenses/add`, `/expenses/<id>/edit` or
  `/expenses/<id>/delete`, and do not link to them.

## Definition of done
- [ ] Signed in as `demo@spendly.com` / `demo123`, `/profile` with no query string shows the same all-time numbers as Step 5 (`₹6,349.00`, `8` transactions, top category `Shopping`).
- [ ] The filter bar shows **This month**, **Last 30 days** and **All time** links plus a From / To date form with an **Apply** button.
- [ ] Clicking **This month** loads `/profile?start=<YYYY-MM-01>&end=<today>`, highlights that preset, and shows the caption with that range.
- [ ] With expenses dated `2026-01-10` (₹100), `2026-02-15` (₹200) and `2026-03-20` (₹400), `/profile?start=2026-02-01&end=2026-02-28` shows Total `₹200.00`, `1` transaction, only the Feb row in the table, and only its category in the breakdown at 100%.
- [ ] Bounds are inclusive: `?start=2026-02-15&end=2026-02-15` includes the ₹200 expense.
- [ ] Only `start` given → everything on or after it; only `end` given → everything on or before it.
- [ ] Submitting the form with both fields blank shows all-time data and no error.
- [ ] `?start=2026-13-01`, `?start=abc`, `?end=2026-02-30` and `?start=2026-03-01&end=2026-02-01` each return 200, show all-time data, and display the invalid-range message.
- [ ] A range with no expenses shows `₹0.00`, `0`, "—" as top category, and "No expenses in this period." in both panels — no 500, no division by zero.
- [ ] The date inputs are pre-filled with the active range after applying a filter.
- [ ] Another user's expenses never appear in any filtered view.
- [ ] Signed-out users requesting `/profile?start=2026-01-01` are still redirected (302) to `/login`.
- [ ] No `$` appears anywhere on the page, and no hex colour is added to `profile.css`.
- [ ] Every modified query in `database/db.py` uses `?` placeholders only.
- [ ] `/expenses/*` stubs are unchanged.
- [ ] `pytest` passes, including all Step 1–5 test files and `tests/test_profile_date_filter.py`, on any calendar day.
- [ ] `python app.py` starts on port 5001 without errors.
