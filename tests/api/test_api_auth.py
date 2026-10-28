import pytest
from core.api_client import APIClient
from config.settings import settings


@pytest.mark.api
@pytest.mark.smoke
class TestAPIAuth:
    def test_unauthenticated_access_redirects_to_login(self, api_client: APIClient):
        """Verifies that accessing protected paths without credentials redirects to login."""
        response = api_client.get("/overview")
        assert response.status_code == 200
        assert "/users/login" in str(response.url) or "sign_in" in str(response.url)

    def test_login_with_valid_credentials(self, api_client: APIClient):
        """Verifies that authenticating with valid credentials succeeds and enters overview."""
        success = api_client.login(
            username=settings.web_user,
            password=settings.web_password,
        )
        assert success is True, "Login failed with correct credentials"
        assert api_client.is_authenticated is True

        # Verify access to protected dashboard overview page
        overview_resp = api_client.get("/overview")
        assert overview_resp.status_code == 200
        assert "/users/login" not in str(overview_resp.url)

    def test_login_with_invalid_credentials_fails(self, api_client: APIClient):
        """Verifies that authenticating with invalid credentials fails with error message."""
        success = api_client.login(
            username="nonexistent_user_xyz",
            password="WrongPassword123!",
        )
        assert success is False, "Login should have failed for invalid credentials"
        assert api_client.is_authenticated is False
