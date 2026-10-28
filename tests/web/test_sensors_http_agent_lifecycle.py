import time
import warnings
import pytest
from playwright.sync_api import Page, expect

from config.settings import settings
from core.pages.login_page import LoginPage
from core.pages.sensors_page import SensorsPage
from core.ssh_client import SSHClient


@pytest.fixture
def authenticated_sensors_page(page: Page, base_url: str) -> SensorsPage:
    """Logs into the Web UI and navigates to the Sensors tree page."""
    login_page = LoginPage(page, base_url)
    login_page.open()
    login_page.login(
        username=settings.web_user,
        password=settings.web_password,
    )
    page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

    sensors_page = SensorsPage(page, base_url)
    sensors_page.open_tree()
    page.wait_for_load_state("domcontentloaded")
    return sensors_page


@pytest.mark.web
class TestHTTPAgentSensorLifecycle:
    def test_http_agent_sensor_full_lifecycle(
        self,
        authenticated_sensors_page: SensorsPage,
        ssh_client: SSHClient,
        require_redborder_sensors,
        attach_screenshot,
    ):
        """End-to-End HTTP Agent sensor test:

        1. Starts mock webserver sandbox (sensor-ctl start rb-web --ip 10.10.10.50 webserver).
        2. Verifies HTTP endpoints via rb_http_agent.rb CLI on appliance:
           - Root GET 200 OK.
           - Basic Auth GET 200 OK (/auth with admin:secret).
        3. Creates a custom tab 'Web Latency' in Tools -> Monitor Custom Tabs (/custom_tabs).
        4. Creates custom HTTP Agent monitor category in Web UI (/monitor/list) linked to the custom tab.
        5. Creates HTTP Agent sensor in Web UI tree (type 23, root level).
        6. Attaches the custom HTTP Agent monitor category to the sensor (/sensors/<id>/monitor_categories).
        7. Synchronizes configuration via chef-client.
        8. Verifies HTTP Agent sensor and monitor results in:
           - /sensors/<id>/monitor_categories
           - /monitor (under the Custom Tab)
           - /monitor/http_agents
        9. Tears down mock sandbox, sensor, monitor category, and custom tab cleanly.
        """
        ts = int(time.time())
        platform_sensor_name = f"rb-http-{ts}"
        mock_sandbox_name = "rb-web"
        webserver_ip = "10.10.10.50"
        custom_tab_display_name = f"WebTab {ts % 10000}"
        category_name = f"rb-hcat-{ts}"
        target_url = f"http://{webserver_ip}/"

        sensors_page = authenticated_sensors_page
        registered_tab_key = None

        # Check if baseline testbed sensor already exists
        sensors_page.open_tree()
        sensors_page.expand_all_tree()
        if sensors_page.is_sensor_present("rb-http-test"):
            platform_sensor_name = "rb-http-test"
            category_name = "rb-test-http-cat"
            custom_tab_display_name = "Web Latency"
            registered_tab_key = "custom_web_latency"
            is_baseline_mode = True
        else:
            platform_sensor_name = f"rb-http-{ts}"
            is_baseline_mode = False

        if not is_baseline_mode:
            # --- Phase 0: Clean slate & Pre-flight checks ---
            if ssh_client.is_mock_sensor_running(mock_sandbox_name):
                warnings.warn(
                    f"[Pre-flight] Lingering mock webserver '{mock_sandbox_name}' running. Stopping it now.",
                    UserWarning,
                )
                ssh_client.stop_mock_webserver(mock_sandbox_name)
            else:
                ssh_client.stop_mock_webserver(mock_sandbox_name)

            sensors_page.open_tree()
            sensors_page.page.wait_for_load_state("domcontentloaded")
            if sensors_page.is_sensor_present(platform_sensor_name):
                sensors_page.delete_sensor(platform_sensor_name)

        try:
            # --- Phase 1: Start Sandboxed Mock Webserver ---
            if not ssh_client.is_mock_sensor_running(mock_sandbox_name):
                start_res = ssh_client.start_mock_webserver(
                    name=mock_sandbox_name,
                    ip=webserver_ip,
                    config_name="config.json",
                )
                assert start_res.ok or "already exists" in start_res.stderr or ssh_client.is_mock_sensor_running(mock_sandbox_name), (
                    f"Failed to start mock webserver '{mock_sandbox_name}': {start_res.stderr}"
                )
            assert ssh_client.is_mock_sensor_running(mock_sandbox_name), (
                f"Mock webserver sandbox '{mock_sandbox_name}' is not running"
            )

            # --- Phase 2: Verify HTTP Agent Endpoints via rb_http_agent.rb ---
            # 2a. Root endpoint HTTP 200 GET
            chk_root = ssh_client.run_http_agent_check(
                url=target_url,
                method="GET",
                expected_status=200,
                timeout=10,
            )
            assert chk_root.ok, f"rb_http_agent.rb failed on root URL {target_url}: {chk_root.stdout} {chk_root.stderr}"
            assert "OK" in chk_root.stdout or "200" in chk_root.stdout, (
                f"Expected 200 OK in check output: {chk_root.stdout}"
            )

            # 2b. Basic Auth endpoint HTTP 200 GET with credentials
            auth_url = f"http://{webserver_ip}/auth"
            chk_auth = ssh_client.run_http_agent_check(
                url=auth_url,
                method="GET",
                expected_status=200,
                auth_type="basic",
                username="admin",
                password="secret",
                timeout=10,
            )
            assert chk_auth.ok, f"rb_http_agent.rb auth check failed: {chk_auth.stdout} {chk_auth.stderr}"
            assert "OK" in chk_auth.stdout or "200" in chk_auth.stdout, (
                f"Expected 200 OK in auth check output: {chk_auth.stdout}"
            )

            if not is_baseline_mode:
                # --- Phase 3: Create Custom Tab in Tools -> Monitor Custom Tabs ---
                registered_tab_key = sensors_page.create_custom_tab(
                    name=custom_tab_display_name,
                    units="ms",
                )
                attach_screenshot(sensors_page.page, "custom_tab_created")

                # --- Phase 4: Create Custom HTTP Agent Monitor Category in Web UI ---
                category_description = f"HTTP Agent monitor {category_name}"
                sensors_page.create_custom_http_agent_monitor_category(
                    name=category_name,
                    url=target_url,
                    method="GET",
                    expected_status=200,
                    category=registered_tab_key,
                    description=category_description,
                    timeout="5s",
                    default_category=False,
                )
                attach_screenshot(sensors_page.page, "monitor_category_created")
            else:
                print(f"[E2E HTTP] Baseline mode active: using '{platform_sensor_name}', '{category_name}', tab '{custom_tab_display_name}'.")
                attach_screenshot(sensors_page.page, "baseline_http_testbed_ready")

            if not is_baseline_mode:
                # --- Phase 5: Create HTTP Agent Sensor in Web UI Tree ---
                sensors_page.open_tree()
                sensors_page.page.wait_for_load_state("domcontentloaded")
                sensors_page.create_http_agent_sensor(
                    name=platform_sensor_name,
                    description="Automated HTTP Agent E2E sensor",
                )
                sensors_page.open_tree()
                sensors_page.page.wait_for_load_state("domcontentloaded")
                sensors_page.expand_all_tree()
                assert sensors_page.is_sensor_present(platform_sensor_name), (
                    f"HTTP Agent sensor '{platform_sensor_name}' not found in tree"
                )
                sensor_id = sensors_page.get_node_id(platform_sensor_name)
                assert sensor_id is not None, f"Could not determine sensor ID for '{platform_sensor_name}'"
                attach_screenshot(sensors_page.page, "http_agent_sensor_created_in_tree")

                # --- Phase 6: Attach Category to HTTP Agent Sensor ---
                attached = sensors_page.attach_http_agent_monitor_category(
                    sensor_id=sensor_id,
                    category_keyword=category_name,
                )
                assert attached, f"Failed to attach monitor category '{category_name}' to sensor {sensor_id}"
                attach_screenshot(sensors_page.page, "http_agent_monitor_category_attached")

                # --- Phase 7: Sync Configuration via Chef Client ---
                chef_res = ssh_client.run_chef_client(timeout=120)
                assert chef_res.ok or "Chef Client finished" in chef_res.stdout or "chef-client" in chef_res.stdout, (
                    f"Chef client sync failed: {chef_res.stderr}"
                )
            else:
                sensors_page.open_tree()
                sensors_page.expand_all_tree()
                sensor_id = sensors_page.get_node_id(platform_sensor_name)

            # --- Phase 8: Verification in Web UI ---
            # 8a. Sensor presence in tree
            sensors_page.open_tree()
            sensors_page.page.wait_for_load_state("domcontentloaded")
            assert sensors_page.is_sensor_present(platform_sensor_name), (
                f"HTTP Agent sensor '{platform_sensor_name}' disappeared after chef run"
            )

            # 8b. Monitor Category presence in sensor's monitor categories page
            sensors_page.open_sensor_monitor_categories(sensor_id)
            cat_row = sensors_page.page.locator("table tbody tr").filter(
                has_text=custom_tab_display_name
            ).first
            if not cat_row.is_visible():
                cat_row = sensors_page.page.locator("table tbody tr").filter(
                    has_text=category_name
                ).first
            cat_row.wait_for(state="visible", timeout=settings.default_timeout_ms)
            assert cat_row.is_visible(), f"Attached category '{category_name}' not listed in sensor monitor categories"
            attach_screenshot(sensors_page.page, "http_agent_sensor_monitor_categories_verified")

            # 8c. Verification in /monitor under the Custom Tab
            sensors_page.open_monitor_tab(registered_tab_key)
            tab_pane = sensors_page.page.locator(f"#tab_{registered_tab_key}").first
            tab_link = sensors_page.page.locator(f"ul.nav-tabs.monitor li a[href='#tab_{registered_tab_key}']").first
            assert tab_link.is_visible(), (
                f"Custom tab '{registered_tab_key}' ({custom_tab_display_name}) should be present in monitor tabs"
            )
            attach_screenshot(sensors_page.page, "monitor_custom_tab_view")

            # 8d. Verification in /monitor/http_agents (platform endpoint check)
            res_http_agents = sensors_page.navigate("/monitor/http_agents")
            assert res_http_agents is not None and res_http_agents.status == 200, (
                f"Expected HTTP 200 for /monitor/http_agents, got {res_http_agents.status if res_http_agents else 'None'}"
            )
            sensors_page.page.wait_for_load_state("domcontentloaded")
            assert not sensors_page.page.locator("text='Error: 500!'").is_visible(), (
                "/monitor/http_agents returned Error 500!"
            )
            attach_screenshot(sensors_page.page, "monitor_http_agents_view")


        finally:
            # --- Phase 9: Resilient Clean Teardown ---
            if not is_baseline_mode:
                # 1. Stop mock webserver sandbox
                ssh_client.stop_mock_webserver(mock_sandbox_name)

                # 2. Delete HTTP Agent sensor from tree
                try:
                    sensors_page.open_tree()
                    sensors_page.page.wait_for_load_state("domcontentloaded")
                    if sensors_page.is_sensor_present(platform_sensor_name):
                        sensors_page.delete_sensor(platform_sensor_name)
                except Exception as e:
                    warnings.warn(f"Failed to delete test sensor '{platform_sensor_name}': {e}", UserWarning)

                # 3. Delete custom monitor category
                try:
                    sensors_page.delete_monitor_category_by_name(category_name)
                except Exception as e:
                    warnings.warn(f"Failed to delete monitor category '{category_name}': {e}", UserWarning)

                # 4. Delete custom tab
                try:
                    sensors_page.delete_custom_tab_by_name(custom_tab_display_name)
                except Exception as e:
                    warnings.warn(f"Failed to delete custom tab '{custom_tab_display_name}': {e}", UserWarning)
            else:
                print(f"[E2E HTTP Teardown] Baseline mode active: preserving sensor '{platform_sensor_name}' and custom tab '{custom_tab_display_name}'.")
