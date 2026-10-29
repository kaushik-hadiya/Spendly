import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from database.db import CATEGORIES, create_expense, get_db
from helpers import (
    DEMO_USER_ID,
    add_expense as insert_expense,
    register_and_login,
    sign_in_as_demo,
    txn_rows,
)

ROOT = Path(__file__).resolve().parent.parent
ADD_URL = "/expenses/add"
TODAY = date.today().isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def expense_count(user_id=None):
    conn = get_db()
    try:
        if user_id is None:
            row = conn.execute("SELECT COUNT(*) AS n FROM expenses").fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return row["n"]
    finally:
        conn.close()


def last_expense():
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()


def valid_form(**overrides):
    data = {
        "amount": "250",
        "category": "Food",
        "date": TODAY,
        "description": "Lunch",
    }
    data.update(overrides)
    return data


def csrf_token_for(client):
    # Mirrors what GET /expenses/add does: one token per session.
    with client.session_transaction() as sess:
        return sess.setdefault("csrf_token", "test-csrf-token")


def post_form(client, data):
    return client.post(ADD_URL, data={"csrf_token": csrf_token_for(client), **data})


def post_expense(client, **overrides):
    return post_form(client, valid_form(**overrides))


def input_tag(html, name):
    match = re.search(r'<input\b[^>]*\bname="%s"[^>]*>' % re.escape(name), html)
    assert match, f"No <input name={name}> found in page"
    return match.group(0)


def attr(tag, attribute):
    match = re.search(r'\b%s="([^"]*)"' % re.escape(attribute), tag)
    return match.group(1) if match else None


def select_options(html):
    select = re.search(
        r'<select\b[^>]*name="category"[^>]*>(.*?)</select>', html, re.DOTALL
    )
    assert select, "No category <select> found"
    return re.findall(r"<option\b([^>]*)>(.*?)</option>", select.group(1), re.DOTALL)


@pytest.fixture
def demo(client):
    sign_in_as_demo(client)
    return client


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_get_signed_out_redirects_to_login(self, client):
        response = client.get(ADD_URL)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")

    def test_post_signed_out_redirects_to_login_and_inserts_nothing(self, client):
        before = expense_count()
        response = post_expense(client)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")
        assert expense_count() == before, "Signed-out POST must not insert"

    def test_signed_out_redirect_flashes_sign_in_message(self, client):
        response = client.get(ADD_URL, follow_redirects=True)
        assert "Please sign in to add an expense." in response.get_data(as_text=True)

    def test_session_for_missing_user_is_cleared_and_redirected(self, client):
        with client.session_transaction() as sess:
            sess["user_id"] = 99999
        before = expense_count()
        response = post_expense(client)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")
        assert expense_count() == before
        with client.session_transaction() as sess:
            assert "user_id" not in sess, "Stale session should be cleared"


# ------------------------------------------------------------------ #
# GET form                                                            #
# ------------------------------------------------------------------ #

