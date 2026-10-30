import re
from datetime import date, timedelta

import pytest
from werkzeug.datastructures import MultiDict

from app import build_date_presets, describe_date_range, parse_date_range, short_date
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

INVALID_MESSAGE = "Invalid date range — showing all time."


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def stat_value(text):
    return f'<span class="stat-value">{text}</span>'


def filter_error_text(html):
    match = re.search(
        r'class="[^"]*filter-error[^"]*"[^>]*>(.*?)</', html, re.DOTALL
    )
    return match.group(1).strip() if match else None


def preset_anchors(html):
    """Return a list of (opening_tag, label) for every preset link."""
    anchors = re.findall(r"(<a\b[^>]*>)(.*?)</a>", html, re.DOTALL)
    return [
        (tag, label.strip())
        for tag, label in anchors
        if "filter-preset" in tag
    ]


def active_preset_labels(html):
    return [
        label
        for tag, label in preset_anchors(html)
        if re.search(r'class="filter-preset active"', tag)
    ]


def presets_matching(start, end):
    # On e.g. the 30th of a 31-day month, "This month" and "Last 30 days"
    # cover the same range — only the first of them should be active.
    return [
        p["label"]
        for p in build_date_presets(date.today())
        if p["start"] == start and p["end"] == end
    ][:1]


def pin_today(monkeypatch, fixed):
    # Make app.date.today() return `fixed`; other date behaviour is unchanged.
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(fixed.year, fixed.month, fixed.day)

    monkeypatch.setattr("app.date", FixedDate)


@pytest.fixture
def user(client):
    """Fresh registered, signed-in user with three fixed-date expenses."""
    user_id = register_and_login(client, "Asha Verma", "asha@example.com")
    add_expense(user_id, 100, "Food", "2026-01-10", "Jan food")
    add_expense(user_id, 200, "Bills", "2026-02-15", "Feb bills")
    add_expense(user_id, 400, "Health", "2026-03-20", "Mar health")
    return user_id


def get_profile(client, query=""):
    response = client.get("/profile" + query)
    return response, response.get_data(as_text=True)


# ------------------------------------------------------------------ #
# Unfiltered parity with Step 5                                       #
# ------------------------------------------------------------------ #

def test_unfiltered_demo_profile_matches_step5_numbers(client):
    sign_in_as_demo(client)
    response, html = get_profile(client)

    assert response.status_code == 200
    assert "₹6,349.00" in html
    assert stat_value("8") in html
    assert "Shopping" in html
    assert len(txn_rows(html)) == 8
    assert "Showing all time" in html
    assert filter_error_text(html) is None


def test_unfiltered_fresh_user_shows_all_three_expenses(client, user):
    response, html = get_profile(client)

    assert response.status_code == 200
    assert stat_value("₹700.00") in html
    assert stat_value("3") in html
    assert len(txn_rows(html)) == 3


# ------------------------------------------------------------------ #
# Filter bar rendering                                                #
# ------------------------------------------------------------------ #

def test_filter_bar_has_presets_form_and_apply(client, user):
    _, html = get_profile(client)

    labels = [label for _, label in preset_anchors(html)]
    assert labels == ["This month", "Last 30 days", "All time"], (
        f"Unexpected preset links: {labels}"
    )
    assert 'method="get"' in html.lower()
    assert 'name="start"' in html
    assert 'name="end"' in html
    assert 'type="date"' in html
    assert "Apply" in html


def test_all_time_is_active_when_unfiltered(client, user):
    _, html = get_profile(client)

    assert active_preset_labels(html) == ["All time"]


def test_all_time_link_has_no_query_params(client, user):
    _, html = get_profile(client)

    all_time_tags = [tag for tag, label in preset_anchors(html) if label == "All time"]
    assert len(all_time_tags) == 1
    assert 'href="/profile"' in all_time_tags[0]


def test_no_filter_error_on_clean_page(client, user):
    _, html = get_profile(client)

    assert INVALID_MESSAGE not in html
    assert filter_error_text(html) is None


# ------------------------------------------------------------------ #
# Presets (derived from date.today())                                 #
# ------------------------------------------------------------------ #

