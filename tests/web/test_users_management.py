import time
import pytest
from playwright.sync_api import Page, expect

from config.settings import settings
from core.pages.login_page import LoginPage
from core.pages.users_page import UsersPage


@pytest.fixture
def authenticated_admin_page(page: Page, base_url: str) -> UsersPage:
    """Logs into the Web UI as Super Administrator and navigates to /users."""
    login_page = LoginPage(page, base_url)
    login_page.open()
    login_page.login(
        username=settings.web_user,
        password=settings.web_password,
    )
    page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

    users_page = UsersPage(page, base_url)
    users_page.open_users()
    return users_page


@pytest.mark.web
class TestUsersManagement:
    """End-to-End suite verifying User Administration, Security & Localization:
    1. Password complexity enforcement (rejects short or weak passwords).
    2. User creation with compliant password and role assignment.
    3. User profile editing and language/locale switching (en <-> es).
    4. Password change and re-authentication with new password.
    5. Account toggle states (enabled/disabled) and user deletion.
    """

    def test_users_lifecycle_security_and_localization(
        self,
        authenticated_admin_page: UsersPage,
        page: Page,
        base_url: str,
        attach_screenshot,
    ):
        users_page = authenticated_admin_page
        login_page = LoginPage(page, base_url)

        ts = int(time.time())
        test_login = f"rb_user_{ts}"
        test_name = test_login
        test_email = f"user_{ts}@example.com"
        valid_password = f"RedBorder!{ts}Aa"
        updated_password = f"NewPassword!{ts}Bb"

        # -------------------------------------------------------------
        # Phase 1: Password Complexity Enforcement
        # -------------------------------------------------------------
        print("[Users Test] Phase 1: Verifying password complexity enforcement...")
        invalid_passwords = [
            "short1!",              # too short (< 12 chars)
            "nouppercase12345!",    # missing uppercase
            "NOLOWERCASE12345!",    # missing lowercase
            "NoSpecialChar12345",   # missing special character
        ]

        for invalid_pwd in invalid_passwords:
            print(f"[Users Test] Testing invalid password: '{invalid_pwd}'...")
            inv_login = f"inv_{int(time.time() * 1000) % 100000}"
            error_msg = users_page.create_user(
                name="Invalid Pwd User",
                login=inv_login,
                email=f"{inv_login}@example.com",
                password=invalid_pwd,
                role="viewer",
                expect_error=True,
            )
            assert error_msg is not None, f"Expected validation error for password '{invalid_pwd}', but creation succeeded"
            assert "The Password must contain" in error_msg or "Password" in error_msg, (
                f"Validation error message unexpected: '{error_msg}'"
            )
            assert not users_page.is_user_present(inv_login), (
                f"User '{inv_login}' with weak password '{invalid_pwd}' was unexpectedly created!"
            )
            print(f"[Users Test] Correctly rejected: {error_msg}")
            attach_screenshot(page, f"01_pwd_reject_{invalid_pwd[:5]}")

        # -------------------------------------------------------------
        # Phase 2: Valid User Creation & Role Assignment
        # -------------------------------------------------------------
        print(f"[Users Test] Phase 2: Creating valid user '{test_login}' with role 'incident_responder'...")
        create_err = users_page.create_user(
            name=test_name,
            login=test_login,
            email=test_email,
            password=valid_password,
            role="incident_responder",
            expect_error=False,
        )
        assert create_err is None, f"Failed to create valid user: {create_err}"
        attach_screenshot(page, "02_user_created_in_table")

        try:
            # Verify row presence and displayed role
            assert users_page.is_user_present(test_login), f"User '{test_login}' not found in table"
            displayed_role = users_page.get_user_role(test_login)
            print(f"[Users Test] User '{test_login}' created. Displayed role: {displayed_role}")
            assert "incident responder" in displayed_role.lower() or "incident_responder" in displayed_role.lower()

            # -------------------------------------------------------------
            # Phase 3: Language / Locale Switching (en -> es -> en)
            # -------------------------------------------------------------
            print(f"[Users Test] Phase 3: Changing preferred locale to Spanish ('es')...")
            users_page.edit_user(login=test_login, locale="es")
            attach_screenshot(page, "03_user_locale_set_es")

            # Log out of admin and log in as the test user
            print(f"[Users Test] Logging in as '{test_login}' to verify Spanish locale...")
            login_page.logout()
            login_page.login(username=test_login, password=valid_password)
            page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)
            attach_screenshot(page, "04_user_spanish_ui")

            # Assert Spanish localized elements on the page
            page_content = page.content()
            has_spanish = any(
                es_term in page_content
                for es_term in ["Visión general", "Sensores", "Monitores", "Configuración", "Cerrar sesión"]
            )
            print(f"[Users Test] Spanish UI elements detected: {has_spanish}")
            assert has_spanish, "Expected Spanish localization in UI, but none found"

            # Log out of test user
            login_page.logout()

            # -------------------------------------------------------------
            # Phase 4: Password Change & Re-authentication
            # -------------------------------------------------------------
            print(f"[Users Test] Phase 4: Logging back in as admin to change password...")
            login_page.login(username=settings.web_user, password=settings.web_password)
            page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

            users_page.open_users()
            print(f"[Users Test] Changing password for '{test_login}'...")
            users_page.change_user_password(login=test_login, new_password=updated_password)
            attach_screenshot(page, "05_password_changed")

            # Verify old password fails
            print(f"[Users Test] Verifying old password is now rejected...")
            login_page.logout()
            old_login_res = login_page.login(username=test_login, password=valid_password)
            assert old_login_res is False or "login" in page.url, "Old password was unexpectedly accepted"

            # Verify new password succeeds
            print(f"[Users Test] Verifying new password is accepted...")
            login_page.logout()
            new_login_res = login_page.login(username=test_login, password=updated_password)
            page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)
            assert "login" not in page.url, "Failed to authenticate with updated password"
            attach_screenshot(page, "06_authenticated_with_new_password")

            # -------------------------------------------------------------
            # Phase 5: Account Toggle & Teardown
            # -------------------------------------------------------------
            print(f"[Users Test] Phase 5: Logging back as admin for account toggling and deletion...")
            login_page.logout()
            login_page.login(username=settings.web_user, password=settings.web_password)
            page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

            users_page.open_users()

            # Test account disable toggle
            print(f"[Users Test] Toggling disabled state for '{test_login}'...")
            initially_enabled = users_page.is_user_enabled(test_login)
            users_page.toggle_enabled(test_login)
            toggled_state = users_page.is_user_enabled(test_login)
            assert toggled_state != initially_enabled, f"Expected enabled state to change, remained {initially_enabled}"
            attach_screenshot(page, "07_account_disabled")

            # Delete user
            print(f"[Users Test] Deleting test user '{test_login}'...")
            deleted = users_page.delete_user(test_login)
            assert deleted, f"Failed to delete user '{test_login}'"
            attach_screenshot(page, "08_user_deleted")

            assert not users_page.is_user_present(test_login), f"User '{test_login}' still present after deletion"
            print("[Users Test] Complete User Management lifecycle verified successfully.")
        finally:
            # Resilient cleanup if test failed before phase 5 deletion
            try:
                if "/users" not in page.url:
                    login_page.logout()
                    login_page.login(username=settings.web_user, password=settings.web_password)
                    page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)
                if users_page.is_user_present(test_login):
                    print(f"[Users Test Cleanup] Deleting test user '{test_login}' in finalizer...")
                    users_page.delete_user(test_login)
            except Exception as e:
                print(f"[Users Test Cleanup Warning] Failed to cleanup user '{test_login}': {e}")
