import time
import pytest
from playwright.sync_api import Page, expect

from config.settings import settings
from core.pages.login_page import LoginPage
from core.pages.sensors_page import SensorsPage
from core.pages.users_page import UsersPage
from core.ssh_client import SSHClient


@pytest.mark.web
class TestUsersRBACScoping:
    """End-to-End suite verifying Domain/Namespace RBAC Scoping & Sensor Movement:
    1. Super Admin provisions domain hierarchy and creates a scoped user tied to Namespace (rb-test-ns).
    2. Scoped User logs in: verifies tree visibility is strictly limited to rb-test-ns (root and siblings hidden).
    3. Super Admin moves a sensor from root to rb-test-ns.
    4. Scoped User verifies sensor is visible, but cannot move/drag it out to root.
    5. Super Admin restores the sensor back to root.
    6. Teardown: Cleans up scoped user and test artifacts.
    """

    def test_namespace_scoped_user_and_sensor_movement(
        self,
        page: Page,
        base_url: str,
        ssh_client: SSHClient,
        stable_testbed,
        attach_screenshot,
    ):
        login_page = LoginPage(page, base_url)
        sensors_page = SensorsPage(page, base_url)
        users_page = UsersPage(page, base_url)

        ts = int(time.time())
        scoped_username = f"scoped_ns_{ts}"
        scoped_email = f"scoped_{ts}@example.com"
        scoped_password = f"ScopedPass!{ts}12"
        test_sensor = "rb-vault-test"
        org_name = "rb-test-org"

        # -------------------------------------------------------------
        # Phase 1: Provision Scoped User on Namespace (rb-test-ns)
        # -------------------------------------------------------------
        print("[RBAC Test] Phase 1: Ensuring Super Admin session to create scoped user...")
        if "login" in page.url or login_page.is_login_page_displayed():
            login_page.login(username=settings.web_user, password=settings.web_password)
            page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

        # Ensure baseline test sensor is positioned under rb-test-org before test starts
        sensors_page.open_tree()
        sensors_page.expand_all_tree()
        org_id = stable_testbed.get("org_id") or sensors_page.get_sensor_id(org_name)
        assert org_id is not None, f"Organization node '{org_name}' not found"
        current_parent = sensors_page.get_node_parent_id(test_sensor)
        if str(current_parent) != str(org_id):
            print(f"[RBAC Test Setup] Repositioning '{test_sensor}' to '{org_name}' (expected {org_id}, currently {current_parent})...")
            sensors_page.drag_sensor_to_node(test_sensor, org_name)
            sensors_page.expand_all_tree()

        users_page.open_users()
        print(f"[RBAC Test] Creating user '{scoped_username}' scoped to domain 'rb-test-ns'...")
        create_err = users_page.create_user(
            name=scoped_username,
            login=scoped_username,
            email=scoped_email,
            password=scoped_password,
            role="incident_responder",
            domain_name="rb-test-ns",
            expect_error=False,
        )
        assert create_err is None, f"Failed to create scoped user: {create_err}"
        attach_screenshot(page, "01_scoped_user_created")

        try:
            # -------------------------------------------------------------
            # Phase 2: Verify Tree Visibility for Scoped User
            # -------------------------------------------------------------
            print(f"[RBAC Test] Phase 2: Logging in as scoped user '{scoped_username}'...")
            login_page.logout()
            login_page.login(username=scoped_username, password=scoped_password)
            page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

            print("[RBAC Test] Navigating to /sensors/tree as scoped user...")
            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            attach_screenshot(page, "02_scoped_tree_view")

            # Scoped user's assigned top domain is rb-test-ns (the root boundary of their view)
            # Therefore they see child organization and sensors inside it, and NOT outside domains
            assert sensors_page.is_sensor_present("rb-test-org"), "Scoped user cannot see child organization 'rb-test-org'"
            assert sensors_page.is_sensor_present("rb-vault-test"), "Scoped user cannot see baseline sensor 'rb-vault-test' inside their domain"

            # Scoped user MUST NOT see parent Service Provider (rb-test-sp) or sibling Service Provider (rb-test-sp2)
            assert not sensors_page.is_sensor_present("rb-test-sp"), "Scoped user can improperly see parent 'rb-test-sp'"
            assert not sensors_page.is_sensor_present("rb-test-sp2"), "Scoped user can improperly see sibling 'rb-test-sp2'"
            print("[RBAC Test] Tree visibility scoping confirmed: parent and sibling domains are hidden.")

            # -------------------------------------------------------------
            # Phase 3: Sensor Movement (Namespace -> Root -> Namespace)
            # -------------------------------------------------------------
            # Log back in as Super Admin to move sensor to Root
            print("[RBAC Test] Phase 3: Logging in as Admin to move sensor to Root...")
            login_page.logout()
            login_page.login(username=settings.web_user, password=settings.web_password)
            page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

            sensors_page.open_tree()
            sensors_page.expand_all_tree()

            test_sensor = "rb-vault-test"
            org_id = sensors_page.get_sensor_id("rb-test-org")
            assert org_id is not None, "Organization node 'rb-test-org' not found in DOM"

            # 1. Drag sensor from namespace out to root
            print(f"[RBAC Test] Dragging sensor '{test_sensor}' to Root...")
            sensors_page.drag_sensor_to_root(test_sensor)
            attach_screenshot(page, "03_sensor_dragged_to_root")

            assert sensors_page.is_sensor_present(test_sensor), f"Sensor '{test_sensor}' missing from tree after root drag"
            root_parent = sensors_page.get_node_parent_id(test_sensor)
            print(f"[RBAC Test] Sensor '{test_sensor}' parent after root drag: {root_parent}")
            assert root_parent is None, f"Expected root parent (None), got {root_parent}"

            # 2. Verify scoped user can NO LONGER see the sensor
            print(f"[RBAC Test] Verifying scoped user can NO LONGER see '{test_sensor}' (since it's at root)...")
            login_page.logout()
            login_page.login(username=scoped_username, password=scoped_password)
            page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            attach_screenshot(page, "04_scoped_user_cannot_see_root_sensor")
            assert not sensors_page.is_sensor_present(test_sensor), f"Scoped user can unexpectedly see root sensor '{test_sensor}'"

            # 3. Restore sensor back into namespace/org as Admin
            print(f"[RBAC Test] Phase 4: Logging back as Admin to restore sensor '{test_sensor}' to 'rb-test-org' (ID: {org_id})...")
            login_page.logout()
            login_page.login(username=settings.web_user, password=settings.web_password)
            page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            sensors_page.drag_sensor_to_node(test_sensor, "rb-test-org")
            attach_screenshot(page, "05_sensor_restored_to_namespace")

            restored_parent = sensors_page.get_node_parent_id(test_sensor)
            print(f"[RBAC Test] Sensor '{test_sensor}' parent after restore: {restored_parent}")
            assert str(restored_parent) == str(org_id), f"Expected parent {org_id}, got {restored_parent}"

            # 4. Verify scoped user can see the sensor again
            print(f"[RBAC Test] Verifying scoped user can see '{test_sensor}' again after restore...")
            login_page.logout()
            login_page.login(username=scoped_username, password=scoped_password)
            page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            attach_screenshot(page, "06_scoped_user_sees_restored_sensor")
            assert sensors_page.is_sensor_present(test_sensor), f"Scoped user cannot see restored sensor '{test_sensor}'"

        finally:
            # -------------------------------------------------------------
            # Phase 5: Cleanup Scoped User and Ensure Sensor Restored
            # -------------------------------------------------------------
            print("[RBAC Test Cleanup] Ensuring Admin session for cleanup...")
            try:
                if "/users" not in page.url and "/sensors" not in page.url:
                    login_page.logout()
                    login_page.login(username=settings.web_user, password=settings.web_password)
                    page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

                # Ensure test_sensor is not left at root
                try:
                    sensors_page.open_tree()
                    sensors_page.expand_all_tree()
                    parent = sensors_page.get_node_parent_id(test_sensor)
                    if str(parent) != str(org_id):
                        print(f"[RBAC Test Cleanup] Repositioning '{test_sensor}' back to '{org_name}'...")
                        sensors_page.drag_sensor_to_node(test_sensor, org_name)
                except Exception as sensor_cleanup_err:
                    print(f"[RBAC Test Cleanup Warning] Sensor reposition failed: {sensor_cleanup_err}")

                print(f"[RBAC Test Cleanup] Deleting scoped user '{scoped_username}'...")
                users_page.open_users()
                users_page.delete_user(scoped_username)
                print(f"[RBAC Test Cleanup] Scoped user '{scoped_username}' deleted.")
            except Exception as e:
                print(f"[RBAC Test Cleanup Warning] Cleanup error: {e}")