def test_this_month_preset_link_href(client, user):
    today = date.today()
    start = today.replace(day=1).isoformat()
    _, html = get_profile(client)

    assert (
        f'href="/profile?start={start}&amp;end={today.isoformat()}'
        '&amp;preset=this-month"'
    ) in html


def test_last_30_days_preset_link_href(client, user):
    today = date.today()
    start = (today - timedelta(days=29)).isoformat()
    _, html = get_profile(client)

    assert (
        f'href="/profile?start={start}&amp;end={today.isoformat()}'
        '&amp;preset=last-30-days"'
    ) in html


def test_this_month_preset_is_active_and_captioned(client, user):
    today = date.today()
    start = today.replace(day=1).isoformat()
    response, html = get_profile(client, f"?start={start}&end={today.isoformat()}")

    assert response.status_code == 200
    assert "This month" in presets_matching(start, today.isoformat())
    assert active_preset_labels(html) == presets_matching(start, today.isoformat())
    assert f"Showing {short_date(start)} – {short_date(today.isoformat())}" in html


def test_last_30_days_preset_is_active(client, user, monkeypatch):
    # Pinned to a day where "Last 30 days" doesn't share "This month"'s range.
    pin_today(monkeypatch, date(2026, 10, 15))
    _, html = get_profile(client, "?start=2026-09-16&end=2026-10-15")

    assert active_preset_labels(html) == ["Last 30 days"]


def test_custom_range_has_no_active_preset(client, user):
    _, html = get_profile(client, "?start=2026-02-01&end=2026-02-28")

    assert active_preset_labels(html) == []


def test_demo_this_month_preset_keeps_all_seed_data(client):
    today = date.today()
    start = today.replace(day=1).isoformat()
    sign_in_as_demo(client)
    _, html = get_profile(client, f"?start={start}&end={today.isoformat()}")

    assert "₹6,349.00" in html
    assert stat_value("8") in html


# ------------------------------------------------------------------ #
# Filtering behaviour                                                 #
# ------------------------------------------------------------------ #

def test_february_range_shows_only_february_expense(client, user):
    response, html = get_profile(client, "?start=2026-02-01&end=2026-02-28")

    assert response.status_code == 200
    assert stat_value("₹200.00") in html
    assert stat_value("1") in html
    assert len(txn_rows(html)) == 1
    assert "Feb bills" in html
    assert "Jan food" not in html
    assert "Mar health" not in html
    assert 'class="cat-bar category-bills" style="width: 100.0%"' in html
    assert "category-food" not in html
    assert "category-health" not in html
    assert filter_error_text(html) is None


def test_february_range_caption(client, user):
    _, html = get_profile(client, "?start=2026-02-01&end=2026-02-28")

    assert f"Showing {short_date('2026-02-01')} – {short_date('2026-02-28')}" in html


def test_bounds_are_inclusive_on_single_day(client, user):
    _, html = get_profile(client, "?start=2026-02-15&end=2026-02-15")

    assert stat_value("₹200.00") in html
    assert stat_value("1") in html
    assert "Feb bills" in html


@pytest.mark.parametrize(
    "start,end,expected_count",
    [
        ("2026-01-10", "2026-03-20", 3),
        ("2026-01-11", "2026-03-20", 2),
        ("2026-01-10", "2026-03-19", 2),
        ("2026-02-16", "2026-03-19", 0),
    ],
)
def test_inclusive_bounds_at_edges(client, user, start, end, expected_count):
    _, html = get_profile(client, f"?start={start}&end={end}")

    assert len(txn_rows(html)) == expected_count, (
        f"Range {start}..{end} should include {expected_count} rows"
    )


def test_start_only_includes_everything_on_or_after(client, user):
    response, html = get_profile(client, "?start=2026-02-15")

    assert response.status_code == 200
    assert stat_value("₹600.00") in html
    assert stat_value("2") in html
    assert "Feb bills" in html
    assert "Mar health" in html
    assert "Jan food" not in html
    assert f"Showing from {short_date('2026-02-15')}" in html


def test_end_only_includes_everything_on_or_before(client, user):
    response, html = get_profile(client, "?end=2026-02-15")

    assert response.status_code == 200
    assert stat_value("₹300.00") in html
    assert stat_value("2") in html
    assert "Jan food" in html
    assert "Feb bills" in html
    assert "Mar health" not in html
    assert f"Showing up to {short_date('2026-02-15')}" in html


