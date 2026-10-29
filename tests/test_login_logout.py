import pytest

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"


def login(client, email=DEMO_EMAIL, password=DEMO_PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def sign_in_as_demo(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["user_name"] = "Demo User"


def test_login_post_is_allowed(client):
    response = login(client)
    assert response.status_code != 405


def test_demo_login_sets_session_and_redirects(client):
    response = login(client)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")

    with client.session_transaction() as sess:
        assert sess["user_id"] == 1
        assert sess["user_name"] == "Demo User"
        assert "password_hash" not in sess


def test_login_normalises_email(client):
    response = login(client, email="  Demo@Spendly.com ")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")


def test_wrong_password_is_rejected(client):
    response = login(client, password="wrong-password")

    assert response.status_code == 200
    assert b"Invalid email or password." in response.data
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_unknown_email_gives_same_message(client):
    response = login(client, email="nobody@example.com")

    assert response.status_code == 200
    assert b"Invalid email or password." in response.data
    with client.session_transaction() as sess:
        assert "user_id" not in sess


@pytest.mark.parametrize(
    "email, password",
    [("", DEMO_PASSWORD), (DEMO_EMAIL, ""), ("", "")],
)
def test_empty_fields_are_rejected(client, email, password):
    response = login(client, email=email, password=password)

    assert response.status_code == 200
    assert b"Please enter your email and password." in response.data


def test_failed_login_keeps_email_but_not_password(client):
    response = login(client, password="wrong-password")
    html = response.get_data(as_text=True)

    assert 'value="demo@spendly.com"' in html
    assert "wrong-password" not in html
    password_input = html[html.index('id="password"'):]
    password_input = password_input[:password_input.index(">")]
    assert "value=" not in password_input


def test_registered_user_can_sign_in(client):
    client.post(
        "/register",
        data={
            "name": "Asha Verma",
            "email": "asha@example.com",
            "password": "securepass1",
            "confirm_password": "securepass1",
        },
    )

    response = login(client, email="asha@example.com", password="securepass1")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")
    with client.session_transaction() as sess:
        assert sess["user_name"] == "Asha Verma"


def test_navbar_when_signed_in(client):
    login(client)
    html = client.get("/").get_data(as_text=True)

    assert '<a href="/profile" class="nav-user">Demo User</a>' in html
    assert 'href="/logout" class="nav-cta">Sign out<' in html
    assert 'href="/login">Sign in<' not in html
    assert 'class="nav-cta">Get started<' not in html


def test_navbar_when_signed_out(client):
    html = client.get("/").get_data(as_text=True)

    assert 'href="/login">Sign in<' in html
    assert 'class="nav-cta">Get started<' in html
    assert "Sign out" not in html
    assert "nav-user" not in html


@pytest.mark.parametrize("path", ["/login", "/register"])
def test_signed_in_user_is_redirected_from_auth_pages(client, path):
    sign_in_as_demo(client)
    response = client.get(path)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")


def test_logout_clears_session_and_flashes(client):
    login(client)
    response = client.get("/logout")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert "user_id" not in sess
        assert "user_name" not in sess

    page = client.get("/login").get_data(as_text=True)
    assert "You have been signed out." in page
    assert "auth-success" in page


def test_logout_when_signed_out(client):
    response = client.get("/logout")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert b"coming in Step 3" not in response.data


def test_stub_routes_unchanged(client):
    assert client.get("/expenses/add").get_data(as_text=True) == "Add expense — coming in Step 7"
    assert client.get("/expenses/1/edit").get_data(as_text=True) == "Edit expense — coming in Step 8"
    assert client.get("/expenses/1/delete").get_data(as_text=True) == "Delete expense — coming in Step 9"


def test_login_clears_previous_session(client):
    with client.session_transaction() as sess:
        sess["stray"] = "value"

    login(client)

    with client.session_transaction() as sess:
        assert "stray" not in sess
        assert sess["user_id"] == 1
