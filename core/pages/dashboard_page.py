from playwright.sync_api import Page, Locator
from core.pages.base_page import BasePage


class DashboardPage(BasePage):
    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)

    @property
    def navbar(self) -> Locator:
        return self.page.locator("header, nav, .navbar").first

    @property
    def user_menu(self) -> Locator:
        return self.page.locator(".dropdown-user, .user-profile, a[href*='sign_out'], a[href*='logout']").first

    def is_dashboard_loaded(self) -> bool:
        login_input = self.page.locator("#user_username")
        # Ensure login input is gone AND positive navigation header is visible
        return not login_input.is_visible() and self.navbar.is_visible()

    def logout(self) -> None:
        signout_link = self.page.locator("a[href*='sign_out'], a[href*='logout']").first
        if signout_link.is_visible():
            signout_link.click()
        else:
            self.navigate("/users/sign_out")
