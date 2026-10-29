# Spec: Profile Page Design

## Overview
Replace the `/profile` raw-string stub with a real, signed-in-only profile
page. Step 3 already redirects every successful sign-in (and any signed-in
visit to `/login` or `/register`) to `/profile`, but that page still returns
"Profile page — coming in Step 4". This step is about **design**: it builds
the page layout and styling. That means a user info card, three summary stat
tiles, a recent-transactions table and a spending-by-category breakdown.
Everything except the user's name and email uses hardcoded placeholder data
defined in `app.py`. The layout is settled now, and a later step swaps the
placeholders for real per-user queries without touching the template
structure. The page also adds the first access-control guard in Spendly:
signed-out visitors are sent to `/login`.

## Depends on
- **Step 1 — Database setup:** `get_db()`, the `users` table, and the seeded
  demo user (`demo@spendly.com` / `demo123`).
- **Step 2 — Registration:** `app.secret_key`, the flash rendering pattern.
- **Step 3 — Login and Logout:** `session["user_id"]` and
  `session["user_name"]` set on sign-in, the session-aware navbar in
  `base.html`, and the redirects to `url_for('profile')`.

## Routes
- `GET /profile` — renders `profile.html` for the signed-in user. If
  `session.get("user_id")` is falsy, flash "Please sign in to view your
  profile." (category `"error"`) and redirect to `url_for('login')`. If the
  session's `user_id` no longer matches a row in `users` (for example, a
  stale cookie after the DB was reset), clear the session and redirect to
  `url_for('login')` — logged-in

Replace the body of the existing `profile()` stub. Do not add new view
functions. No other new routes.

## Database changes
No database changes. The `users` table already has `id`, `name`, `email`
and `created_at`.

One new read-only helper in `database/db.py`:
- `get_user_by_id(user_id)` — returns `id, name, email, created_at` for the
  user, or `None`. Never select `password_hash`. Parameterised query, same
  connection open/close pattern as `get_user_by_email()`.

## Templates
- **Create:**
  - `templates/profile.html` — extends `base.html`, title
    "Profile — Spendly". Loads `css/profile.css` via `{% block head %}`.
    Sections, top to bottom:
    1. **Flash messages**: same `get_flashed_messages(with_categories=true)`
       pattern as `login.html`.
    2. **User info card**: an avatar circle with the user's initials
       (first letter of the first and last word of `user.name`, uppercased,
       or one letter for a one-word name), the name, the email, and
       "Member since <Mon YYYY>" formatted from `user.created_at`.
    3. **Summary stats**: three tiles in a row: "Total spent",
       "Transactions", "Top category". Amounts formatted as INR, e.g.
       `₹6,349.00`.
    4. **Recent transactions**: a table with columns Date, Description,
       Category, Amount. Category shows as a small pill/badge. A missing
       description shows as "—". Amounts right-aligned in INR.
    5. **Spending by category**: one row per category with the name, the
       INR amount, and a horizontal bar whose width is the category's
       percentage of the total (set with an inline `style="width: N%"`;
       this is the only inline style allowed, and it carries data, not
       design).
    - The tiles and both lists must stack to a single column at the
      existing `600px` breakpoint.
- **Modify:**
  - `templates/base.html` — when signed in, make the navbar user name
    (`.nav-user`) a link to `url_for('profile')`. No other changes.

## Files to change
- `app.py`:
  - Import `get_user_by_id` from `database.db`.
  - Replace the `profile()` stub with the guarded handler described in
    Routes. The placeholder data (see Rules) is built by a module-level
    helper or constant, not inline in the route body, so the route stays
    "fetch data, render template, done".
- `database/db.py` — add `get_user_by_id(user_id)`.
- `templates/base.html` — navbar user name links to the profile.
- `static/css/style.css` — only if `.nav-user` needs a link style; use
  existing variables.
- `CLAUDE.md` — in the routes table, mark `GET /profile` as
  "Implemented — renders `profile.html` (placeholder stats); redirects
  signed-out users to `/login`".

## Files to create
- `templates/profile.html`
- `static/css/profile.css` — all profile page styles (the CLAUDE.md rule is
  that page-specific styles go in their own CSS file).
- `tests/test_profile.py` — pytest tests using the existing `conftest.py`
  fixtures (`app`, `client`, autouse `fresh_db`), so the tests never touch
  `expense_tracker.db`.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs.
- Parameterised queries only (`?` placeholders). No f-strings in SQL.
- Passwords hashed with werkzeug. This step never reads, selects or renders
  `password_hash`.
- Use CSS variables. Never hardcode hex values. Use only the variables
  already defined in `style.css` `:root` (`--accent`, `--accent-light`,
  `--paper-card`, `--border`, `--radius-md`, `--font-display`, etc.). If a
  new variable is truly needed, add it to `:root` in `style.css`, not in
  `profile.css`.
- All templates extend `base.html`.
- No DB logic in `app.py`. The user lookup goes through `get_user_by_id()`.
- `url_for()` for every internal link, stylesheet and redirect.
- No inline `<style>` tags. The only inline `style` attribute allowed is the
  category bar width.
- **Placeholder data:** user name and email come from the DB. Stats,
  recent transactions and category breakdown are hardcoded sample values
  that mirror the seeded demo expenses (same categories from
  `CATEGORIES`, same INR amounts, e.g. ₹1,850.00 electricity bill). Totals
  and percentages must add up correctly. Mark the constant with a comment
  saying a later step replaces it with real queries.
- **Currency:** INR (`₹`) everywhere, never `$`. Format amounts with
  thousands separators and 2 decimals. Do it in one place (a small Jinja
  filter registered in `app.py`, or values pre-formatted in the
  placeholder helper), not repeated ad hoc in the template.
- Initials and "Member since" formatting happen in Python or as a Jinja
  filter, not with JS.
- Vanilla JS only. No JS is needed for this step.
- Do not implement or guard `/expenses/*`. Those are Steps 7–9.
- Do not add an edit-profile form, password change or avatar upload. This
  step is display only.

## Definition of done
- [ ] Visiting `/profile` while signed out redirects (302) to `/login`, and the login page shows "Please sign in to view your profile."
- [ ] Signing in as `demo@spendly.com` / `demo123` lands on `/profile` with status 200 instead of the old raw string.
- [ ] The profile page shows the signed-in user's name, email, initials avatar ("DU" for Demo User) and a "Member since" date.
- [ ] A user registered through `/register` sees their own name and email on `/profile`, not the demo user's.
- [ ] A session whose `user_id` doesn't exist in `users` is cleared and redirected to `/login`, not a 500.
- [ ] Three stat tiles (Total spent, Transactions, Top category) render with INR amounts. No `$` appears anywhere on the page.
- [ ] The recent-transactions table shows Date, Description, Category and Amount, with "—" for a missing description.
- [ ] The category breakdown shows a bar per category, and the widths match each category's share of the total.
- [ ] The page HTML contains no `password_hash` or hash value.
- [ ] `profile.html` extends `base.html`, styles live in `static/css/profile.css`, and that file contains no hex colour values.
- [ ] At a viewport ≤ 600px, the stat tiles and sections stack into one column with no horizontal scroll.
- [ ] When signed in, the navbar user name links to `/profile`.
- [ ] `/expenses/add`, `/expenses/<id>/edit` and `/expenses/<id>/delete` are still the unchanged stubs.
- [ ] `pytest` passes, including `tests/test_profile.py`, `tests/test_login_logout.py` and `tests/test_registration.py`, and the run does not modify `expense_tracker.db`.
- [ ] `python app.py` starts on port 5001 without errors.