def test_blank_form_submission_shows_all_time_without_error(client, user):
    response, html = get_profile(client, "?start=&end=")

    assert response.status_code == 200
    assert stat_value("₹700.00") in html
    assert stat_value("3") in html
    assert "Showing all time" in html
    assert filter_error_text(html) is None
    assert INVALID_MESSAGE not in html


def test_category_breakdown_respects_range(client, user):
    _, html = get_profile(client, "?start=2026-02-01&end=2026-03-31")

    assert "category-bills" in html
    assert "category-health" in html
    assert "category-food" not in html


# ------------------------------------------------------------------ #
# Invalid input                                                       #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize(
    "query",
    [
        "?start=2026-13-01",
        "?start=abc",
        "?end=2026-02-30",
        "?end=abc",
        "?start=2026-03-01&end=2026-02-01",
        "?start=2026-02-01&end=garbage",
        "?start=01/02/2026",
        "?start=2026-02-01'%20OR%201=1--",
    ],
)
def test_invalid_range_returns_200_all_time_with_message(client, user, query):
    response, html = get_profile(client, query)

    assert response.status_code == 200, f"{query} should not error"
    assert stat_value("₹700.00") in html
    assert stat_value("3") in html
    assert len(txn_rows(html)) == 3
    assert INVALID_MESSAGE in html
    assert filter_error_text(html) == INVALID_MESSAGE
    assert "Showing all time" in html


# ------------------------------------------------------------------ #
# Empty range                                                         #
# ------------------------------------------------------------------ #

def test_range_without_expenses_shows_empty_state(client, user):
    response, html = get_profile(client, "?start=2027-01-01&end=2027-01-31")

    assert response.status_code == 200
    assert stat_value("₹0.00") in html
    assert stat_value("0") in html
    assert stat_value("—") in html
    assert html.count("No expenses in this period.") == 2
    assert "No expenses yet." not in html
    assert "No spending to show yet." not in html
    assert "cat-bar" not in html
    assert len(txn_rows(html)) == 0


def test_unfiltered_empty_user_keeps_original_empty_state(client):
    register_and_login(client, "Empty Eve", "eve@example.com")
    response, html = get_profile(client)

    assert response.status_code == 200
    assert "No expenses yet." in html
    assert "No spending to show yet." in html
    assert "No expenses in this period." not in html


# ------------------------------------------------------------------ #
# Prefilled inputs                                                    #
# ------------------------------------------------------------------ #

def test_inputs_prefilled_with_active_range(client, user):
    _, html = get_profile(client, "?start=2026-02-01&end=2026-02-28")

    assert 'name="start" value="2026-02-01"' in html
    assert 'name="end" value="2026-02-28"' in html


def test_inputs_empty_when_unfiltered(client, user):
    _, html = get_profile(client)

    assert 'name="start" value=""' in html
    assert 'name="end" value=""' in html


def test_inputs_only_start_prefilled(client, user):
    _, html = get_profile(client, "?start=2026-02-01")

    assert 'name="start" value="2026-02-01"' in html
    assert 'name="end" value=""' in html


def test_inputs_not_prefilled_with_invalid_values(client, user):
    _, html = get_profile(client, "?start=abc")

    assert 'value="abc"' not in html
    assert 'name="start" value=""' in html


# ------------------------------------------------------------------ #
# Isolation, auth, currency                                           #
# ------------------------------------------------------------------ #

def test_other_users_expenses_never_appear_in_filtered_view(client, user):
    add_expense(DEMO_USER_ID, 777, "Food", "2026-02-20", "Demo Feb lunch")

    _, html = get_profile(client, "?start=2026-02-01&end=2026-02-28")
    assert stat_value("₹200.00") in html
    assert stat_value("1") in html
    assert "Feb bills" in html
    assert "Demo Feb lunch" not in html
    assert "₹777.00" not in html

    sign_in_as_demo(client)
    _, html = get_profile(client, "?start=2026-02-01&end=2026-02-28")
    assert stat_value("₹777.00") in html
    assert "Demo Feb lunch" in html
    assert "Feb bills" not in html


