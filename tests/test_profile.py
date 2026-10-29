import os
import re
from datetime import date

import pytest

from app import format_inr, initials, member_since, short_date

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
PROFILE_CSS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static", "css", "profile.css",
)


def login(client, email=DEMO_EMAIL, password=DEMO_PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def sign_in_as_demo(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["user_name"] = "Demo User"


def profile_html(client):
    sign_in_as_demo(client)
    return client.get("/profile").get_data(as_text=True)


def test_signed_out_user_is_redirected_to_login(client):
    response = client.get("/profile")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    page = client.get("/login").get_data(as_text=True)
    assert "Please sign in to view your profile." in page
    assert "auth-error" in page


def test_demo_login_lands_on_profile(client):
    response = login(client)
    assert response.headers["Location"].endswith("/profile")

    response = client.get("/profile")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "coming in Step 4" not in html
    assert "Demo User" in html
    assert DEMO_EMAIL in html
    assert '<div class="profile-avatar">DU</div>' in html
    assert "Member since " in html


def test_registered_user_sees_own_details(client):
    client.post(
        "/register",
        data={
            "name": "Asha Verma",
            "email": "asha@example.com",
            "password": "securepass1",
            "confirm_password": "securepass1",
        },
    )
    login(client, email="asha@example.com", password="securepass1")
    html = client.get("/profile").get_data(as_text=True)

    assert "Asha Verma" in html
    assert "asha@example.com" in html
    assert '<div class="profile-avatar">AV</div>' in html
    assert "Demo User" not in html
    assert DEMO_EMAIL not in html


def test_stale_session_is_cleared(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 999
        sess["user_name"] = "Ghost"

    response = client.get("/profile")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert "user_id" not in sess
        assert "user_name" not in sess


def test_stats_render_in_inr(client):
    html = profile_html(client)

    assert "Total spent" in html
    assert "₹6,349.00" in html
    assert '<span class="stat-value">8</span>' in html
    assert '<span class="stat-value">Shopping</span>' in html
    assert "$" not in html


def test_recent_transactions_table(client):
    html = profile_html(client)

    for heading in ("Date", "Description", "Category", "Amount"):
        assert f">{heading}</th>" in html
    assert "Electricity bill" in html
    assert "₹1,850.00" in html
    assert "<td>—</td>" in html
    assert html.count('class="category-pill category-') == 8
    assert 'class="category-pill category-bills">Bills<' in html
    # The seed's newest expense is always dated today.
    today = date.today().isoformat()
    assert f'<td class="txn-date">{short_date(today)}</td>' in html
    # Table dates use short_date; raw ISO dates may still appear in filter links.
    assert not re.search(r'<td class="txn-date">\d{4}-\d{2}-\d{2}</td>', html)


def test_category_bars_match_share_of_total(client):
    html = profile_html(client)
    widths = [float(w) for w in re.findall(r'class="cat-bar category-\w+" style="width: ([\d.]+)%"', html)]

    assert len(widths) == 7
    assert widths[0] == 39.4  # Shopping: 2499 / 6349
    assert widths == sorted(widths, reverse=True)
    assert sum(widths) == pytest.approx(100, abs=0.5)


def test_each_category_has_its_own_colour(client):
    html = profile_html(client)
    with open(PROFILE_CSS, encoding="utf-8") as f:
        css = f.read()

    bar_classes = re.findall(r'class="cat-bar (category-\w+)"', html)
    assert len(set(bar_classes)) == 7
    for cls in bar_classes:
        assert f".{cls} " in css


def test_profile_never_exposes_password_hash(client):
    html = profile_html(client)

    assert "password_hash" not in html
    assert "scrypt:" not in html
    assert "pbkdf2:" not in html


def test_profile_uses_base_layout_and_own_stylesheet(client):
    html = profile_html(client)

    assert "<title>Profile — Spendly</title>" in html
    assert 'class="navbar"' in html
    assert "css/profile.css" in html


def test_profile_css_has_no_hex_colours():
    with open(PROFILE_CSS, encoding="utf-8") as f:
        css = f.read()

    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)


def test_navbar_name_links_to_profile(client):
    html = profile_html(client)
    assert '<a href="/profile" class="nav-user">Demo User</a>' in html


@pytest.mark.parametrize(
    "amount, expected",
    [
        (0, "₹0.00"),
        (450, "₹450.00"),
        (6349, "₹6,349.00"),
        (100000, "₹1,00,000.00"),
        (12345678.5, "₹1,23,45,678.50"),
        (-2499, "-₹2,499.00"),
    ],
)
def test_inr_uses_indian_grouping(amount, expected):
    assert format_inr(amount) == expected


@pytest.mark.parametrize(
    "name, expected",
    [("Demo User", "DU"), ("asha", "A"), ("Ravi Kumar Singh", "RS"), ("", "?"), (None, "?")],
)
def test_initials(name, expected):
    assert initials(name) == expected


@pytest.mark.parametrize(
    "created_at, expected",
    [("2026-10-29 08:15:00", "Oct 2026"), (None, ""), ("not a date", "")],
)
def test_member_since(created_at, expected):
    assert member_since(created_at) == expected


@pytest.mark.parametrize(
    "iso_date, expected",
    [("2026-10-29", "29 Oct, 2026"), ("2026-10-01", "1 Oct, 2026"), (None, ""), ("bad", "bad")],
)
def test_short_date(iso_date, expected):
    assert short_date(iso_date) == expected
