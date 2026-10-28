# Spec: Login and Logout

## Overview
Make sign-in and sign-out work. Right now `GET /login` renders a form whose
`action` already points at `url_for('login')`, but the route only accepts GET,
so submitting it returns 405. `/logout` is a raw-string stub. This step adds a
`POST /login` handler that looks the user up by email, checks the password
against the stored werkzeug hash, and on success stores the user in Flask's
signed `session` cookie. It turns `GET /logout` into a real handler that
clears the session. The navbar in `base.html` changes based on whether
someone is signed in. Step 2 created accounts but never signed anyone in.
This step gives Spendly a logged-in user, which Step 4 (profile) and the
expense steps (7–9) need.

## Depends on
- **Step 1 — Database setup:** `get_db()`, the `users` table, and the seeded
  demo user (`demo@spendly.com` / `demo123`).
- **Step 2 — Registration:** `get_user_by_email(email)` in `database/db.py`,
  `app.secret_key` (needed for `session` and `flash`), the flash rendering
  and `.auth-success` / `.auth-error` styles in `login.html`, and the
  redirect to `/login` after sign-up.

## Routes
- `GET /login` — renders the sign-in form (exists already; keep it). If the
  user is already signed in, redirect to `url_for('profile')` — public
- `POST /login` — validates credentials. On success, clears and sets the
  session, then redirects to `url_for('profile')`. On failure, re-renders
  `login.html` with status 200, an error, and the submitted email — public
- `GET /logout` — clears the session, flashes "You have been signed out.",
  and redirects to `url_for('login')`. Safe to call when not signed in —
  public

`GET` and `POST /login` are both handled by the existing `login()` view
(`methods=["GET", "POST"]`). Replace the body of the existing `logout()` stub.
Do not add new view functions.

`GET /register` also redirects to `url_for('profile')` when the user is
already signed in. `POST /register` is unchanged.

`/profile` stays a Step 4 stub. It is only used here as the redirect
target. Do not implement it.

## Database changes
No database changes. The `users` table already has `id`, `name`, `email` and
`password_hash`, and `get_user_by_email()` already exists. No new `db.py`
helpers are needed.

## Templates
- **Create:** none
- **Modify:**
  - `templates/login.html`:
    - Keep the submitted email after a failed attempt
      (`value="{{ email or '' }}"`). Never refill the password.
    - Existing flash and `error` rendering stays as is.
  - `templates/base.html` — make the navbar depend on the session:
    - Signed out (`session.get('user_id')` is falsy): keep the current
      "Sign in" and "Get started" links.
    - Signed in: show the user's name (`session['user_name']`) and a
      "Sign out" link to `url_for('logout')`, styled with the existing
      `nav-cta` class. Hide "Sign in" and "Get started".

## Files to change
- `app.py`:
  - Import `session` from flask and `check_password_hash` from
    `werkzeug.security`.
  - `login()` accepts GET and POST (see Routes and Rules).
  - `logout()` stops returning a raw string and does the work described
    above.
  - `register()` GET redirects signed-in users to `url_for('profile')`.
- `templates/login.html` — keep the email value after errors.
- `templates/base.html` — navbar depends on the session.
- `CLAUDE.md` — in the routes table, mark `POST /login` and `GET /logout`
  as implemented.

## Files to create
- `tests/test_login_logout.py` — pytest tests for login and logout. Use the
  existing `conftest.py` fixtures (`app`, `client` from pytest-flask, and the
  autouse `fresh_db` temp database) so tests never touch
  `expense_tracker.db`.

## New dependencies
No new dependencies. `session` is part of Flask, and `check_password_hash`
comes from werkzeug, which is already in `requirements.txt`.

## Rules for implementation
- No SQLAlchemy or ORMs. User lookup goes through `get_user_by_email()` only.
- Parameterised queries only (`?` placeholders). No f-strings in SQL.
- Passwords hashed with werkzeug. Verify with `check_password_hash`. Never
  compare plain strings, and never store, log, flash or echo the password.
- Use CSS variables. Never hardcode hex values. No new CSS should be
  needed. Any new rule may use only existing variables.
- All templates extend `base.html`.
- No DB logic in `app.py`.
- Use `url_for()` for every internal link, form action and redirect.
- Login input handling:
  - `email`: `.strip().lower()`, the same as registration, so
    `Demo@Spendly.com ` matches `demo@spendly.com`.
  - `password`: never stripped.
  - Either field empty → "Please enter your email and password."
  - Unknown email, or the wrong password → the same message for both:
    "Invalid email or password." Never say which one was wrong.
  - Do not enforce the 8-character minimum at login. The seeded demo
    password `demo123` is 7 characters and must still work.
- On success: call `session.clear()` first (this stops session fixation),
  then set `session["user_id"] = user["id"]` and
  `session["user_name"] = user["name"]`. Never put the password hash in the
  session.
- Use Post/Redirect/Get. A successful POST always redirects and never
  renders a template.
- Logout uses `session.clear()` and then a flash with the `"success"`
  category, so it shows in the existing `.auth-success` box on the login
  page.
- Do not add login-required guards to the stub routes. Access control for
  `/profile` and `/expenses/*` belongs to the steps that implement them.
- Vanilla JS only. No JS is needed for this step.

## Definition of done
- [ ] Submitting the sign-in form no longer returns 405.
- [ ] Signing in as `demo@spendly.com` / `demo123` redirects (302) to `/profile`, and the session holds `user_id` and `user_name`.
- [ ] The email is normalised: ` Demo@Spendly.com ` with `demo123` signs in successfully.
- [ ] A wrong password re-renders the login page (200) with "Invalid email or password.", and no `user_id` is put in the session.
- [ ] An unknown email shows exactly the same "Invalid email or password." message.
- [ ] An empty email or password shows "Please enter your email and password."
- [ ] After a failed attempt the email field keeps its value and the password field is empty.
- [ ] A user registered through `/register` can then sign in with the same credentials.
- [ ] When signed in, the navbar shows the user's name and a "Sign out" link, and hides "Sign in" and "Get started".
- [ ] When signed out, the navbar shows "Sign in" and "Get started" as before.
- [ ] Visiting `/login` or `/register` while signed in redirects to `/profile`.
- [ ] `GET /logout` clears the session, redirects (302) to `/login`, and the login page shows "You have been signed out."
- [ ] `GET /logout` while signed out still redirects to `/login` without an error.
- [ ] `/logout` no longer returns a raw string.
- [ ] `/profile` and the expense routes are still the unchanged stubs.
- [ ] `pytest` passes, including `tests/test_login_logout.py` and the existing `tests/test_registration.py`, and the tests do not modify `expense_tracker.db`.
- [ ] `python app.py` starts on port 5001 without errors.
