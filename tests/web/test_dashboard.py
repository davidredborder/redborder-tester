import pytest
from playwright.sync_api import Page, expect

from config.settings import settings
from core.pages.login_page import LoginPage
from core.pages.dashboard_page import DashboardPage


@pytest.fixture
def logged_in_page(page: Page, base_url: str) -> DashboardPage:
    """Fixture that logs in once and returns the dashboard page."""
    login_page = LoginPage(page, base_url)
    login_page.open()
    login_page.login(
        username=settings.web_user,
        password=settings.web_password,
    )
    dashboard = DashboardPage(page, base_url)
    page.wait_for_url(lambda u: "login" not in u, timeout=15000)
    return dashboard


@pytest.mark.web
class TestDashboardNavigation:
    def test_dashboard_header_and_navigation(self, logged_in_page: DashboardPage, attach_screenshot):
        """Verifies that the main navigation bar and layout render after login."""
        page = logged_in_page.page
        expect(logged_in_page.navbar).to_be_visible(timeout=10000)
        assert "redborder" in page.title().lower()
        attach_screenshot(page, title="Dashboard Overview")

    def test_navigate_to_sensors_view(self, logged_in_page: DashboardPage, attach_screenshot):
        """Verifies navigation to the sensors tree view."""
        page = logged_in_page.page
        logged_in_page.navigate("/sensors")
        page.wait_for_load_state("domcontentloaded")
        assert "/sensors" in page.url
        assert logged_in_page.is_dashboard_loaded()
        attach_screenshot(page, title="Navigation - Sensors View")

    def test_navigate_to_users_view(self, logged_in_page: DashboardPage, attach_screenshot):
        """Verifies navigation to the users management view."""
        page = logged_in_page.page
        logged_in_page.navigate("/users")
        page.wait_for_load_state("domcontentloaded")
        assert "/users" in page.url
        assert logged_in_page.is_dashboard_loaded()
        attach_screenshot(page, title="Navigation - Users Management")
