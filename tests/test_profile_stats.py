import re

from database.db import (
    get_category_totals,
    get_expense_summary,
    get_recent_expenses,
)
from helpers import (
    DEMO_USER_ID,
    add_expense,
    register_and_login,
    sign_in_as_demo,
    txn_rows,
)


# ------------------------------------------------------------------ #
# DB helpers                                                          #
# ------------------------------------------------------------------ #

def test_summary_helper_matches_seed():
    summary = get_expense_summary(DEMO_USER_ID)

    assert summary["total"] == 6349.0
    assert summary["count"] == 8


def test_summary_helper_for_user_without_expenses():
    summary = get_expense_summary(999)

    assert summary["total"] == 0
    assert summary["count"] == 0


def test_recent_orders_newest_first():
    add_expense(DEMO_USER_ID, 10, "Food", "2099-01-02", "Later")
    add_expense(DEMO_USER_ID, 10, "Food", "2099-01-01", "Earlier")
    add_expense(DEMO_USER_ID, 10, "Food", "2099-01-02", "Later, inserted last")

    rows = get_recent_expenses(DEMO_USER_ID, limit=3)

    assert [r["description"] for r in rows] == ["Later, inserted last", "Later", "Earlier"]


def test_category_totals_ordered_by_amount():
    rows = get_category_totals(DEMO_USER_ID)
    amounts = [r["amount"] for r in rows]

    assert rows[0]["category"] == "Shopping"
    assert amounts == sorted(amounts, reverse=True)
    assert len(rows) == 7
    assert dict((r["category"], r["amount"]) for r in rows)["Food"] == 730.0


def test_category_totals_empty_for_user_without_expenses():
    assert get_category_totals(999) == []


# ------------------------------------------------------------------ #
# /profile with real data                                             #
# ------------------------------------------------------------------ #

def test_new_expense_changes_profile(client):
    add_expense(DEMO_USER_ID, 1000, "Bills", "2099-01-01", "Internet bill")
    sign_in_as_demo(client)
    html = client.get("/profile").get_data(as_text=True)

    assert "₹7,349.00" in html
    assert '<span class="stat-value">9</span>' in html
    assert "Internet bill" in html


def test_new_user_sees_empty_state(client):
    register_and_login(client, "Asha Verma", "asha@example.com")
    response = client.get("/profile")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<span class="stat-value">₹0.00</span>' in html
    assert '<span class="stat-value">0</span>' in html
    assert '<span class="stat-value">—</span>' in html
    assert "No expenses yet." in html
    assert "No spending to show yet." in html
    assert "cat-bar" not in html
    assert "category-pill" not in html


def test_users_never_see_each_others_expenses(client):
    asha_id = register_and_login(client, "Asha Verma", "asha@example.com")
    add_expense(asha_id, 999, "Health", "2099-01-01", "Asha dentist visit")
    add_expense(DEMO_USER_ID, 777, "Food", "2099-01-01", "Demo team lunch")

    html = client.get("/profile").get_data(as_text=True)
    assert "Asha dentist visit" in html
    assert "₹999.00" in html
    assert "Demo team lunch" not in html
    assert "Electricity bill" not in html
    assert '<span class="stat-value">1</span>' in html

    sign_in_as_demo(client)
    html = client.get("/profile").get_data(as_text=True)
    assert "Demo team lunch" in html
    assert "Asha dentist visit" not in html


def test_recent_limited_to_ten_but_totals_count_all(client):
    for day in range(1, 8):
        add_expense(DEMO_USER_ID, 100, "Food", f"2099-01-{day:02d}", f"Extra {day}")
    sign_in_as_demo(client)
    html = client.get("/profile").get_data(as_text=True)

    assert len(txn_rows(html)) == 10
    assert '<span class="stat-value">15</span>' in html
    assert "₹7,049.00" in html
    assert "Extra 7" in html


def test_signed_out_still_redirects(client):
    response = client.get("/profile")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
