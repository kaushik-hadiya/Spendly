import inspect
import re
from datetime import date
from pathlib import Path

import pytest

import app as app_module
from database import db as db_module
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
MISSING_ID = 99999
ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def other_id():
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM expenses WHERE category = ? AND user_id = ?",
            ("Other", DEMO_USER_ID),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "Seeded Other expense missing"
    return row["id"]


def latest_expense_id(user_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT MAX(id) AS m FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()["m"]
    finally:
        conn.close()


def delete_url(expense_id):
    return f"/expenses/{expense_id}/delete"


def post_delete(client, expense_id, **extra):
    return client.post(
        delete_url(expense_id),
        data={"csrf_token": csrf_token_for(client), **extra},
    )


def category_names(html):
    return re.findall(r'<span class="cat-name">(.*?)</span>', html)


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
        response = client.get(delete_url(gid))
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")
        assert fetch_row(gid) is not None

    def test_post_signed_out_redirects_and_row_remains(self, client, gid):
        before = snapshot(gid)
        response = client.post(
            delete_url(gid), data={"csrf_token": csrf_token_for(client)}
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")
        assert snapshot(gid) == before, "Signed-out POST must not delete the row"

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_signed_out_flashes_sign_in_message(self, client, gid, method):
        response = getattr(client, method)(delete_url(gid), follow_redirects=True)
        assert "Please sign in to delete an expense." in response.get_data(as_text=True)

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_signed_out_missing_id_redirects_rather_than_404(self, client, method):
        response = getattr(client, method)(delete_url(MISSING_ID))
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_session_with_nonexistent_user_redirects_to_login(
        self, client, gid, method
    ):
        with client.session_transaction() as sess:
            sess["user_id"] = 424242
        response = getattr(client, method)(delete_url(gid))
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")
        assert fetch_row(gid) is not None


# ------------------------------------------------------------------ #
# Profile Delete links                                                #
# ------------------------------------------------------------------ #

class TestProfileDeleteLinks:
    def test_every_recent_row_has_edit_and_delete_links(self, demo):
        html = demo.get("/profile").get_data(as_text=True)
        rows = txn_rows(html)
        assert len(rows) == 8
        deletes = re.findall(r'href="(/expenses/(\d+)/delete)"', html)
        edits = re.findall(r'href="/expenses/(\d+)/edit"', html)
        assert len(deletes) == len(rows), "Each row needs exactly one Delete link"
        assert sorted(e for _, e in deletes) == sorted(edits)
        for href, expense_id in deletes:
            assert href == delete_url(int(expense_id))
            assert fetch_row(int(expense_id))["user_id"] == DEMO_USER_ID

    def test_delete_link_has_txn_delete_class_and_follows_edit(self, demo, gid):
        html = demo.get("/profile").get_data(as_text=True)
        expected = (
            f'<a href="/expenses/{gid}/edit" class="txn-edit">Edit</a>'
            f'<a href="/expenses/{gid}/delete" class="txn-delete">Delete</a>'
        )
        assert expected in html, "Delete link (class txn-delete) should follow Edit"

    def test_table_still_has_five_columns(self, demo):
        html = demo.get("/profile").get_data(as_text=True)
        head = re.search(r"<thead>(.*?)</thead>", html, re.DOTALL).group(1)
        assert len(re.findall(r"<th\b", head)) == 5

    def test_no_delete_links_for_new_user_without_expenses(self, client):
        register_and_login(client, "Second User", "second@example.com")
        html = client.get("/profile").get_data(as_text=True)
        assert not re.search(r'href="/expenses/\d+/delete"', html)


# ------------------------------------------------------------------ #
# GET confirmation page                                               #
# ------------------------------------------------------------------ #

class TestConfirmationPage:
    def test_get_returns_200_with_heading_subtitle_and_button(self, demo, gid):
        response = demo.get(delete_url(gid))
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Delete expense" in html
        assert "This can't be undone." in html
        assert re.search(r"<button\b[^>]*>\s*Delete expense\s*</button>", html)

    def test_shows_amount_category_date_and_description(self, demo, gid):
        row = fetch_row(gid)
        html = demo.get(delete_url(gid)).get_data(as_text=True)
        assert "₹450.00" in html
        assert row["category"] == "Food"
        assert "Food" in html
        assert GROCERIES in html
        assert row["date"][:4] in html, "Expected the expense year to be shown"

    def test_null_description_shown_as_dash(self, demo):
        html = demo.get(delete_url(other_id())).get_data(as_text=True)
        assert "₹200.00" in html
        assert "Other" in html
        assert "—" in html

    def test_has_cancel_link_to_profile(self, demo, gid):
        html = demo.get(delete_url(gid)).get_data(as_text=True)
        assert re.search(r'<a\b[^>]*href="/profile"[^>]*>\s*Cancel\s*</a>', html)

    def test_form_posts_to_delete_url_with_hidden_csrf(self, demo, gid):
        html = demo.get(delete_url(gid)).get_data(as_text=True)
        form = re.search(r"<form\b([^>]*)>", html)
        assert form, "No <form> found"
        assert attr(form.group(1), "method").lower() == "post"
        assert attr(form.group(1), "action") == delete_url(gid)
        tag = input_tag(html, "csrf_token")
        assert attr(tag, "type") == "hidden"
        with demo.session_transaction() as sess:
            assert attr(tag, "value") == sess["csrf_token"]

    def test_get_does_not_modify_db(self, demo, gid):
        before_count = expense_count()
        before = snapshot(gid)
        demo.get(delete_url(gid))
        demo.get(delete_url(gid) + "?confirm=1")
        assert expense_count() == before_count
        assert snapshot(gid) == before

    def test_no_dollar_sign_on_page(self, demo, gid):
        html = demo.get(delete_url(gid)).get_data(as_text=True)
        assert "$" not in html, "Currency must be INR only"

    def test_has_no_javascript_confirm(self, demo, gid):
        html = demo.get(delete_url(gid)).get_data(as_text=True)
        assert "confirm(" not in html


# ------------------------------------------------------------------ #
# POST delete                                                         #
# ------------------------------------------------------------------ #

class TestDelete:
    def test_post_deletes_and_redirects_to_profile(self, demo, gid):
        response = post_delete(demo, gid)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/profile")
        assert fetch_row(gid) is None, "Row should be gone from the DB"

    def test_follow_redirect_shows_flash(self, demo, gid):
        response = demo.post(
            delete_url(gid),
            data={"csrf_token": csrf_token_for(demo)},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "Expense deleted." in response.get_data(as_text=True)

    def test_only_target_row_deleted(self, demo, gid):
        before = expense_count()
        post_delete(demo, gid)
        assert expense_count() == before - 1

    def test_csrf_token_from_rendered_form_works(self, demo, gid):
        html = demo.get(delete_url(gid)).get_data(as_text=True)
        token = attr(input_tag(html, "csrf_token"), "value")
        response = demo.post(delete_url(gid), data={"csrf_token": token})
        assert response.status_code == 302
        assert fetch_row(gid) is None

    def test_profile_totals_after_deleting_groceries(self, demo, gid):
        post_delete(demo, gid)
        html = demo.get("/profile").get_data(as_text=True)
        assert "₹5,899.00" in html
        assert len(txn_rows(html)) == 7
        assert GROCERIES not in html
        assert f"/expenses/{gid}/delete" not in html

    def test_deleting_only_other_removes_category_from_breakdown(self, demo):
        html = demo.get("/profile").get_data(as_text=True)
        assert "Other" in category_names(html), "Precondition: Other present"
        post_delete(demo, other_id())
        html = demo.get("/profile").get_data(as_text=True)
        assert "Other" not in category_names(html)
        assert "₹6,149.00" in html

    def test_deleting_last_expense_shows_empty_state(self, client):
        user_id = register_and_login(client, "Second User", "second@example.com")
        insert_expense(user_id, 120, "Food", TODAY, "Lunch")
        expense_id = latest_expense_id(user_id)
        html = client.get("/profile").get_data(as_text=True)
        assert len(txn_rows(html)) == 1
        response = post_delete(client, expense_id)
        assert response.status_code == 302
        html = client.get("/profile").get_data(as_text=True)
        assert "No expenses yet." in html
        assert "₹0.00" in html
        assert expense_count(user_id) == 0

    def test_second_post_to_deleted_id_returns_404(self, demo, gid):
        assert post_delete(demo, gid).status_code == 302
        assert post_delete(demo, gid).status_code == 404

    def test_get_after_delete_returns_404(self, demo, gid):
        post_delete(demo, gid)
        assert demo.get(delete_url(gid)).status_code == 404

    def test_tampered_user_id_field_has_no_effect(self, client):
        other_user = register_and_login(client, "Second User", "second@example.com")
        insert_expense(other_user, 77, "Food", TODAY, "Mine")
        mine = latest_expense_id(other_user)
        demo_before = expense_count(DEMO_USER_ID)
        post_delete(client, mine, user_id=str(DEMO_USER_ID))
        assert fetch_row(mine) is None, "Session user's own expense is deleted"
        assert expense_count(DEMO_USER_ID) == demo_before

    def test_tampered_user_id_cannot_delete_other_users_row(self, client, gid):
        register_and_login(client, "Second User", "second@example.com")
        before = snapshot(gid)
        response = post_delete(client, gid, user_id=str(DEMO_USER_ID))
        assert response.status_code == 404
        assert snapshot(gid) == before

    def test_user_id_query_string_has_no_effect(self, client, gid):
        register_and_login(client, "Second User", "second@example.com")
        before = snapshot(gid)
        response = client.post(
            delete_url(gid) + f"?user_id={DEMO_USER_ID}",
            data={"csrf_token": csrf_token_for(client)},
        )
        assert response.status_code == 404
        assert snapshot(gid) == before


# ------------------------------------------------------------------ #
# CSRF                                                                #
# ------------------------------------------------------------------ #

class TestCsrf:
    @pytest.mark.parametrize(
        "token", ["forged", "", "tökén-✓-ünïcode", "x" * 5000]
    )
    def test_bad_token_returns_400_and_row_unchanged(self, demo, gid, token):
        csrf_token_for(demo)
        before = snapshot(gid)
        response = demo.post(delete_url(gid), data={"csrf_token": token})
        assert response.status_code == 400
        assert snapshot(gid) == before

    def test_missing_token_returns_400_and_row_unchanged(self, demo, gid):
        csrf_token_for(demo)
        before = snapshot(gid)
        response = demo.post(delete_url(gid), data={})
        assert response.status_code == 400
        assert snapshot(gid) == before

    def test_no_session_token_returns_400(self, demo, gid):
        before = snapshot(gid)
        response = demo.post(delete_url(gid), data={"csrf_token": ""})
        assert response.status_code == 400
        assert snapshot(gid) == before

    def test_bad_csrf_checked_before_lookup(self, demo):
        csrf_token_for(demo)
        response = demo.post(delete_url(MISSING_ID), data={"csrf_token": "forged"})
        assert response.status_code == 400


# ------------------------------------------------------------------ #
# Ownership and 404                                                   #
# ------------------------------------------------------------------ #

class TestOwnershipAndNotFound:
    def test_get_other_users_expense_returns_404(self, client, gid):
        register_and_login(client, "Second User", "second@example.com")
        assert client.get(delete_url(gid)).status_code == 404
        assert fetch_row(gid) is not None

    def test_post_other_users_expense_returns_404_and_row_remains(self, client, gid):
        register_and_login(client, "Second User", "second@example.com")
        before = snapshot(gid)
        assert post_delete(client, gid).status_code == 404
        assert snapshot(gid) == before

    def test_demo_cannot_delete_new_users_expense(self, client):
        user_id = register_and_login(client, "Second User", "second@example.com")
        insert_expense(user_id, 55, "Bills", TODAY, "Theirs")
        theirs = latest_expense_id(user_id)
        sign_in_as_demo(client)
        assert client.get(delete_url(theirs)).status_code == 404
        assert post_delete(client, theirs).status_code == 404
        assert fetch_row(theirs) is not None

    def test_other_users_status_same_as_missing(self, client, gid):
        register_and_login(client, "Second User", "second@example.com")
        assert (
            client.get(delete_url(gid)).status_code
            == client.get(delete_url(MISSING_ID)).status_code
            == 404
        )

    def test_get_missing_id_returns_404(self, demo):
        assert demo.get(delete_url(MISSING_ID)).status_code == 404

    def test_post_missing_id_returns_404(self, demo):
        assert post_delete(demo, MISSING_ID).status_code == 404

    def test_non_integer_id_returns_404(self, demo):
        assert demo.get("/expenses/abc/delete").status_code == 404

    def test_helper_returning_zero_makes_post_404(self, demo, gid, monkeypatch):
        monkeypatch.setattr(app_module, "delete_expense_by_id", lambda *a, **k: 0)
        response = post_delete(demo, gid)
        assert response.status_code == 404
        assert fetch_row(gid) is not None, "Patched helper must not have deleted"


# ------------------------------------------------------------------ #
# DB helper                                                           #
# ------------------------------------------------------------------ #

class TestDeleteHelper:
    def test_returns_one_and_deletes_owned_row(self, gid):
        assert db_module.delete_expense_by_id(gid, DEMO_USER_ID) == 1
        assert fetch_row(gid) is None

    def test_returns_zero_for_other_users_row(self, gid):
        before = snapshot(gid)
        assert db_module.delete_expense_by_id(gid, DEMO_USER_ID + 1000) == 0
        assert snapshot(gid) == before

    def test_returns_zero_for_missing_id(self):
        assert db_module.delete_expense_by_id(MISSING_ID, DEMO_USER_ID) == 0

    def test_second_call_returns_zero(self, gid):
        assert db_module.delete_expense_by_id(gid, DEMO_USER_ID) == 1
        assert db_module.delete_expense_by_id(gid, DEMO_USER_ID) == 0

    def test_sql_injection_in_ids_is_harmless(self, gid):
        before = expense_count()
        assert db_module.delete_expense_by_id("1 OR 1=1", DEMO_USER_ID) == 0
        assert expense_count() == before

    def test_sql_uses_question_mark_placeholders_only(self):
        source = inspect.getsource(db_module.delete_expense_by_id)
        assert "DELETE FROM expenses" in source
        assert source.count("?") >= 2, "Expected ? placeholders for id and user_id"
        assert not re.search(r'f"[^"]*DELETE|f\'[^\']*DELETE', source), "No f-string SQL"
        assert ".format(" not in source
        assert not re.search(r'DELETE[^\n]*"\s*%', source), "No % formatting in SQL"
        assert not re.search(r'"\s*\+', source), "No string concatenation in SQL"


# ------------------------------------------------------------------ #
# Template and CSS rules                                              #
# ------------------------------------------------------------------ #

class TestTemplateAndCss:
    def test_template_extends_base(self):
        text = (ROOT / "templates" / "delete_expense.html").read_text(encoding="utf-8")
        assert re.search(r'{%\s*extends\s+["\']base\.html["\']\s*%}', text)

    def test_template_has_no_style_tag(self):
        text = (ROOT / "templates" / "delete_expense.html").read_text(encoding="utf-8")
        assert "<style" not in text.lower()

    def test_template_has_no_hardcoded_internal_hrefs(self):
        text = (ROOT / "templates" / "delete_expense.html").read_text(encoding="utf-8")
        hrefs = re.findall(r'(?:href|action)="([^"]*)"', text)
        for value in hrefs:
            assert not value.startswith("/"), f"Hardcoded internal URL: {value}"

    def test_css_has_no_hex_colours(self):
        css = (ROOT / "static" / "css" / "delete_expense.css").read_text(
            encoding="utf-8"
        )
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), "Hex colour found in CSS"

    def test_css_file_is_served(self, demo, gid):
        html = demo.get(delete_url(gid)).get_data(as_text=True)
        assert "delete_expense.css" in html
        assert demo.get("/static/css/delete_expense.css").status_code == 200
