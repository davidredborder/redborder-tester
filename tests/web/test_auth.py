import pytest
from playwright.sync_api import Page, expect

from config.settings import settings
from core.pages.login_page import LoginPage
from core.pages.dashboard_page import DashboardPage


@pytest.mark.web
@pytest.mark.smoke
class TestWebAuthentication:
    def test_login_page_renders_elements(self, page: Page, base_url: str, attach_screenshot):
        """Verifies that the login page loads with all expected form controls."""
        login_page = LoginPage(page, base_url)
        login_page.open()

        expect(login_page.username_input).to_be_visible()
        expect(login_page.password_input).to_be_visible()
        expect(login_page.submit_button).to_be_visible()
        assert "redborder" in page.title().lower()
        attach_screenshot(page, title="Login Page")

    def test_login_with_invalid_credentials_shows_error(self, page: Page, base_url: str, attach_screenshot):
        """Verifies that invalid credentials trigger an alert error and keep user on login page."""
        login_page = LoginPage(page, base_url)
        login_page.open()

        login_page.login(
            username="invalid_admin",
            password="WrongPassword123!",
        )

        # Wait for error alert to appear
        alert_locator = page.locator(".alert, .alert-danger, .flash-message")
        expect(alert_locator).to_be_visible(timeout=10000)
        assert "Invalid" in alert_locator.inner_text()
        assert login_page.is_login_page_displayed()
        attach_screenshot(page, title="Authentication - Invalid Credentials Alert")

    def test_login_with_valid_credentials_succeeds(self, page: Page, base_url: str, attach_screenshot):
        """Verifies that submitting valid credentials navigates to the main dashboard."""
        login_page = LoginPage(page, base_url)
        login_page.open()

        login_page.login(
            username=settings.web_user,
            password=settings.web_password,
        )

        dashboard = DashboardPage(page, base_url)
        # Wait for navigation away from login
        page.wait_for_url(lambda u: "/overview" in u or "/nodes" in u or "/dashboard" in u or "login" not in u, timeout=15000)
        assert dashboard.is_dashboard_loaded()
        attach_screenshot(page, title="Authentication - Successful Login Dashboard")
