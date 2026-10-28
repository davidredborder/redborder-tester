import time
import uuid
import pytest
from playwright.sync_api import Page, expect

from config.settings import settings
from core.pages.login_page import LoginPage
from core.pages.sensors_page import SensorsPage
from core.pages.users_page import UsersPage


@pytest.fixture
def admin_session(page: Page, base_url: str):
    """Ensures an authenticated Super Administrator session before running tests."""
    login_page = LoginPage(page, base_url)
    login_page.open()
    login_page.login(username=settings.web_user, password=settings.web_password)
    page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)
    users_page = UsersPage(page, base_url)
    users_page.open_users()
    return users_page


@pytest.mark.web
class TestUsersRolesPermissions:
    """End-to-End suite verifying the Redborder Multi-Role Matrix and Permission Boundaries:
    1. Role assignment & mutation: viewer -> security_analyst -> incident_responder -> administrator.
    2. Permission boundary verification:
       - Viewer: Read-only sensor tree (no Add/Edit/Delete actions), blocked from /users with privilege warning.
       - Administrator: Full administrative powers (Add Sensor visible, /users fully accessible).
    """

    def test_roles_assignment_and_mutation(
        self,
        admin_session: UsersPage,
        page: Page,
        attach_screenshot,
    ):
        users_page = admin_session
        unique_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
        role_user = f"role_mut_{unique_id}"
        role_email = f"role_{unique_id}@example.com"
        role_pwd = f"RoleMutation!{unique_id}Aa"

        print(f"[Roles Test] Phase 1: Creating user '{role_user}' initially as 'viewer'...")
        users_page.create_user(
            name=role_user,
            login=role_user,
            email=role_email,
            password=role_pwd,
            role="viewer",
            expect_error=False,
        )
        assert users_page.is_user_present(role_user), f"User '{role_user}' not found in table after creation"
        attach_screenshot(page, "01_role_created_viewer")

        try:
            # 1. Verify Viewer
            role_text = users_page.get_user_role(role_user)
            print(f"[Roles Test] Initial role: '{role_text}'")
            assert role_text.strip().lower() == "viewer", f"Expected exact 'Viewer' role, got '{role_text}'"

            # 2. Mutate to Security Analyst
            print(f"[Roles Test] Mutating role to 'security_analyst'...")
            users_page.edit_user(login=role_user, role="security_analyst")
            attach_screenshot(page, "02_role_mutated_security_analyst")
            role_text = users_page.get_user_role(role_user)
            print(f"[Roles Test] Updated role: '{role_text}'")
            assert role_text.strip().lower() == "security analyst", f"Expected exact 'Security Analyst' role, got '{role_text}'"

            # 3. Mutate to Incident Responder
            print(f"[Roles Test] Mutating role to 'incident_responder'...")
            users_page.edit_user(login=role_user, role="incident_responder")
            attach_screenshot(page, "03_role_mutated_incident_responder")
            role_text = users_page.get_user_role(role_user)
            print(f"[Roles Test] Updated role: '{role_text}'")
            assert role_text.strip().lower() == "incident responder", f"Expected exact 'Incident Responder' role, got '{role_text}'"

            # 4. Mutate to Administrator
            print(f"[Roles Test] Mutating role to 'administrator'...")
            users_page.edit_user(login=role_user, role="administrator")
            attach_screenshot(page, "04_role_mutated_administrator")
            role_text = users_page.get_user_role(role_user)
            print(f"[Roles Test] Updated role: '{role_text}'")
            assert role_text.strip().lower() == "administrator", f"Expected exact 'Administrator' role, got '{role_text}'"

        finally:
            print(f"[Roles Test Cleanup] Deleting test user '{role_user}'...")
            try:
                users_page.open_users()
                deleted = users_page.delete_user(role_user)
                assert deleted or not users_page.is_user_present(role_user), f"User '{role_user}' deletion returned False"
                assert not users_page.is_user_present(role_user), f"User '{role_user}' still present after cleanup"
                print(f"[Roles Test Cleanup] User '{role_user}' cleaned up successfully.")
            except Exception as e:
                print(f"[Roles Test Cleanup Warning] Failed to delete '{role_user}': {e}")

    def test_role_permission_boundaries_viewer_vs_admin(
        self,
        admin_session: UsersPage,
        page: Page,
        base_url: str,
        attach_screenshot,
    ):
        users_page = admin_session
        login_page = LoginPage(page, base_url)
        sensors_page = SensorsPage(page, base_url)

        unique_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
        viewer_username = f"rb_v_{unique_id}"
        viewer_email = f"v_{unique_id}@example.com"
        viewer_password = f"ViewerPass!{unique_id}Aa"

        admin_username = f"rb_a_{unique_id}"
        admin_email = f"a_{unique_id}@example.com"
        admin_password = f"AdminPass!{unique_id}Aa"

        # -------------------------------------------------------------
        # Setup: Create Viewer and Administrator users
        # -------------------------------------------------------------
        print(f"[Permission Test] Setup: Creating viewer '{viewer_username}'...")
        users_page.create_user(
            name=viewer_username,
            login=viewer_username,
            email=viewer_email,
            password=viewer_password,
            role="viewer",
            expect_error=False,
        )
        assert users_page.is_user_present(viewer_username), f"Viewer user '{viewer_username}' not found after creation"

        print(f"[Permission Test] Setup: Creating administrator '{admin_username}'...")
        users_page.create_user(
            name=admin_username,
            login=admin_username,
            email=admin_email,
            password=admin_password,
            role="administrator",
            expect_error=False,
        )
        assert users_page.is_user_present(admin_username), f"Admin user '{admin_username}' not found after creation"
        attach_screenshot(page, "05_viewer_and_admin_created")

        try:
            # -------------------------------------------------------------
            # Part 1: Viewer Permission Boundaries (Read-Only)
            # -------------------------------------------------------------
            print(f"[Permission Test] Part 1: Logging in as Viewer '{viewer_username}'...")
            login_page.logout()
            login_page.login(username=viewer_username, password=viewer_password)
            page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

            # Assert /sensors/tree is read-only
            print("[Permission Test] Verifying /sensors/tree as Viewer...")
            sensors_page.open_tree()
            sensors_page.tree_table.wait_for(state="visible", timeout=10000)
            attach_screenshot(page, "06_viewer_tree_view")

            assert not sensors_page.add_sensor_dropdown.is_visible(), (
                "Add Sensor button is unexpectedly visible for Viewer"
            )
            action_buttons_count = page.locator(
                "table#tree tbody a[href*='/edit'], table#tree tbody a[href*='/destroy'], table#tree tbody a.sensor-delete"
            ).count()
            print(f"[Permission Test] Viewer tree action buttons count: {action_buttons_count}")
            assert action_buttons_count == 0, (
                f"Viewer unexpectedly has {action_buttons_count} sensor edit/delete action buttons"
            )

            # Assert /users access is strictly blocked
            print("[Permission Test] Verifying /users access restriction as Viewer...")
            users_page.open_users()
            page.wait_for_load_state("domcontentloaded")
            attach_screenshot(page, "07_viewer_blocked_users_url")

            # Must be redirected away from /users or display access denied
            assert "/users" not in page.url or "overview" in page.url or "dashboard" in page.url, (
                f"Viewer was not redirected from /users: {page.url}"
            )
            # Privilege denial alert must be displayed
            alerts = page.locator(".alert-danger, .alert-warning").all_inner_texts()
            print(f"[Permission Test] Viewer privilege alert: {alerts}")
            assert any("privilege" in a.lower() or "privilegio" in a.lower() for a in alerts), (
                f"Expected privilege denial alert, got: {alerts}"
            )

            # -------------------------------------------------------------
            # Part 2: Administrator Privileges
            # -------------------------------------------------------------
            print(f"[Permission Test] Part 2: Logging in as created Administrator '{admin_username}'...")
            login_page.logout()
            login_page.login(username=admin_username, password=admin_password)
            page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

            # Assert /sensors/tree has Add Sensor enabled
            print("[Permission Test] Verifying /sensors/tree as Administrator...")
            sensors_page.open_tree()
            sensors_page.tree_table.wait_for(state="visible", timeout=10000)
            attach_screenshot(page, "08_admin_tree_view")
            expect(sensors_page.add_sensor_dropdown).to_be_visible(timeout=10000)

            # Assert /users access is granted
            print("[Permission Test] Verifying /users access as Administrator...")
            users_page.open_users()
            attach_screenshot(page, "09_admin_users_view")
            assert "/users" in page.url, f"Administrator unexpectedly redirected away from /users: {page.url}"
            assert users_page.users_table.is_visible(), "Users table not visible for Administrator"
            print("[Permission Test] All role permission boundaries confirmed.")

        finally:
            # -------------------------------------------------------------
            # Teardown: Super Admin deletes test users
            # -------------------------------------------------------------
            print("[Permission Test Cleanup] Logging back as Super Admin to delete test users...")
            try:
                login_page.logout()
                login_page.login(username=settings.web_user, password=settings.web_password)
                page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

                users_page.open_users()
                for u in [viewer_username, admin_username]:
                    if users_page.is_user_present(u):
                        print(f"[Permission Test Cleanup] Deleting '{u}'...")
                        deleted = users_page.delete_user(u)
                        assert deleted or not users_page.is_user_present(u), f"Deletion failed for '{u}'"
                        print(f"[Permission Test Cleanup] '{u}' deleted.")
            except Exception as e:
                print(f"[Permission Test Cleanup Warning] Teardown error: {e}")