def test_user_id_in_query_string_is_ignored(client, user):
    add_expense(DEMO_USER_ID, 777, "Food", "2026-02-20", "Demo Feb lunch")
    _, html = get_profile(
        client, f"?start=2026-02-01&end=2026-02-28&user_id={DEMO_USER_ID}"
    )

    assert "Demo Feb lunch" not in html
    assert "Feb bills" in html


def test_signed_out_with_query_string_redirects_to_login(client):
    response = client.get("/profile?start=2026-01-01")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


@pytest.mark.parametrize(
    "query",
    ["", "?start=2026-02-01&end=2026-02-28", "?start=abc", "?start=2027-01-01"],
)
def test_no_dollar_sign_on_page(client, user, query):
    _, html = get_profile(client, query)

    assert "$" not in html, f"Found '$' on /profile{query}"
    assert "₹" in html


# ------------------------------------------------------------------ #
# DB helpers                                                          #
# ------------------------------------------------------------------ #

def test_summary_helper_filters_by_range(user):
    summary = get_expense_summary(user, start_date="2026-02-01", end_date="2026-03-31")

    assert summary["total"] == 600.0
    assert summary["count"] == 2


def test_summary_helper_without_dates_is_all_time(user):
    summary = get_expense_summary(user)

    assert summary["total"] == 700.0
    assert summary["count"] == 3


def test_recent_helper_filters_and_orders(user):
    rows = get_recent_expenses(user, start_date="2026-02-01")

    assert [r["description"] for r in rows] == ["Mar health", "Feb bills"]


def test_recent_helper_respects_limit_with_filter(user):
    rows = get_recent_expenses(user, limit=1, end_date="2026-02-28")

    assert [r["description"] for r in rows] == ["Feb bills"]


def test_category_totals_helper_filters_by_range(user):
    rows = get_category_totals(user, start_date="2026-02-01", end_date="2026-02-28")

    assert [(r["category"], r["amount"]) for r in rows] == [("Bills", 200.0)]


def test_helpers_filtered_empty_range(user):
    assert get_category_totals(user, start_date="2027-01-01") == []
    assert get_recent_expenses(user, start_date="2027-01-01") == []
    summary = get_expense_summary(user, start_date="2027-01-01")
    assert summary["count"] == 0
    assert summary["total"] == 0


# ------------------------------------------------------------------ #
# parse_date_range                                                    #
# ------------------------------------------------------------------ #

def test_parse_neither_returns_nones_without_error():
    assert parse_date_range(MultiDict()) == (None, None, None)


def test_parse_both_valid():
    start, end, error = parse_date_range(
        MultiDict([("start", "2026-02-01"), ("end", "2026-02-28")])
    )

    assert (start, end) == ("2026-02-01", "2026-02-28")
    assert not error


def test_parse_start_only():
    start, end, error = parse_date_range(MultiDict([("start", "2026-02-01")]))

    assert (start, end) == ("2026-02-01", None)
    assert not error


def test_parse_end_only():
    start, end, error = parse_date_range(MultiDict([("end", "2026-02-01")]))

    assert (start, end) == (None, "2026-02-01")
    assert not error


def test_parse_blank_strings_count_as_not_provided():
    start, end, error = parse_date_range(MultiDict([("start", ""), ("end", "")]))

    assert (start, end) == (None, None)
    assert not error


def test_parse_same_day_is_valid():
    start, end, error = parse_date_range(
        MultiDict([("start", "2026-02-15"), ("end", "2026-02-15")])
    )

    assert (start, end) == ("2026-02-15", "2026-02-15")
    assert not error


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2026-13-01"},
        {"start": "abc"},
        {"end": "2026-02-30"},
        {"start": "2026-03-01", "end": "2026-02-01"},
        {"start": "2026-02-01", "end": "nope"},
    ],
)
def test_parse_invalid_returns_nones_and_error(params):
    start, end, error = parse_date_range(MultiDict(params))

    assert start is None
    assert end is None
    assert error, f"Expected an error message for {params}"


# ------------------------------------------------------------------ #
# build_date_presets                                                  #
# ------------------------------------------------------------------ #

