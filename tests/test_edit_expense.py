import re
from datetime import date, timedelta

import pytest

from database.db import get_db
from helpers import (
    DEMO_USER_ID,
    GROCERIES,
    add_expense as insert_expense,
    attr,
    csrf_token_for,
    expense_count,
    fetch_row,
    groceries_id,
    input_tag,
    register_and_login,
    sign_in_as_demo,
    snapshot,
    txn_rows,
)

TODAY = date.today().isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
OLD_DATE = (date.today() - timedelta(days=40)).isoformat()
MISSING_ID = 99999


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def all_rows_except(expense_id):
    conn = get_db()
    try:
        return [
            tuple(r) for r in conn.execute(
                "SELECT id, user_id, amount, category, date, description "
                "FROM expenses WHERE id != ? ORDER BY id",
                (expense_id,),
            ).fetchall()
        ]
    finally:
        conn.close()


def latest_expense_id(user_id=None):
    conn = get_db()
    try:
        if user_id is None:
            row = conn.execute("SELECT MAX(id) AS m FROM expenses").fetchone()
        else:
            row = conn.execute(
                "SELECT MAX(id) AS m FROM expenses WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row["m"]
    finally:
        conn.close()


def edit_url(expense_id):
    return f"/expenses/{expense_id}/edit"


def valid_form(**overrides):
    data = {
        "amount": "500",
        "category": "Food",
        "date": TODAY,
        "description": "Edited description",
    }
    data.update(overrides)
    return data


def post_form(client, expense_id, data):
    return client.post(
        edit_url(expense_id),
        data={"csrf_token": csrf_token_for(client), **data},
    )


def select_options(html):
    select = re.search(
        r'<select\b[^>]*name="category"[^>]*>(.*?)</select>', html, re.DOTALL
    )
    assert select, "No category <select> found"
    return re.findall(r"<option\b([^>]*)>(.*?)</option>", select.group(1), re.DOTALL)


def selected_categories(html):
    return [
        attr(a, "value")
        for a, _ in select_options(html)
        if re.search(r"\bselected\b", a)
    ]


@pytest.fixture
def demo(client):
    sign_in_as_demo(client)
    return client


@pytest.fixture
def gid():
    return groceries_id()


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_get_signed_out_redirects_to_login(self, client, gid):
        response = client.get(edit_url(gid))
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")

    def test_post_signed_out_redirects_and_row_unchanged(self, client, gid):
        before = snapshot(gid)
        response = client.post(
            edit_url(gid),
            data={"csrf_token": csrf_token_for(client), **valid_form(amount="999")},
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")
        assert snapshot(gid) == before, "Signed-out POST must not change the row"

    def test_signed_out_redirect_flashes_sign_in_message(self, client, gid):
        response = client.get(edit_url(gid), follow_redirects=True)
        assert "Please sign in to edit an expense." in response.get_data(as_text=True)

    def test_signed_out_missing_id_redirects_rather_than_404(self, client):
        response = client.get(edit_url(MISSING_ID))
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")


# ------------------------------------------------------------------ #
# Profile Edit links                                                  #
# ------------------------------------------------------------------ #

class TestProfileEditLinks:
    def test_every_recent_row_has_edit_link(self, demo):
        html = demo.get("/profile").get_data(as_text=True)
        rows = txn_rows(html)
        assert len(rows) == 8
        links = re.findall(r'href="(/expenses/(\d+)/edit)"', html)
        assert len(links) == len(rows), "Each row needs exactly one Edit link"
        for href, expense_id in links:
            assert href == edit_url(int(expense_id))
            assert fetch_row(int(expense_id))["user_id"] == DEMO_USER_ID

    def test_groceries_row_links_to_its_edit_page(self, demo, gid):
        html = demo.get("/profile").get_data(as_text=True)
        assert f'href="{edit_url(gid)}"' in html

    def test_edit_links_do_not_expose_other_users_rows(self, client):
        register_and_login(client, "Second User", "second@example.com")
        html = client.get("/profile").get_data(as_text=True)
        assert len(txn_rows(html)) == 0
        assert not re.search(r'href="/expenses/\d+/edit"', html)


# ------------------------------------------------------------------ #
# GET form                                                            #
# ------------------------------------------------------------------ #

class TestForm:
    def test_get_returns_200_with_heading_and_button(self, demo, gid):
        response = demo.get(edit_url(gid))
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Edit expense" in html
        assert "Save changes" in html
        assert "Cancel" in html

    def test_form_prefilled_with_current_values(self, demo, gid):
        row = fetch_row(gid)
        html = demo.get(edit_url(gid)).get_data(as_text=True)
        assert attr(input_tag(html, "amount"), "value") == "450.00"
        assert attr(input_tag(html, "date"), "value") == row["date"]
        assert attr(input_tag(html, "description"), "value") == GROCERIES
        assert selected_categories(html) == ["Food"]

    def test_form_posts_to_edit_url(self, demo, gid):
        html = demo.get(edit_url(gid)).get_data(as_text=True)
        form = re.search(r"<form\b[^>]*>", html).group(0)
        assert attr(form, "action") == edit_url(gid)
        assert "post" in form.lower()

    def test_prefill_for_expense_without_description_is_empty(self, demo):
        insert_expense(DEMO_USER_ID, 12.5, "Bills", TODAY, None)
        new_id = latest_expense_id()
        html = demo.get(edit_url(new_id)).get_data(as_text=True)
        assert attr(input_tag(html, "description"), "value") in ("", None)
        assert "None" not in html
        assert attr(input_tag(html, "amount"), "value") == "12.50"
        assert selected_categories(html) == ["Bills"]

    def test_amount_prefill_has_no_currency_symbol_or_grouping(self, demo):
        insert_expense(DEMO_USER_ID, 12345.5, "Other", TODAY, "Big")
        new_id = latest_expense_id()
        html = demo.get(edit_url(new_id)).get_data(as_text=True)
        assert attr(input_tag(html, "amount"), "value") == "12345.50"

    def test_form_has_hidden_csrf_token_matching_session(self, demo, gid):
        html = demo.get(edit_url(gid)).get_data(as_text=True)
        tag = input_tag(html, "csrf_token")
        assert attr(tag, "type") == "hidden"
        with demo.session_transaction() as sess:
            assert attr(tag, "value") == sess["csrf_token"]

    def test_form_has_no_user_id_field(self, demo, gid):
        html = demo.get(edit_url(gid)).get_data(as_text=True)
        assert 'name="user_id"' not in html

    def test_no_dollar_sign_on_page(self, demo, gid):
        html = demo.get(edit_url(gid)).get_data(as_text=True)
        assert "$" not in html

    def test_rendered_token_is_accepted_on_post(self, demo, gid):
        html = demo.get(edit_url(gid)).get_data(as_text=True)
        token = attr(input_tag(html, "csrf_token"), "value")
        response = demo.post(edit_url(gid), data={"csrf_token": token, **valid_form()})
        assert response.status_code == 302


# ------------------------------------------------------------------ #
# Successful update                                                   #
# ------------------------------------------------------------------ #

class TestSuccess:
    def test_post_redirects_to_profile(self, demo, gid):
        response = post_form(demo, gid, valid_form(
            amount="500", date=fetch_row(gid)["date"], description=GROCERIES))
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/profile")

    def test_profile_shows_flash_total_and_unchanged_count(self, demo, gid):
        row = fetch_row(gid)
        before_count = expense_count()
        post_form(demo, gid, valid_form(
            amount="500", date=row["date"], description=GROCERIES))
        response = demo.get("/profile")
        html = response.get_data(as_text=True)
        assert "Expense updated." in html
        assert "₹6,399.00" in html, "6349 - 450 + 500 expected"
        assert len(txn_rows(html)) == 8
        assert expense_count() == before_count, "Edit must not create a row"

    def test_follow_redirect_shows_flash(self, demo, gid):
        response = demo.post(
            edit_url(gid),
            data={"csrf_token": csrf_token_for(demo), **valid_form()},
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Expense updated." in html

    def test_flash_is_shown_only_once(self, demo, gid):
        post_form(demo, gid, valid_form())
        demo.get("/profile")
        html = demo.get("/profile").get_data(as_text=True)
        assert "Expense updated." not in html

    def test_amount_persists(self, demo, gid):
        post_form(demo, gid, valid_form(amount="500"))
        assert fetch_row(gid)["amount"] == 500.0

    def test_category_date_description_persist(self, demo, gid):
        post_form(demo, gid, valid_form(
            amount="123.45", category="Transport", date=OLD_DATE,
            description="Taxi to airport"))
        row = fetch_row(gid)
        assert row["amount"] == 123.45
        assert row["category"] == "Transport"
        assert row["date"] == OLD_DATE
        assert row["description"] == "Taxi to airport"
        assert row["user_id"] == DEMO_USER_ID

    @pytest.mark.parametrize("description", ["", "   ", "\t \n"])
    def test_blank_description_stored_as_null(self, demo, gid, description):
        response = post_form(demo, gid, valid_form(description=description))
        assert response.status_code == 302
        assert fetch_row(gid)["description"] is None

    def test_missing_description_field_stored_as_null(self, demo, gid):
        data = valid_form()
        del data["description"]
        response = post_form(demo, gid, data)
        assert response.status_code == 302
        assert fetch_row(gid)["description"] is None

    def test_other_rows_untouched(self, demo, gid):
        others = all_rows_except(gid)
        post_form(demo, gid, valid_form(amount="1"))
        assert all_rows_except(gid) == others

    def test_sql_injection_description_stored_literally(self, demo, gid):
        payload = "'); DROP TABLE expenses; --"
        before = expense_count()
        post_form(demo, gid, valid_form(description=payload))
        assert fetch_row(gid)["description"] == payload
        assert expense_count() == before

    def test_description_html_escaped_on_profile(self, demo, gid):
        post_form(demo, gid, valid_form(description="<script>alert(1)</script>"))
        html = demo.get("/profile").get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html

    def test_user_id_form_field_is_ignored(self, client, gid):
        other_id = register_and_login(client, "Other Person", "other@example.com")
        assert other_id != DEMO_USER_ID
        client.get("/logout")
        sign_in_as_demo(client)
        response = post_form(client, gid, valid_form(user_id=str(other_id)))
        assert response.status_code == 302
        assert fetch_row(gid)["user_id"] == DEMO_USER_ID, "Posted user_id must be ignored"
        assert fetch_row(gid)["amount"] == 500.0


# ------------------------------------------------------------------ #
# Validation                                                          #
# ------------------------------------------------------------------ #

INVALID_CASES = [
    pytest.param({"amount": ""}, id="amount-blank"),
    pytest.param({"amount": "0"}, id="amount-zero"),
    pytest.param({"amount": "-5"}, id="amount-negative"),
    pytest.param({"amount": "abc"}, id="amount-text"),
    pytest.param({"amount": "nan"}, id="amount-nan"),
    pytest.param({"amount": "inf"}, id="amount-inf"),
    pytest.param({"amount": "10000000.01"}, id="amount-above-max"),
    pytest.param({"category": ""}, id="category-blank"),
    pytest.param({"category": "Crypto"}, id="category-unknown"),
    pytest.param({"date": ""}, id="date-blank"),
    pytest.param({"date": "2026-02-30"}, id="date-impossible"),
    pytest.param({"date": "abc"}, id="date-text"),
    pytest.param({"date": TOMORROW}, id="date-tomorrow"),
    pytest.param({"description": "d" * 201}, id="description-too-long"),
]


class TestValidation:
    @pytest.mark.parametrize("overrides", INVALID_CASES)
    def test_invalid_input_rerenders_with_error_and_row_unchanged(
        self, demo, gid, overrides
    ):
        before = snapshot(gid)
        count = expense_count()
        response = post_form(demo, gid, valid_form(**overrides))
        html = response.get_data(as_text=True)
        assert response.status_code == 200, f"Expected re-render for {overrides}"
        assert '<div class="auth-error">' in html, "Expected inline error"
        assert "Edit expense" in html
        assert snapshot(gid) == before, "Invalid input must not change the row"
        assert expense_count() == count

    @pytest.mark.parametrize("overrides", INVALID_CASES)
    def test_invalid_input_keeps_submitted_values(self, demo, gid, overrides):
        form = valid_form(**{
            "category": "Bills", "description": "Keep me", "amount": "77",
            "date": OLD_DATE, **overrides,
        })
        html = post_form(demo, gid, form).get_data(as_text=True)
        if "amount" not in overrides:
            assert attr(input_tag(html, "amount"), "value") == "77"
        if "date" not in overrides:
            assert attr(input_tag(html, "date"), "value") == OLD_DATE
        if "description" not in overrides:
            assert attr(input_tag(html, "description"), "value") == "Keep me"
        if "category" not in overrides:
            assert selected_categories(html) == ["Bills"]

    def test_invalid_amount_echoed_raw(self, demo, gid):
        html = post_form(demo, gid, valid_form(amount="abc")).get_data(as_text=True)
        assert attr(input_tag(html, "amount"), "value") == "abc"

    def test_error_form_still_posts_to_edit_url(self, demo, gid):
        html = post_form(demo, gid, valid_form(amount="0")).get_data(as_text=True)
        form = re.search(r"<form\b[^>]*>", html).group(0)
        assert attr(form, "action") == edit_url(gid)

    def test_error_page_has_no_success_flash_or_dollar(self, demo, gid):
        html = post_form(demo, gid, valid_form(amount="0")).get_data(as_text=True)
        assert "Expense updated." not in html
        assert "$" not in html

    def test_description_200_accepted_201_rejected(self, demo, gid):
        assert post_form(demo, gid, valid_form(description="y" * 200)).status_code == 302
        assert post_form(demo, gid, valid_form(description="y" * 201)).status_code == 200

    def test_max_amount_boundary_accepted(self, demo, gid):
        assert post_form(demo, gid, valid_form(amount="10000000")).status_code == 302
        assert fetch_row(gid)["amount"] == 10000000.0


# ------------------------------------------------------------------ #
# Ownership and missing ids                                           #
# ------------------------------------------------------------------ #

class TestOwnership:
    def test_get_other_users_expense_is_404(self, client, gid):
        register_and_login(client, "Second User", "second@example.com")
        assert client.get(edit_url(gid)).status_code == 404

    def test_post_other_users_expense_is_404_and_unchanged(self, client, gid):
        register_and_login(client, "Second User", "second@example.com")
        before = snapshot(gid)
        response = post_form(client, gid, valid_form(amount="1", description="Hacked"))
        assert response.status_code == 404
        assert snapshot(gid) == before

    def test_demo_cannot_edit_other_users_expense(self, client):
        other_id = register_and_login(client, "Second User", "second@example.com")
        insert_expense(other_id, 80, "Health", TODAY, "Private pharmacy")
        row_id = latest_expense_id(other_id)
        client.get("/logout")
        sign_in_as_demo(client)
        before = snapshot(row_id)
        assert client.get(edit_url(row_id)).status_code == 404
        response = post_form(client, row_id, valid_form(amount="1"))
        assert response.status_code == 404
        assert snapshot(row_id) == before

    def test_other_users_404_body_does_not_leak_data(self, client, gid):
        register_and_login(client, "Second User", "second@example.com")
        html = client.get(edit_url(gid)).get_data(as_text=True)
        assert GROCERIES not in html

    def test_other_users_expense_same_status_as_missing(self, client, gid):
        register_and_login(client, "Second User", "second@example.com")
        assert (
            client.get(edit_url(gid)).status_code
            == client.get(edit_url(MISSING_ID)).status_code
            == 404
        )

    def test_get_missing_id_is_404(self, demo):
        assert demo.get(edit_url(MISSING_ID)).status_code == 404

    def test_post_missing_id_is_404(self, demo):
        count = expense_count()
        response = post_form(demo, MISSING_ID, valid_form())
        assert response.status_code == 404
        assert expense_count() == count, "Edit of a missing id must not insert"


# ------------------------------------------------------------------ #
# CSRF                                                                #
# ------------------------------------------------------------------ #

class TestCsrf:
    def test_missing_token_rejected_and_row_unchanged(self, demo, gid):
        before = snapshot(gid)
        response = demo.post(edit_url(gid), data=valid_form(amount="1"))
        assert response.status_code == 400
        assert snapshot(gid) == before

    def test_wrong_token_rejected_and_row_unchanged(self, demo, gid):
        csrf_token_for(demo)
        before = snapshot(gid)
        response = demo.post(
            edit_url(gid), data={"csrf_token": "forged", **valid_form(amount="1")}
        )
        assert response.status_code == 400
        assert snapshot(gid) == before

    def test_empty_token_rejected(self, demo, gid):
        csrf_token_for(demo)
        before = snapshot(gid)
        response = demo.post(
            edit_url(gid), data={"csrf_token": "", **valid_form(amount="1")}
        )
        assert response.status_code == 400
        assert snapshot(gid) == before

    def test_signed_out_post_redirects_before_csrf_check(self, client, gid):
        response = client.post(edit_url(gid), data=valid_form())
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")


# ------------------------------------------------------------------ #
# Date filter integration                                             #
# ------------------------------------------------------------------ #

class TestDateFilter:
    def test_expense_moves_into_range_after_date_edit(self, demo, gid):
        start = (date.today() - timedelta(days=45)).isoformat()
        end = (date.today() - timedelta(days=35)).isoformat()
        url = f"/profile?start={start}&end={end}"
        html = demo.get(url).get_data(as_text=True)
        assert GROCERIES not in html, "Seeded date is this month, outside range"

        post_form(demo, gid, valid_form(
            amount="450", date=OLD_DATE, description=GROCERIES))
        html = demo.get(url).get_data(as_text=True)
        assert GROCERIES in html
        assert len(txn_rows(html)) == 1
        assert "₹450.00" in html

    def test_expense_moves_out_of_range_after_date_edit(self, demo, gid):
        original = fetch_row(gid)["date"]
        url = f"/profile?start={original}&end={original}"
        assert GROCERIES in demo.get(url).get_data(as_text=True)

        post_form(demo, gid, valid_form(
            amount="450", date=OLD_DATE, description=GROCERIES))
        html = demo.get(url).get_data(as_text=True)
        assert GROCERIES not in html

    def test_amount_edit_reflected_in_filtered_total(self, demo, gid):
        original = fetch_row(gid)["date"]
        url = f"/profile?start={original}&end={original}"
        post_form(demo, gid, valid_form(
            amount="500", date=original, description=GROCERIES))
        html = demo.get(url).get_data(as_text=True)
        assert GROCERIES in html
        assert "₹500.00" in html


# ------------------------------------------------------------------ #
# Neighbouring routes                                                 #
# ------------------------------------------------------------------ #

class TestNeighbouringRoutes:
    def test_signed_out_delete_get_does_not_remove_row(self, client, gid):
        before = expense_count()
        client.get(f"/expenses/{gid}/delete")
        assert expense_count() == before
