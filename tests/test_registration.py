import os

from werkzeug.security import check_password_hash

import database.db as db

VALID_FORM = {
    "name": "Asha Verma",
    "email": "asha@example.com",
    "password": "securepass1",
    "confirm_password": "securepass1",
}


def count_users():
    conn = db.get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


def test_register_page_renders(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert b'action="/register"' in response.data


def test_valid_registration_creates_user_and_redirects(client):
    response = client.post("/register", data=VALID_FORM)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    user = db.get_user_by_email("asha@example.com")
    assert user is not None
    assert user["name"] == "Asha Verma"
    assert user["password_hash"] != VALID_FORM["password"]
    assert check_password_hash(user["password_hash"], VALID_FORM["password"])


def test_success_message_shown_on_login(client):
    response = client.post("/register", data=VALID_FORM, follow_redirects=True)

    assert response.status_code == 200
    assert "Account created — please sign in." in response.get_data(as_text=True)
    assert b"auth-success" in response.data


def test_duplicate_seed_email_rejected(client):
    before = count_users()
    response = client.post(
        "/register", data={**VALID_FORM, "email": "demo@spendly.com"}
    )

    assert response.status_code == 200
    assert b"An account with that email already exists." in response.data
    assert count_users() == before


def test_email_is_normalised(client):
    client.post("/register", data={**VALID_FORM, "email": "  Foo@Example.com "})
    assert db.get_user_by_email("foo@example.com") is not None

    before = count_users()
    response = client.post("/register", data={**VALID_FORM, "email": "foo@example.com"})

    assert b"An account with that email already exists." in response.data
    assert count_users() == before


def test_empty_name_rejected(client):
    before = count_users()
    response = client.post("/register", data={**VALID_FORM, "name": "   "})

    assert response.status_code == 200
    assert b"Please enter your name." in response.data
    assert count_users() == before


def test_invalid_email_rejected(client):
    before = count_users()
    response = client.post("/register", data={**VALID_FORM, "email": "not-an-email"})

    assert response.status_code == 200
    assert b"Please enter a valid email address." in response.data
    assert count_users() == before


def test_short_password_rejected(client):
    before = count_users()
    response = client.post("/register", data={**VALID_FORM, "password": "short12"})

    assert response.status_code == 200
    assert b"Password must be at least 8 characters." in response.data
    assert count_users() == before


def test_register_page_has_confirm_password_field(client):
    response = client.get("/register")
    assert b'name="confirm_password"' in response.data


def test_mismatched_passwords_rejected(client):
    before = count_users()
    response = client.post(
        "/register", data={**VALID_FORM, "confirm_password": "differentpass"}
    )

    assert response.status_code == 200
    assert b"Passwords do not match." in response.data
    assert count_users() == before


def test_missing_confirm_password_rejected(client):
    form = {k: v for k, v in VALID_FORM.items() if k != "confirm_password"}
    before = count_users()
    response = client.post("/register", data=form)

    assert b"Passwords do not match." in response.data
    assert count_users() == before


def test_form_keeps_name_and_email_but_not_passwords(client):
    response = client.post(
        "/register",
        data={**VALID_FORM, "password": "mismatch01", "confirm_password": "mismatch02"},
    )
    html = response.get_data(as_text=True)

    assert 'value="Asha Verma"' in html
    assert 'value="asha@example.com"' in html
    assert "mismatch01" not in html
    assert "mismatch02" not in html


def test_tests_do_not_use_real_database():
    assert os.path.basename(db.DB_PATH) == "test.db"
