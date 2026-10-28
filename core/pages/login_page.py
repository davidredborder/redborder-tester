from typing import Optional
from playwright.sync_api import Page, Locator
from core.pages.base_page import BasePage
from config.settings import settings


class LoginPage(BasePage):
    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)

    @property
    def username_input(self) -> Locator:
        return self.page.locator("#user_username")

    @property
    def password_input(self) -> Locator:
        return self.page.locator("#password")

    @property
    def remember_me_checkbox(self) -> Locator:
        return self.page.locator("#user_remember_me")

    @property
    def submit_button(self) -> Locator:
        return self.page.locator("button[type='submit'][value='database'], button[type='submit'].btn-success, button[type='submit']").first

    def open(self) -> None:
        self.navigate("/users/login")
        self.username_input.wait_for(state="visible", timeout=settings.default_timeout_ms)

    def logout(self) -> None:
        """Logs out the active session by triggering Redborder sign out and clearing cookies."""
        try:
            if "login" not in self.page.url:
                self.page.evaluate("""() => {
                    const link = document.querySelector("a[href*='/users/logout'], a.user-item[href*='logout']");
                    if (link) {
                        link.click();
                    } else {
                        fetch('/users/logout', { method: 'DELETE' });
                    }
                }""")
                self.page.wait_for_timeout(300)
        except Exception:
            pass

        try:
            self.page.context.clear_cookies()
        except Exception:
            pass

        self.navigate("/users/login")
        try:
            self.username_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        except Exception:
            self.navigate("/users/login")
            self.username_input.wait_for(state="visible", timeout=settings.default_timeout_ms)

    def is_login_page_displayed(self) -> bool:
        return self.username_input.is_visible() and self.password_input.is_visible()

    def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        remember_me: bool = False,
    ) -> None:
        user = username if username is not None else settings.web_user
        pwd = password if password is not None else settings.web_password

        if not self.is_login_page_displayed():
            self.open()

        self.username_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        self.username_input.fill(user)
        self.password_input.fill(pwd)
        if remember_me:
            self.remember_me_checkbox.check()
        self.submit_button.click()
