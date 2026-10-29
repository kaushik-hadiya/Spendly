from helpers import sign_in_as_demo

ANALYTICS_LINK = '<a href="/analytics"'
ACTIVE_ANALYTICS_LINK = '<a href="/analytics" class="active" aria-current="page">Analytics</a>'


def test_signed_out_user_is_redirected_to_login(client):
    response = client.get("/analytics")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_signed_out_redirect_shows_sign_in_message(client):
    response = client.get("/analytics", follow_redirects=True)
    assert b"Please sign in to view analytics." in response.data


def test_stale_session_is_cleared(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 9999
        sess["user_name"] = "Ghost"
    response = client.get("/analytics")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_signed_in_user_sees_coming_soon_page(client):
    sign_in_as_demo(client)
    response = client.get("/analytics")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "<title>Analytics — Spendly</title>" in html
    assert "Coming Soon" in html
    assert "Advanced Analytics" in html
    assert "css/analytics.css" in html


def test_navbar_hides_analytics_when_signed_out(client):
    html = client.get("/login").get_data(as_text=True)
    assert ANALYTICS_LINK not in html


def test_navbar_shows_analytics_when_signed_in(client):
    sign_in_as_demo(client)
    html = client.get("/profile").get_data(as_text=True)
    assert '<a href="/analytics">Analytics</a>' in html


def test_navbar_highlights_analytics_on_analytics_page(client):
    sign_in_as_demo(client)
    html = client.get("/analytics").get_data(as_text=True)
    assert ACTIVE_ANALYTICS_LINK in html


def test_navbar_does_not_highlight_analytics_elsewhere(client):
    sign_in_as_demo(client)
    html = client.get("/profile").get_data(as_text=True)
    assert ACTIVE_ANALYTICS_LINK not in html
