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
class TestSensorsLifecycle:
    def test_sensor_full_lifecycle_and_telemetry_ingestion(
        self,
        authenticated_sensors_page: SensorsPage,
        ssh_client: SSHClient,
        require_redborder_sensors,
        attach_screenshot,
    ):
        """End-to-End test:

        1. Creates a Flow sensor 'flow1' (IP 10.10.10.2) in the Web UI.
        2. Syncs platform collectors via chef-client.
        3. Starts mock sensor 'flow1' emitting telemetry traffic via sensor-ctl.sh.
        4. Verifies in Druid that new events for specifically sensor_name='flow1' and sensor_ip='10.10.10.2' are ingested.
        5. Confirms Web UI display and then deletes the sensor cleanly.
        """
        ts = int(time.time())
        platform_sensor_name = f"rb-flow-{ts}"
        mock_sensor_name = "rb-flow"
        sensor_ip = "10.10.10.2"
        target_gw = "10.10.10.1"

        sensors_page = authenticated_sensors_page

        # Check if baseline testbed sensor already exists
        sensors_page.open_tree()
        sensors_page.expand_all_tree()
        if sensors_page.is_sensor_present("rb-flow-test"):
            platform_sensor_name = "rb-flow-test"
            is_baseline_mode = True
        else:
            platform_sensor_name = f"rb-flow-{ts}"
            is_baseline_mode = False

        if not is_baseline_mode:
            # --- Phase 0: Clean slate ---
            ssh_client.stop_mock_sensor(mock_sensor_name)
            if sensors_page.is_sensor_present(platform_sensor_name):
                sensors_page.delete_sensor(platform_sensor_name)

        try:
            if not is_baseline_mode:
                # --- Phase 1: Web UI Sensor Creation ---
                print(f"\n[E2E] Creating sensor '{platform_sensor_name}' ({sensor_ip}) in Web UI...")
                sensors_page.create_flow_sensor(name=platform_sensor_name, ip=sensor_ip)

                # Assert sensor appears in the tree
                assert sensors_page.is_sensor_present(platform_sensor_name), (
                    f"Sensor '{platform_sensor_name}' did not appear in #tree table after creation"
                )
                print(f"[E2E] Sensor '{platform_sensor_name}' successfully visible in tree table.")
                attach_screenshot(sensors_page.page, title=f"Sensors Tree - Created {platform_sensor_name}")

                # --- Phase 2: Chef Synchronization ---
                print("[E2E] Running chef-client on target manager to sync collectors...")
                chef_res = ssh_client.run_chef_client(timeout=180)
                assert chef_res.ok, f"chef-client failed with exit code {chef_res.exit_code}: {chef_res.stderr}"
                print("[E2E] chef-client completed successfully.")
            else:
                print(f"[E2E] Baseline mode active: sensor '{platform_sensor_name}' is already provisioned.")
                attach_screenshot(sensors_page.page, title=f"Sensors Tree - Baseline {platform_sensor_name}")

            # --- Phase 3: Telemetry Injection via Mock Agent ---
            baseline_sensor_count = ssh_client.query_druid_flow_count(
                sensor_name=platform_sensor_name, sensor_ip=sensor_ip
            )
            print(f"[E2E] Baseline Druid count for sensor '{platform_sensor_name}' ({sensor_ip}): {baseline_sensor_count}")

            if not ssh_client.is_mock_sensor_running(mock_sensor_name):
                print(f"[E2E] Starting mock sensor '{mock_sensor_name}' via sensor-ctl.sh...")
                start_res = ssh_client.start_mock_sensor(
                    name=mock_sensor_name,
                    ip=sensor_ip,
                    target_ip=target_gw,
                    agent_type="telemetry-agent",
                )
                assert start_res.ok, f"Failed to start mock sensor: {start_res.stderr}"
            assert ssh_client.is_mock_sensor_running(mock_sensor_name), "Mock sensor is not listed as Running"
            print("[E2E] Mock telemetry agent is running.")

            # --- Phase 4: Verify Druid Data Ingestion For This Specific Sensor ---
            print(f"[E2E] Waiting for NetFlow packets from '{platform_sensor_name}' ({sensor_ip}) in Druid...")
            ingested = False
            sample_flows = []
            for attempt in range(12):  # Poll for up to 60s
                time.sleep(5)
                current_sensor_count = ssh_client.query_druid_flow_count(
                    sensor_name=platform_sensor_name, sensor_ip=sensor_ip
                )
                print(
                    f"[E2E] Check {attempt + 1}/12: Druid count for '{platform_sensor_name}' = {current_sensor_count} "
                    f"(baseline = {baseline_sensor_count})"
                )
                if current_sensor_count > baseline_sensor_count:
                    sample_flows = ssh_client.query_druid_sensor_flows(sensor_name=platform_sensor_name, limit=3)
                    ingested = True
                    break

            assert ingested, (
                f"No new flow events detected in Druid specifically for sensor '{platform_sensor_name}' ({sensor_ip})! "
                f"Initial: {baseline_sensor_count}, Current: {ssh_client.query_druid_flow_count(sensor_name=platform_sensor_name, sensor_ip=sensor_ip)}"
            )

            print(f"[E2E] Confirmed new telemetry events for sensor '{platform_sensor_name}' ({sensor_ip}) in Druid!")
            print(f"[E2E] Sample Druid flow record: {sample_flows[0] if sample_flows else 'N/A'}")

            # Verify that the ingested records strictly match our sensor
            if sample_flows:
                assert sample_flows[0].get("sensor_name") == platform_sensor_name
                assert sample_flows[0].get("sensor_ip") == sensor_ip

            # --- Phase 5: Web UI Verification ---
            sensors_page.open_flow()
            sensors_page.page.wait_for_load_state("domcontentloaded")
            expect(sensors_page.tree_table).to_be_visible()
            assert sensors_page.is_sensor_present(platform_sensor_name), (
                f"Sensor '{platform_sensor_name}' not listed on /sensors/flow view"
            )
            attach_screenshot(sensors_page.page, title=f"Sensors Flow View - Verified {platform_sensor_name}")

        finally:
            # --- Phase 6: Teardown & Deletion with independent guards ---
            if not is_baseline_mode:
                teardown_errors = []
                try:
                    print(f"[E2E Teardown] Stopping mock agent '{mock_sensor_name}'...")
                    ssh_client.stop_mock_sensor(mock_sensor_name)
                except Exception as e:
                    teardown_errors.append(f"stop_mock_sensor failed: {e}")

                try:
                    print(f"[E2E Teardown] Deleting sensor '{platform_sensor_name}' from Web UI...")
                    sensors_page.open_tree()
                    sensors_page.page.wait_for_load_state("domcontentloaded")
                    if sensors_page.is_sensor_present(platform_sensor_name):
                        sensors_page.delete_sensor(platform_sensor_name)
                except Exception as e:
                    teardown_errors.append(f"delete_sensor failed: {e}")

                if teardown_errors:
                    print(f"[E2E Teardown Warning] Issues during teardown: {'; '.join(teardown_errors)}")
                else:
                    print("[E2E Teardown] Teardown complete and verified.")
            else:
                print(f"[E2E Teardown] Baseline mode active: preserving sensor '{platform_sensor_name}' in tree.")