class TestForm:
    def test_get_returns_200_with_fields_and_button(self, demo):
        response = demo.get(ADD_URL)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Amount (₹)" in html
        for name in ("amount", "date", "description"):
            input_tag(html, name)
        assert re.search(r'<select\b[^>]*name="category"', html)
        for name in ("amount", "category", "date", "description"):
            assert f'<label for="{name}">' in html
        assert "Add expense" in html

    def test_get_form_posts_to_add_url(self, demo):
        html = demo.get(ADD_URL).get_data(as_text=True)
        form = re.search(r"<form\b[^>]*>", html).group(0)
        assert attr(form, "action") == ADD_URL
        assert "post" in form.lower()

    def test_category_select_has_placeholder_then_all_categories(self, demo):
        html = demo.get(ADD_URL).get_data(as_text=True)
        options = select_options(html)
        first_attrs, _ = options[0]
        assert attr(first_attrs, "value") == "", "First option must be a placeholder"
        values = [attr(a, "value") for a, _ in options[1:]]
        assert values == list(CATEGORIES)
        assert sorted(values) == sorted(
            ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]
        )

    def test_date_input_defaults_to_today_with_max_today(self, demo):
        tag = input_tag(demo.get(ADD_URL).get_data(as_text=True), "date")
        assert attr(tag, "value") == TODAY
        assert attr(tag, "max") == TODAY

    def test_amount_input_attributes(self, demo):
        tag = input_tag(demo.get(ADD_URL).get_data(as_text=True), "amount")
        assert attr(tag, "type") == "number"
        assert attr(tag, "step") == "0.01"

    def test_description_input_has_maxlength_200(self, demo):
        tag = input_tag(demo.get(ADD_URL).get_data(as_text=True), "description")
        assert attr(tag, "maxlength") == "200"

    def test_form_has_no_user_id_field(self, demo):
        html = demo.get(ADD_URL).get_data(as_text=True)
        assert 'name="user_id"' not in html

    def test_no_dollar_sign_on_page(self, demo):
        assert "$" not in demo.get(ADD_URL).get_data(as_text=True)

    def test_profile_links_to_add_expense(self, demo):
        html = demo.get("/profile").get_data(as_text=True)
        assert f'href="{ADD_URL}"' in html
        assert "Add expense" in html


# ------------------------------------------------------------------ #
# Successful submission                                               #
# ------------------------------------------------------------------ #

class TestSuccess:
    def test_post_redirects_to_profile(self, demo):
        response = post_expense(demo)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/profile")

    def test_profile_shows_flash_totals_and_lunch_first(self, demo):
        response = post_expense(demo, date=TODAY)
        assert response.status_code == 302
        response = demo.get("/profile")
        html = response.get_data(as_text=True)
        assert "Expense added." in html
        assert "₹6,599.00" in html, "6349 + 250 expected"
        assert len(txn_rows(html)) == 9
        first_row = re.search(r'<td class="txn-date">.*?</tr>', html, re.DOTALL).group(0)
        assert "Lunch" in first_row, "New expense should be on top of recent table"

    def test_flash_is_shown_only_once(self, demo):
        post_expense(demo)
        demo.get("/profile")
        html = demo.get("/profile").get_data(as_text=True)
        assert "Expense added." not in html

    def test_row_saved_for_signed_in_user(self, demo):
        before = expense_count()
        post_expense(demo, amount="250", category="Food", date=YESTERDAY,
                     description="Lunch")
        assert expense_count() == before + 1
        row = last_expense()
        assert row["user_id"] == DEMO_USER_ID
        assert row["amount"] == 250.0
        assert row["category"] == "Food"
        assert row["date"] == YESTERDAY
        assert row["description"] == "Lunch"

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_every_category_is_accepted(self, demo, category):
        response = post_expense(demo, category=category)
        assert response.status_code == 302
        assert last_expense()["category"] == category

    @pytest.mark.parametrize("description", ["", "   ", "\t \n"])
    def test_blank_description_stored_as_null(self, demo, description):
        post_expense(demo, description=description)
        row = last_expense()
        assert row["description"] is None, "Blank description must be NULL, not ''"

    def test_missing_description_field_stored_as_null(self, demo):
        data = valid_form()
        del data["description"]
        response = post_form(demo, data)
        assert response.status_code == 302
        assert last_expense()["description"] is None

    def test_description_is_stripped(self, demo):
        post_expense(demo, description="  Coffee  ")
        assert last_expense()["description"] == "Coffee"

    def test_description_of_exactly_200_chars_accepted(self, demo):
        post_expense(demo, description="x" * 200)
        assert last_expense()["description"] == "x" * 200

    def test_description_with_sql_injection_stored_literally(self, demo):
        payload = "'); DROP TABLE expenses; --"
        before = expense_count()
        post_expense(demo, description=payload)
        assert last_expense()["description"] == payload
        assert expense_count() == before + 1

    def test_description_html_is_escaped_on_profile(self, demo):
        post_expense(demo, description="<script>alert(1)</script>")
        html = demo.get("/profile").get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html

    def test_user_id_form_field_is_ignored(self, client):
        other_id = register_and_login(client, "Other Person", "other@example.com")
        assert other_id != DEMO_USER_ID
        demo_before = expense_count(DEMO_USER_ID)
        post_expense(client, user_id=str(DEMO_USER_ID))
        row = last_expense()
        assert row["user_id"] == other_id, "Posted user_id must be ignored"
        assert expense_count(DEMO_USER_ID) == demo_before


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
    pytest.param({"amount": "-inf"}, id="amount-neg-inf"),
    pytest.param({"amount": "10000000.01"}, id="amount-above-max"),
    pytest.param({"amount": "99999999"}, id="amount-way-above-max"),
    pytest.param({"amount": "0.004"}, id="amount-rounds-to-zero"),
    pytest.param({"category": ""}, id="category-blank"),
    pytest.param({"category": "Crypto"}, id="category-unknown"),
    pytest.param({"category": "food"}, id="category-wrong-case"),
    pytest.param({"date": ""}, id="date-blank"),
    pytest.param({"date": "2026-02-30"}, id="date-impossible"),
    pytest.param({"date": "abc"}, id="date-text"),
    pytest.param({"date": TOMORROW}, id="date-tomorrow"),
    pytest.param({"description": "d" * 201}, id="description-too-long"),
]


