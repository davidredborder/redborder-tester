import pytest
from bs4 import BeautifulSoup
from core.api_client import APIClient


@pytest.mark.api
class TestPlatformEndpoints:
    def test_login_page_renders_html_with_csrf(self, api_client: APIClient):
        """Verifies that the login page returns 200 OK and contains the authenticity token."""
        token = api_client.fetch_csrf_token()
        assert token is not None, "Failed to retrieve CSRF authenticity token from login page"
        assert len(token) > 10

    def test_static_assets_reachable(self, api_client: APIClient):
        """Verifies that static assets referenced by the application are served properly."""
        page_resp = api_client.get("/users/login")
        assert page_resp.status_code == 200, "Failed to fetch login page to discover assets"

        soup = BeautifulSoup(page_resp.text, "html.parser")
        icon_link = soup.find("link", rel=lambda val: val and "icon" in val)
        asset_href = icon_link["href"] if icon_link and "href" in icon_link.attrs else None

        assert asset_href is not None, "Could not find any icon asset link in the page HTML"

        response = api_client.get(asset_href)
        assert response.status_code in (200, 304), (
            f"Asset at {asset_href} failed with status {response.status_code}"
        )

    def test_authenticated_dashboard_views(self, authenticated_api_client: APIClient):
        """Verifies that key application views render successfully for authenticated users."""
        for endpoint in ["/overview", "/sensors", "/users"]:
            resp = authenticated_api_client.get(endpoint)
            assert "/users/login" not in str(resp.url), f"Accessing {endpoint} redirected back to login"
            assert resp.status_code in (200, 302), f"Endpoint {endpoint} returned status {resp.status_code}"