def test_build_date_presets_values():
    presets = build_date_presets(date(2026, 10, 29))
    by_label = {p["label"]: p for p in presets}

    assert [p["label"] for p in presets] == ["This month", "Last 30 days", "All time"]
    assert by_label["This month"]["start"] == "2026-10-01"
    assert by_label["This month"]["end"] == "2026-10-29"
    assert by_label["Last 30 days"]["start"] == "2026-09-30"
    assert by_label["Last 30 days"]["end"] == "2026-10-29"
    assert by_label["All time"]["start"] is None
    assert by_label["All time"]["end"] is None


def test_build_date_presets_last_30_days_spans_30_inclusive_days():
    today = date(2026, 3, 1)
    by_label = {p["label"]: p for p in build_date_presets(today)}

    assert by_label["Last 30 days"]["start"] == (today - timedelta(days=29)).isoformat()


def active_labels(presets):
    return [p["label"] for p in presets if p["active"]]


def test_overlapping_presets_only_first_is_active():
    # 30 Oct: "This month" and "Last 30 days" both span 1–30 Oct.
    today = date(2026, 10, 30)
    presets = build_date_presets(today, "2026-10-01", "2026-10-30")

    by_label = {p["label"]: p for p in presets}
    assert by_label["This month"]["start"] == by_label["Last 30 days"]["start"]
    assert active_labels(presets) == ["This month"]


@pytest.mark.parametrize(
    "start, end, expected",
    [
        ("2026-10-01", "2026-10-29", ["This month"]),
        ("2026-09-30", "2026-10-29", ["Last 30 days"]),
        (None, None, ["All time"]),
        ("2026-02-01", "2026-02-28", []),
    ],
)
def test_build_date_presets_marks_at_most_one_active(start, end, expected):
    presets = build_date_presets(date(2026, 10, 29), start, end)
    assert active_labels(presets) == expected


def test_profile_overlap_lights_only_this_month(client, user, monkeypatch):
    # Pin "today" to an overlap day so the page-level check is deterministic.
    pin_today(monkeypatch, date(2026, 10, 30))
    _, html = get_profile(client, "?start=2026-10-01&end=2026-10-30")

    assert active_preset_labels(html) == ["This month"]


@pytest.mark.parametrize(
    "preset, expected",
    [("last-30-days", ["Last 30 days"]), ("this-month", ["This month"])],
)
def test_profile_overlap_lights_the_clicked_preset(
    client, user, monkeypatch, preset, expected
):
    # 30 Oct: both presets link to 1–30 Oct; ?preset= says which was clicked.
    pin_today(monkeypatch, date(2026, 10, 30))
    _, html = get_profile(
        client, f"?start=2026-10-01&end=2026-10-30&preset={preset}"
    )

    assert active_preset_labels(html) == expected


def test_clicking_last_30_days_link_on_overlap_day_keeps_it_lit(
    client, user, monkeypatch
):
    # Follow the real href from the page, as a browser click would.
    pin_today(monkeypatch, date(2026, 10, 30))
    _, html = get_profile(client)
    href = re.search(r'<a href="([^"]*)" class="filter-preset[^"]*">Last 30 days</a>', html)
    _, html = get_profile(client, "?" + href.group(1).split("?", 1)[1].replace("&amp;", "&"))

    assert active_preset_labels(html) == ["Last 30 days"]


@pytest.mark.parametrize(
    "start, end, chosen, expected",
    [
        # Key's range doesn't match the dates shown → ignored, date match wins.
        ("2026-10-01", "2026-10-29", "last-30-days", ["This month"]),
        # Unknown key → ignored.
        ("2026-09-30", "2026-10-29", "bogus", ["Last 30 days"]),
        # Custom range never lights a preset, even with a key.
        ("2026-02-01", "2026-02-28", "this-month", []),
    ],
)
def test_build_date_presets_ignores_mismatched_preset_key(start, end, chosen, expected):
    presets = build_date_presets(date(2026, 10, 29), start, end, chosen)
    assert active_labels(presets) == expected


@pytest.mark.parametrize(
    "start, end, expected",
    [
        ("2026-02-01", "2026-02-28", "Showing 1 Feb, 2026 – 28 Feb, 2026"),
        ("2026-02-15", None, "Showing from 15 Feb, 2026"),
        (None, "2026-02-15", "Showing up to 15 Feb, 2026"),
        (None, None, "Showing all time"),
    ],
)
def test_describe_date_range(start, end, expected):
    assert describe_date_range(start, end) == expected