class TestValidation:
    @pytest.mark.parametrize("overrides", INVALID_CASES)
    def test_invalid_input_rerenders_with_error_and_inserts_nothing(
        self, demo, overrides
    ):
        before = expense_count()
        response = post_expense(demo, **overrides)
        html = response.get_data(as_text=True)
        assert response.status_code == 200, f"Expected re-render for {overrides}"
        assert '<div class="auth-error">' in html, "Expected inline error"
        assert expense_count() == before, "Invalid input must not insert"

    @pytest.mark.parametrize("overrides", INVALID_CASES)
    def test_invalid_input_keeps_other_submitted_values(self, demo, overrides):
        form = valid_form(**{"description": "Keep me", **overrides})
        html = post_form(demo, form).get_data(as_text=True)
        if "amount" not in overrides:
            assert attr(input_tag(html, "amount"), "value") == "250"
        if "date" not in overrides:
            assert attr(input_tag(html, "date"), "value") == TODAY
        if "description" not in overrides:
            assert attr(input_tag(html, "description"), "value") == "Keep me"
        if "category" not in overrides:
            selected = [
                attr(a, "value")
                for a, _ in select_options(html)
                if re.search(r"\bselected\b", a)
            ]
            assert selected == ["Food"], "Submitted category should stay selected"

    def test_invalid_input_keeps_submitted_invalid_value(self, demo):
        html = post_expense(demo, amount="abc").get_data(as_text=True)
        # The server echoes the raw submission; the browser decides what to show.
        assert attr(input_tag(html, "amount"), "value") == "abc"

    def test_error_page_has_no_flash_success(self, demo):
        html = post_expense(demo, amount="0").get_data(as_text=True)
        assert "Expense added." not in html

    def test_error_page_still_has_no_dollar_sign(self, demo):
        html = post_expense(demo, amount="0").get_data(as_text=True)
        assert "$" not in html

    def test_error_page_date_max_still_today(self, demo):
        html = post_expense(demo, date=TOMORROW).get_data(as_text=True)
        assert attr(input_tag(html, "date"), "max") == TODAY

    def test_description_with_200_chars_boundary_vs_201(self, demo):
        assert post_expense(demo, description="y" * 200).status_code == 302
        assert post_expense(demo, description="y" * 201).status_code == 200

    def test_date_today_is_accepted(self, demo):
        assert post_expense(demo, date=TODAY).status_code == 302

    def test_whitespace_only_description_over_200_is_treated_as_blank(self, demo):
        response = post_expense(demo, description=" " * 250)
        assert response.status_code == 302
        assert last_expense()["description"] is None

    def test_failed_post_does_not_touch_other_rows(self, demo):
        before = expense_count(DEMO_USER_ID)
        post_expense(demo, amount="-5")
        assert expense_count(DEMO_USER_ID) == before


