import re
from typing import Optional
from playwright.sync_api import Page, Locator

from config.settings import settings
from core.pages.base_page import BasePage


class UsersPage(BasePage):
    """Page Object Model for Redborder's Users & Roles Management (/users):
    - User list navigation and inspection.
    - User creation with validation error handling (e.g. password complexity).
    - User editing (profile attributes, role, preferred locale).
    - Password updates.
    - Account state toggling (enabled/blocked) and user deletion.
    """

    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)

    # -------------------------------------------------------------
    # Locators
    # -------------------------------------------------------------

    @property
    def users_table(self) -> Locator:
        return self.page.locator("table#users-table")

    @property
    def new_user_btn(self) -> Locator:
        return self.page.locator("a[href='/users/new'], a:has(i.fa-plus):has-text('New')").first

    def get_user_row(self, login: str) -> Locator:
        """Locates the table row for a user with the specified login or name, matching exactly."""
        pattern = re.compile(rf"^\s*{re.escape(login)}\s*$")
        return self.page.locator("table#users-table tr.user").filter(
            has=self.page.locator("td.name, td.email, td.username, td:first-child").filter(has_text=pattern)
        ).first

    # -------------------------------------------------------------
    # Navigation
    # -------------------------------------------------------------

    def open_users(self) -> None:
        """Navigates to the Users management index (/users)."""
        self.navigate("/users")
        self.wait_for_loading_complete()
        try:
            self.users_table.wait_for(state="visible", timeout=settings.default_timeout_ms)
        except Exception:
            pass

    def open_new_user(self) -> None:
        """Navigates to the user creation form (/users/new)."""
        self.navigate("/users/new")
        self.wait_for_loading_complete()
        self.page.wait_for_selector("form#new_user, input#user_login", timeout=settings.default_timeout_ms)

    def is_user_present(self, login: str) -> bool:
        """Checks if a user row is present in the users table."""
        self.open_users()
        row = self.get_user_row(login)
        return row.is_visible()

    def get_user_role(self, login: str) -> str:
        """Returns the role string displayed in the user row."""
        row = self.get_user_row(login)
        if row.is_visible():
            role_cell = row.locator("td.role").first
            if role_cell.is_visible():
                return role_cell.inner_text().strip()
        return ""

    def get_user_domain(self, login: str) -> str:
        """Returns the top domain string displayed in the user row."""
        row = self.get_user_row(login)
        if row.is_visible():
            domain_cell = row.locator("td[data-label*='Top'], td[data-label*='top']").first
            if domain_cell.is_visible():
                return domain_cell.inner_text().strip()
        return ""

    # -------------------------------------------------------------
    # User Creation & Validation
    # -------------------------------------------------------------

    def create_user(
        self,
        name: str,
        login: str,
        email: str,
        password: str,
        password_confirmation: Optional[str] = None,
        role: str = "viewer",
        domain_name: Optional[str] = None,
        expect_error: bool = False,
    ) -> Optional[str]:
        """Fills and submits the New User form.
        
        If expect_error=True, captures and returns any validation error message
        displayed (e.g. password complexity failure). If creation succeeds, returns None.
        """
        self.open_new_user()

        self.page.locator("input#user_name").fill(name)
        self.page.locator("input#user_login").fill(login)
        self.page.locator("input#user_email").fill(email)

        # Select role
        role_select = self.page.locator("select#user_role")
        if role_select.is_visible():
            role_select.select_option(value=role)

        # Select top domain if specified
        if domain_name:
            self.page.evaluate(
                """(targetName) => {
                    const sel = document.querySelector('select#user_sensor_id');
                    if (!sel) return;
                    for (const opt of sel.options) {
                        if (opt.text.includes(targetName)) {
                            sel.value = opt.value;
                            if (window.jQuery) {
                                window.jQuery(sel).trigger('chosen:updated').trigger('change');
                            }
                            break;
                        }
                    }
                }""",
                domain_name,
            )

        # Fill passwords
        self.page.locator("input#user_password").fill(password)
        conf_pwd = password_confirmation if password_confirmation is not None else password
        self.page.locator("input#user_password_confirmation").fill(conf_pwd)

        # Submit form
        submit_btn = self.page.locator(".panel-actions input[type='submit'], .panel-actions button.btn-success, input[type='submit']").first
        submit_btn.click()
        self.wait_for_loading_complete()
        self.page.wait_for_timeout(500)

        if expect_error:
            # Check for form validation error blocks
            error_loc = self.page.locator(".has-error .help-block, .alert-danger, .alert-warning, .help-block.error").first
            if error_loc.is_visible():
                return error_loc.inner_text().strip()
            # Check general flash message
            flash_error = self.get_alert_text()
            if flash_error:
                return flash_error
            # If redirected to /users or no error is visible, creation did not fail as expected
            if "/users" in self.page.url and "new" not in self.page.url:
                return None
            return None

        # If creation expected to succeed, verify we land on /users
        self.page.wait_for_url(lambda u: "/users" in u and "new" not in u, timeout=15000)
        self.wait_for_loading_complete()
        return None

    # -------------------------------------------------------------
    # User Editing & Personalization
    # -------------------------------------------------------------

    def open_edit_user(self, login: str) -> None:
        """Finds the user row and clicks the Edit icon."""
        self.open_users()
        row = self.get_user_row(login)
        assert row.is_visible(), f"Cannot edit: user '{login}' not found in table"
        edit_link = row.locator("a.edit-user").first
        edit_link.click()
        self.wait_for_loading_complete()
        self.page.wait_for_selector("article#user_settings, form.edit_user", timeout=settings.default_timeout_ms)

    def edit_user(
        self,
        login: str,
        name: Optional[str] = None,
        role: Optional[str] = None,
        locale: Optional[str] = None,
        domain_name: Optional[str] = None,
    ) -> None:
        """Edits an existing user's profile attributes."""
        self.open_edit_user(login)

        if name:
            self.page.locator("input#user_name").fill(name)

        if role:
            role_select = self.page.locator("select#user_role")
            if role_select.is_visible():
                role_select.select_option(value=role)

        if locale:
            locale_select = self.page.locator("select#user_preferred_locale")
            if locale_select.is_visible():
                locale_select.select_option(value=locale)

        if domain_name:
            self.page.evaluate(
                """(targetName) => {
                    const sel = document.querySelector('select#user_sensor_id');
                    if (!sel) return;
                    for (const opt of sel.options) {
                        if (opt.text.includes(targetName)) {
                            sel.value = opt.value;
                            if (window.jQuery) {
                                window.jQuery(sel).trigger('chosen:updated').trigger('change');
                            }
                            break;
                        }
                    }
                }""",
                domain_name,
            )

        submit_btn = self.page.locator(".panel-actions input[type='submit'], .panel-actions button.btn-success").first
        submit_btn.click()
        self.wait_for_loading_complete()
        self.page.wait_for_url(lambda u: "/users" in u and "edit" not in u, timeout=15000)

    def change_user_password(self, login: str, new_password: str) -> None:
        """Updates the password for a user from the admin edit interface."""
        self.open_edit_user(login)

        # Click the 'Edit' button to reveal the password change section
        edit_pwd_btn = self.page.locator("a.edit_password_button").first
        if edit_pwd_btn.is_visible():
            edit_pwd_btn.click()
            self.page.wait_for_timeout(300)

        pwd_input = self.page.locator("input#user_password")
        pwd_input.wait_for(state="visible", timeout=5000)
        pwd_input.fill(new_password)

        conf_input = self.page.locator("input#user_password_confirmation")
        conf_input.fill(new_password)

        submit_btn = self.page.locator(".panel-actions input[type='submit'], .panel-actions button.btn-success").first
        submit_btn.click()
        self.wait_for_loading_complete()
        self.page.wait_for_url(lambda u: "/users" in u and "edit" not in u, timeout=15000)

    # -------------------------------------------------------------
    # State Toggles & Deletion
    # -------------------------------------------------------------

    def is_user_enabled(self, login: str) -> bool:
        """Returns True if the user's enabled checkbox is checked."""
        self.open_users()
        row = self.get_user_row(login)
        if not row.is_visible():
            return False
        checkbox = row.locator("td.toggle_enabled input[type='checkbox']").first
        return checkbox.is_checked()

    def toggle_enabled(self, login: str) -> bool:
        """Toggles the 'enabled' checkbox for a user and returns the new checked state."""
        self.open_users()
        row = self.get_user_row(login)
        assert row.is_visible(), f"User '{login}' not found in table"
        checkbox = row.locator("td.toggle_enabled input[type='checkbox']").first
        checkbox.click()
        self.wait_for_loading_complete()
        self.page.wait_for_timeout(500)
        return checkbox.is_checked()

    def delete_user(self, login: str) -> bool:
        """Deletes a user via the table delete button, accepting confirmation."""
        self.open_users()
        row = self.get_user_row(login)
        if not row.is_visible():
            return False

        destroy_btn = row.locator("a.destroy-user").first
        if destroy_btn.is_visible():
            self.page.once("dialog", lambda dialog: dialog.accept())
            destroy_btn.click()
            self.wait_for_loading_complete()
            try:
                row.wait_for(state="detached", timeout=5000)
            except Exception:
                self.page.wait_for_timeout(1000)
            return not self.is_user_present(login)
        return False

    def wait_for_loading_complete(self, timeout: int = 15000) -> None:
        """Waits for any blockUI overlay or spinner to disappear."""
        try:
            self.page.locator(".blockUI.blockOverlay").wait_for(state="hidden", timeout=timeout)
        except Exception:
            pass
        self.page.wait_for_load_state("domcontentloaded")
