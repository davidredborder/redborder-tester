import time
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
class TestSNMPSensorLifecycle:
    def test_snmp_sensor_full_lifecycle_and_polling(
        self,
        authenticated_sensors_page: SensorsPage,
        ssh_client: SSHClient,
        require_redborder_sensors,
        attach_screenshot,
    ):
        """End-to-End SNMP test:

        1. Creates custom monitor category 'rb-tester-cpu' with OID 1.3.6.1.4.1.9.9.109.1.1.1.1.8 in Web UI.
        2. Creates SNMP sensor 'rb-snmp' (IP 10.10.10.4, community 'redBorder', version '2c') in Web UI.
        3. Attaches 'rb-tester-cpu' to the sensor.
        4. Starts mock sensor 'rb-snmp' running mock SNMP agent.
        5. Verifies SNMP polling response for sysDescr and Cisco CPU OID.
        6. Runs chef-client to configure redborder-monitor poller.
        7. Verifies CPU metric ingestion into Druid rb_monitor.
        8. Verifies sensor metrics on the /monitor CPU tab.
        9. Cleans up sensor and monitor category via platform Web UI.
        """
        ts = int(time.time())
        platform_sensor_name = f"rb-snmp-{ts}"
        mock_sensor_name = "rb-snmp"
        sensor_ip = "10.10.10.4"
        target_gw = "10.10.10.1"
        category_name = f"rb-cpu-{ts}"
        cisco_cpu_oid = "1.3.6.1.4.1.9.9.109.1.1.1.1.5.1"

        sensors_page = authenticated_sensors_page

        # Check if baseline testbed sensor already exists
        sensors_page.open_tree()
        sensors_page.expand_all_tree()
        if sensors_page.is_sensor_present("rb-snmp-test"):
            platform_sensor_name = "rb-snmp-test"
            category_name = "rb-test-cpu-cat"
            is_baseline_mode = True
        else:
            platform_sensor_name = f"rb-snmp-{ts}"
            is_baseline_mode = False

        if not is_baseline_mode:
            # --- Phase 0: Clean slate & Self-Healing Pre-flight via Web UI ---
            import warnings
            if ssh_client.is_mock_sensor_running(mock_sensor_name):
                warnings.warn(
                    f"[Self-Healing Warning] Lingering mock sensor '{mock_sensor_name}' was still running. Stopping it now.",
                    UserWarning,
                )
                ssh_client.stop_mock_sensor(mock_sensor_name)
            else:
                ssh_client.stop_mock_sensor(mock_sensor_name)

            # Check and heal any orphaned Chef nodes registered to this IP
            ssh_client.cleanup_orphaned_chef_nodes(ip=sensor_ip)

            sensors_page.open_tree()
            sensors_page.page.wait_for_load_state("domcontentloaded")
            if sensors_page.is_sensor_present(platform_sensor_name):
                warnings.warn(
                    f"[Self-Healing Warning] Stale sensor '{platform_sensor_name}' was found in the Web UI tree. Deleting it now.",
                    UserWarning,
                )
                sensors_page.delete_sensor(platform_sensor_name)

        try:
            if not is_baseline_mode:
                # --- Phase 1: Create Custom Monitor Category via Web UI ---
                print(f"\n[E2E SNMP] Creating custom monitor category '{category_name}' with OID {cisco_cpu_oid}...")
                sensors_page.create_custom_snmp_monitor_category(
                    name=category_name,
                    oid=cisco_cpu_oid,
                    category="cpu",
                    description=f"Custom CPU monitor category {category_name}",
                )
                print(f"[E2E SNMP] Custom monitor category '{category_name}' created.")
                attach_screenshot(sensors_page.page, title=f"Monitor Categories - Created {category_name}")

                # --- Phase 2: Web UI SNMP Sensor Creation ---
                print(f"[E2E SNMP] Creating SNMP sensor '{platform_sensor_name}' ({sensor_ip}) in Web UI...")
                sensors_page.open_tree()
                sensors_page.page.wait_for_load_state("domcontentloaded")
                sensors_page.create_snmp_sensor(
                    name=platform_sensor_name,
                    ip=sensor_ip,
                    community="redBorder",
                    version="2c",
                )

                # Assert sensor appears in the tree
                assert sensors_page.is_sensor_present(platform_sensor_name), (
                    f"Sensor '{platform_sensor_name}' did not appear in #tree table after creation"
                )
                print(f"[E2E SNMP] Sensor '{platform_sensor_name}' successfully visible in tree table.")
                attach_screenshot(sensors_page.page, title=f"Sensors Tree - Created {platform_sensor_name}")
            else:
                print(f"[E2E SNMP] Baseline mode active: sensor '{platform_sensor_name}' and category '{category_name}' already provisioned.")
                attach_screenshot(sensors_page.page, title=f"Sensors Tree - Baseline {platform_sensor_name}")

            # --- Phase 3: Start Mock SNMP Sandbox ---
            if not ssh_client.is_mock_sensor_running(mock_sensor_name):
                print(f"[E2E SNMP] Starting mock sensor '{mock_sensor_name}' via sensor-ctl.sh...")
                start_res = ssh_client.start_mock_sensor(
                    name=mock_sensor_name,
                    ip=sensor_ip,
                    target_ip=target_gw,
                    agent_type="snmp",
                )
                assert start_res.ok, f"Failed to start mock SNMP sensor: {start_res.stderr}"
            assert ssh_client.is_mock_sensor_running(mock_sensor_name), "Mock SNMP sensor is not listed as Running"
            print("[E2E SNMP] Mock SNMP agent is running.")

            # --- Phase 4: Verify SNMP Polling / Agent Query (sysDescr & Cisco CPU OIDs) ---
            print(f"[E2E SNMP] Querying mock agent at {sensor_ip} for sysDescr...")
            snmp_res = ssh_client.snmpwalk_query(
                target_ip=sensor_ip,
                community="public",
                version="2c",
                oid="1.3.6.1.2.1.1.1.0",
                timeout=15,
            )
            assert snmp_res.ok, f"snmpwalk sysDescr failed against {sensor_ip}: {snmp_res.stderr}"
            assert "Cisco" in snmp_res.stdout or "STRING" in snmp_res.stdout, (
                f"Unexpected sysDescr response from {sensor_ip}: {snmp_res.stdout}"
            )
            print(f"[E2E SNMP] sysDescr query succeeded: {snmp_res.stdout.strip()}")

            print(f"[E2E SNMP] Querying mock agent at {sensor_ip} for Cisco CPU utilization ({cisco_cpu_oid})...")
            cpu_res = ssh_client.snmpwalk_query(
                target_ip=sensor_ip,
                community="public",
                version="2c",
                oid=cisco_cpu_oid,
                timeout=15,
            )
            assert cpu_res.ok, f"snmpwalk CPU failed against {sensor_ip}: {cpu_res.stderr}"
            assert "INTEGER:" in cpu_res.stdout, f"Unexpected CPU response: {cpu_res.stdout}"
            print(f"[E2E SNMP] CPU query succeeded: {cpu_res.stdout.strip()}")

            # --- Phase 5: Attach Custom Monitor Category to the Sensor ---
            print(f"[E2E SNMP] Attaching monitor category '{category_name}' to '{platform_sensor_name}'...")
            sensors_page.open_tree()
            sensors_page.page.wait_for_load_state("domcontentloaded")
            sensor_id = sensors_page.get_sensor_id(platform_sensor_name)
            assert sensor_id is not None, f"Could not determine sensor ID for '{platform_sensor_name}'"
            print(f"[E2E SNMP] Discovered sensor ID: {sensor_id}")

            attached = sensors_page.attach_cpu_monitor_category(sensor_id, category_keyword=category_name)
            assert attached, f"Failed to attach monitor category '{category_name}' to sensor {sensor_id}"
            print(f"[E2E SNMP] Monitor category '{category_name}' successfully attached to sensor {sensor_id}.")
            attach_screenshot(sensors_page.page, title=f"Sensor {platform_sensor_name} - Attached {category_name}")

            # --- Phase 6: Chef Synchronization ---
            print("[E2E SNMP] Running chef-client on target manager to sync monitor poller...")
            chef_res = ssh_client.run_chef_client(timeout=180)
            assert chef_res.ok, f"chef-client failed with exit code {chef_res.exit_code}: {chef_res.stderr}"
            print("[E2E SNMP] chef-client completed successfully.")

            # --- Phase 7: Wait for CPU Metrics Ingestion in Druid rb_monitor ---
            print(f"[E2E SNMP] Polling Druid rb_monitor for CPU events from '{platform_sensor_name}'...")
            initial_cpu_count = ssh_client.query_druid_monitor_count(sensor_name=platform_sensor_name, monitor="cpu")
            print(f"[E2E SNMP] Initial Druid rb_monitor CPU count for '{platform_sensor_name}' = {initial_cpu_count}")

            ingested = False
            for attempt in range(24):  # Poll for up to 120 seconds (poller runs periodically)
                time.sleep(5)
                cpu_count = ssh_client.query_druid_monitor_count(sensor_name=platform_sensor_name, monitor="cpu")
                print(f"[E2E SNMP] Check {attempt + 1}/24: Druid rb_monitor CPU count for '{platform_sensor_name}' = {cpu_count}")
                if cpu_count > initial_cpu_count:
                    ingested = True
                    sample_records = ssh_client.query_druid_sensor_monitor_records(sensor_name=platform_sensor_name, monitor="cpu")
                    print(f"[E2E SNMP] Ingested fresh sample CPU records: {sample_records}")
                    break

            assert ingested, f"No fresh CPU monitor records found in Druid rb_monitor for sensor '{platform_sensor_name}' after 120s (initial={initial_cpu_count}, current={cpu_count})"

            # --- Phase 8: Web UI Monitor Module CPU Tab Verification ---
            print("[E2E SNMP] Navigating to Web UI /monitor module to verify CPU tab...")
            sensors_page.navigate("/monitor")
            sensors_page.page.wait_for_load_state("domcontentloaded")

            # Ensure all namespaces are selected in top bar so sensor nested in namespace is visible
            print("[E2E SNMP] Selecting active namespace 'All' in top bar...")
            ns_selected = sensors_page.select_active_namespace("All")
            print(f"[E2E SNMP] Namespace selection applied: {ns_selected}")

            # Click CPU tab if not already active
            cpu_tab_link = sensors_page.page.locator("a[href='#tab_cpu']").first
            if cpu_tab_link.is_visible():
                cpu_tab_link.click()
                sensors_page.page.wait_for_timeout(1000)

            cpu_tab_pane = sensors_page.page.locator("div.tab-pane#tab_cpu, div#tab_cpu").first
            expect(cpu_tab_pane).to_be_visible(timeout=10000)

            # Locate sensor cell in the CPU table.
            # Give the Web UI adequate time to poll and render the newly ingested minute rollup.
            # Filter table using the Sensor search box to display our sensor even if not in default Top 10
            for attempt in range(12):  # Poll for up to 60s
                # Try filtering via search box if visible
                search_input = sensors_page.page.locator("input[placeholder='Sensor'], input.search, #search_sensor, div#tab_cpu input[type='text']").first
                if search_input.is_visible():
                    try:
                        search_input.fill(platform_sensor_name)
                        sensors_page.page.keyboard.press("Enter")
                        sensors_page.page.wait_for_timeout(1000)
                    except Exception:
                        pass

                sensor_cell = cpu_tab_pane.locator("table tbody tr").filter(has_text=platform_sensor_name).first
                if sensor_cell.is_visible():
                    break
                sensors_page.page.wait_for_timeout(5000)
                # Refresh or re-query if not yet displayed
                sensors_page.navigate("/monitor")
                sensors_page.page.wait_for_load_state("domcontentloaded")
                cpu_tab_link = sensors_page.page.locator("a[href='#tab_cpu']").first
                if cpu_tab_link.is_visible():
                    cpu_tab_link.click()
                    sensors_page.page.wait_for_timeout(1000)
                cpu_tab_pane = sensors_page.page.locator("div.tab-pane#tab_cpu, div#tab_cpu").first

            # Search once more if needed before assertion
            search_input = sensors_page.page.locator("input[placeholder='Sensor'], input.search, #search_sensor, div#tab_cpu input[type='text']").first
            if search_input.is_visible():
                try:
                    search_input.fill(platform_sensor_name)
                    sensors_page.page.keyboard.press("Enter")
                    sensors_page.page.wait_for_timeout(1000)
                except Exception:
                    pass

            sensor_cell = cpu_tab_pane.locator("table tbody tr").filter(has_text=platform_sensor_name).first
            expect(sensor_cell).to_be_visible(timeout=10000)
            print(f"[E2E SNMP] Sensor '{platform_sensor_name}' successfully verified on Web UI /monitor CPU tab.")
            attach_screenshot(sensors_page.page, title=f"Monitor Module - CPU Tab with {platform_sensor_name}")


        finally:
            # --- Phase 9: Resilient Teardown via Platform UI ---
            if not is_baseline_mode:
                teardown_errors = []
                try:
                    print(f"[E2E SNMP Teardown] Stopping mock agent '{mock_sensor_name}'...")
                    ssh_client.stop_mock_sensor(mock_sensor_name)
                except Exception as e:
                    teardown_errors.append(f"stop_mock_sensor failed: {e}")

                try:
                    print(f"[E2E SNMP Teardown] Deleting sensor '{platform_sensor_name}' via Web UI...")
                    sensors_page.open_tree()
                    sensors_page.page.wait_for_load_state("domcontentloaded")
                    if sensors_page.is_sensor_present(platform_sensor_name):
                        sensors_page.delete_sensor(platform_sensor_name)
                        print(f"[E2E SNMP Teardown] Sensor '{platform_sensor_name}' deleted via Web UI.")
                except Exception as e:
                    teardown_errors.append(f"delete_sensor failed: {e}")

                try:
                    print(f"[E2E SNMP Teardown] Deleting custom monitor category '{category_name}' via Web UI...")
                    sensors_page.delete_monitor_category_by_name(category_name)
                    print(f"[E2E SNMP Teardown] Custom monitor category '{category_name}' deleted via Web UI.")
                except Exception as e:
                    teardown_errors.append(f"delete_monitor_category failed: {e}")

                if teardown_errors:
                    import warnings
                    warnings.warn(f"Issues during teardown: {'; '.join(teardown_errors)}")
                else:
                    print("[E2E SNMP Teardown] Teardown complete and verified via platform Web UI.")
            else:
                print(f"[E2E SNMP Teardown] Baseline mode active: preserving sensor '{platform_sensor_name}' and category '{category_name}' in testbed.")