# ------------------------------------------------------------------ #
# Amount rounding and bounds                                          #
# ------------------------------------------------------------------ #

class TestAmount:
    def test_99_999_rounds_to_100(self, demo):
        response = post_expense(demo, amount="99.999")
        assert response.status_code == 302
        assert last_expense()["amount"] == 100.0

    def test_rounds_to_two_decimals(self, demo):
        post_expense(demo, amount="12.344")
        assert last_expense()["amount"] == 12.34

    def test_smallest_valid_amount_accepted(self, demo):
        response = post_expense(demo, amount="0.01")
        assert response.status_code == 302
        assert last_expense()["amount"] == 0.01

    def test_0_004_rejected_because_it_rounds_to_zero(self, demo):
        before = expense_count()
        response = post_expense(demo, amount="0.004")
        assert response.status_code == 200
        assert '<div class="auth-error">' in response.get_data(as_text=True)
        assert expense_count() == before

    def test_exactly_max_amount_accepted(self, demo):
        response = post_expense(demo, amount="10000000")
        assert response.status_code == 302
        assert last_expense()["amount"] == 10000000.0

    def test_above_max_amount_rejected(self, demo):
        before = expense_count()
        response = post_expense(demo, amount="10000000.01")
        assert response.status_code == 200
        assert expense_count() == before

    def test_amount_with_surrounding_spaces_is_accepted(self, demo):
        response = post_expense(demo, amount=" 75.50 ")
        assert response.status_code == 302
        assert last_expense()["amount"] == 75.5


# ------------------------------------------------------------------ #
# Isolation and date filter                                           #
# ------------------------------------------------------------------ #

class TestProfileIntegration:
    def test_expense_added_by_one_user_not_visible_to_another(self, client):
        sign_in_as_demo(client)
        post_expense(client, description="DemoSecretLunch")
        client.get("/logout")
        register_and_login(client, "Second User", "second@example.com")
        html = client.get("/profile").get_data(as_text=True)
        assert "DemoSecretLunch" not in html
        assert len(txn_rows(html)) == 0

    def test_new_users_expense_not_added_to_demo_profile(self, client):
        register_and_login(client, "Second User", "second@example.com")
        post_expense(client, description="SecondUserOnly")
        client.get("/logout")
        sign_in_as_demo(client)
        html = client.get("/profile").get_data(as_text=True)
        assert "SecondUserOnly" not in html
        assert len(txn_rows(html)) == expense_count(DEMO_USER_ID)

    def test_new_user_sees_own_expense_total(self, client):
        register_and_login(client, "Second User", "second@example.com")
        post_expense(client, amount="1234.5", description="Mine")
        html = client.get("/profile").get_data(as_text=True)
        assert "₹1,234.50" in html
        assert "Mine" in html

    def test_expense_appears_in_range_that_includes_its_date(self, demo):
        past = (date.today() - timedelta(days=400)).isoformat()
        post_expense(demo, date=past, description="OldLunch")
        html = demo.get(f"/profile?start={past}&end={past}").get_data(as_text=True)
        assert "OldLunch" in html
        assert len(txn_rows(html)) == 1

    def test_expense_hidden_from_range_that_excludes_its_date(self, demo):
        past = (date.today() - timedelta(days=400)).isoformat()
        post_expense(demo, date=past, description="OldLunch")
        later = (date.today() - timedelta(days=300)).isoformat()
        html = demo.get(f"/profile?start={later}&end={TODAY}").get_data(as_text=True)
        assert "OldLunch" not in html

    def test_expense_dated_today_respects_range_ending_yesterday(self, demo):
        post_expense(demo, date=TODAY, description="TodayOnly")
        start = (date.today() - timedelta(days=3650)).isoformat()
        html = demo.get(f"/profile?start={start}&end={YESTERDAY}").get_data(as_text=True)
        assert "TodayOnly" not in html
        html = demo.get(f"/profile?start={TODAY}&end={TODAY}").get_data(as_text=True)
        assert "TodayOnly" in html


# ------------------------------------------------------------------ #
# create_expense helper                                               #
# ------------------------------------------------------------------ #

class TestCreateExpense:
    def test_returns_lastrowid_and_inserts_row(self):
        row_id = create_expense(DEMO_USER_ID, 42.5, "Bills", YESTERDAY, "Power")
        assert isinstance(row_id, int)
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM expenses WHERE id = ?", (row_id,)
            ).fetchone()
        finally:
            conn.close()
        assert row["user_id"] == DEMO_USER_ID
        assert row["amount"] == 42.5
        assert row["category"] == "Bills"
        assert row["date"] == YESTERDAY
        assert row["description"] == "Power"

    def test_ids_increase_between_calls(self):
        first = create_expense(DEMO_USER_ID, 1, "Food", TODAY)
        second = create_expense(DEMO_USER_ID, 2, "Food", TODAY)
        assert second > first

    @pytest.mark.parametrize("description", [None, ""])
    def test_empty_description_stored_as_null(self, description):
        row_id = create_expense(DEMO_USER_ID, 5, "Other", TODAY, description)
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT description FROM expenses WHERE id = ?", (row_id,)
            ).fetchone()
        finally:
            conn.close()
        assert row["description"] is None

    def test_description_defaults_to_none(self):
        row_id = create_expense(DEMO_USER_ID, 5, "Other", TODAY)
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT description FROM expenses WHERE id = ?", (row_id,)
            ).fetchone()
        finally:
            conn.close()
        assert row["description"] is None

    def test_unknown_user_is_rejected_by_foreign_key(self):
        import sqlite3

        with pytest.raises(sqlite3.IntegrityError):
            create_expense(99999, 5, "Food", TODAY)

    def test_raw_insert_helper_still_coexists(self):
        before = expense_count()
        insert_expense(DEMO_USER_ID, 10, "Food", TODAY, "raw")
        assert expense_count() == before + 1


# ------------------------------------------------------------------ #
# CSRF                                                                #
# ------------------------------------------------------------------ #

class TestCsrf:
    def test_form_has_hidden_token_matching_session(self, demo):
        html = demo.get(ADD_URL).get_data(as_text=True)
        tag = input_tag(html, "csrf_token")
        assert attr(tag, "type") == "hidden"
        with demo.session_transaction() as sess:
            assert attr(tag, "value") == sess["csrf_token"]

    def test_token_from_rendered_form_is_accepted(self, demo):
        html = demo.get(ADD_URL).get_data(as_text=True)
        token = attr(input_tag(html, "csrf_token"), "value")
        response = demo.post(ADD_URL, data={"csrf_token": token, **valid_form()})
        assert response.status_code == 302

    def test_missing_token_rejected_and_inserts_nothing(self, demo):
        before = expense_count()
        response = demo.post(ADD_URL, data=valid_form())
        assert response.status_code == 400
        assert expense_count() == before

    def test_wrong_token_rejected_and_inserts_nothing(self, demo):
        csrf_token_for(demo)
        before = expense_count()
        response = demo.post(ADD_URL, data={"csrf_token": "forged", **valid_form()})
        assert response.status_code == 400
        assert expense_count() == before

    def test_signed_out_post_still_redirects_before_csrf_check(self, client):
        response = client.post(ADD_URL, data=valid_form())
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")


# ------------------------------------------------------------------ #
# Static assets and neighbouring stubs                                #
# ------------------------------------------------------------------ #

class TestAssetsAndStubs:
    @pytest.mark.parametrize(
        "relative", ["static/css/expense_form.css", "static/css/profile.css"]
    )
    def test_css_has_no_hex_colours(self, relative):
        css = (ROOT / relative).read_text(encoding="utf-8")
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b(?!\s*\{)", css), (
            f"Hardcoded hex colour in {relative}"
        )

    def test_edit_stub_unchanged(self, client):
        text = client.get("/expenses/1/edit").get_data(as_text=True)
        assert text == "Edit expense — coming in Step 8"

    def test_delete_stub_unchanged(self, client):
        text = client.get("/expenses/1/delete").get_data(as_text=True)
        assert text == "Delete expense — coming in Step 9"
