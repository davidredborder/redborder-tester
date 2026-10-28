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
class TestVaultSensorLifecycle:
    def test_vault_sensor_full_lifecycle_and_syslog_ingestion(
        self,
        authenticated_sensors_page: SensorsPage,
        ssh_client: SSHClient,
        require_redborder_sensors,
        attach_screenshot,
    ):
        """End-to-End Vault (Syslog) test:

        1. Creates a Vault sensor 'vault1' (IP 10.10.10.3) in the Web UI.
        2. Syncs platform rsyslog / Kafka pipeline via chef-client.
        3. Starts mock sensor 'vault1' emitting syslog events via telemetry-agent.
        4. Verifies in Druid rb_vault table that events for sensor_name='vault1' and sensor_ip='10.10.10.3' are indexed.
        5. Captures screenshots and cleanly deletes the sensor and sandbox.
        """
        ts = int(time.time())
        platform_sensor_name = f"rb-vault-{ts}"
        mock_sensor_name = "rb-vault"
        sensor_ip = "10.10.10.3"
        target_gw = "10.10.10.1"

        sensors_page = authenticated_sensors_page

        # Check if baseline testbed sensor already exists
        sensors_page.open_tree()
        sensors_page.expand_all_tree()
        if sensors_page.is_sensor_present("rb-vault-test"):
            platform_sensor_name = "rb-vault-test"
            is_baseline_mode = True
        else:
            platform_sensor_name = f"rb-vault-{ts}"
            is_baseline_mode = False

        if not is_baseline_mode:
            # --- Phase 0: Clean slate & Self-Healing Pre-flight ---
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

            if sensors_page.is_sensor_present(platform_sensor_name):
                warnings.warn(
                    f"[Self-Healing Warning] Stale sensor '{platform_sensor_name}' was found in the Web UI tree. Deleting it now.",
                    UserWarning,
                )
                sensors_page.delete_sensor(platform_sensor_name)

        try:
            # --- Phase 1: Start Mock Sensor Sandbox & Converge Network Subnet ---
            # Starting the mock sensor sandbox (sensor-ctl.sh) creates the bridge interface
            # (br-10 / 10.10.10.0/24 link scope).
            #
            # WHY WE RUN CHEF-CLIENT AND WAIT HERE BEFORE THE WEB UI:
            # Redborder's PostgreSQL cookbook reads host routes via `ip route` to generate /var/lib/pgsql/data/pg_hba.conf.
            # Whenever a new bridge route (10.10.10.0/24) appears on the host, Chef detects that pg_hba.conf has changed
            # and issues `notifies :restart, 'service[postgresql]'`.
            #
            # If we were to create the Vault sensor in the Web UI first, a concurrent or delayed Chef run
            # would restart PostgreSQL right in the middle of Rails saving the sensor to Postgres, causing:
            #   "PQconsumeInput() FATAL: terminating connection due to administrator command"
            # which rolls back Rails' database transaction while leaving an orphaned Chef node behind.
            #
            # By starting the mock sandbox first and running chef-client to convergence BEFORE touching the Web UI,
            # pg_hba.conf is already updated and PostgreSQL has completed its restart and stabilized.
            if not is_baseline_mode:
                print(f"\n[E2E Vault] Phase 1: Starting mock sensor '{mock_sensor_name}' ({sensor_ip}) to establish network bridge...")
                start_res = ssh_client.start_mock_sensor(
                    name=mock_sensor_name,
                    ip=sensor_ip,
                    target_ip=target_gw,
                    agent_type="telemetry-agent",
                    extra_args=f"-mode syslog -port 514 -rate 5",
                )
                assert start_res.ok, f"Failed to start mock sensor: {start_res.stderr}"
                assert ssh_client.is_mock_sensor_running(mock_sensor_name), "Mock sensor is not listed as Running"

                print("[E2E Vault] Pre-converging chef-client and settling PostgreSQL before Web UI sensor creation...")
                converged = ssh_client.converge_chef_and_wait_druid(iterations=1, druid_timeout=30, chef_timeout=120)
                assert converged, "Chef convergence or Druid stabilization failed after starting mock sensor sandbox"
                time.sleep(5)  # Brief settling pause for PostgreSQL connection pool

                # --- Phase 2: Web UI Vault Sensor Creation ---
                print(f"[E2E Vault] Phase 2: Creating Vault sensor '{platform_sensor_name}' ({sensor_ip}) in Web UI...")
                sensors_page.create_vault_sensor(name=platform_sensor_name, ip=sensor_ip)

                # Assert sensor appears in the tree
                assert sensors_page.is_sensor_present(platform_sensor_name), (
                    f"Sensor '{platform_sensor_name}' did not appear in #tree table after creation"
                )
                print(f"[E2E Vault] Sensor '{platform_sensor_name}' successfully visible in tree table.")
                attach_screenshot(sensors_page.page, title=f"Sensors Tree - Created {platform_sensor_name}")

                # --- Phase 3: Chef Synchronization for Rsyslog Pipeline ---
                print("[E2E Vault] Phase 3: Running chef-client to configure rsyslog RFC5424 mapping for new sensor...")
                chef_res = ssh_client.run_chef_client(timeout=180)
                assert chef_res.ok, f"chef-client failed with exit code {chef_res.exit_code}: {chef_res.stderr}"
                print("[E2E Vault] chef-client completed successfully.")
            else:
                print(f"[E2E Vault] Baseline mode active: sensor '{platform_sensor_name}' is already provisioned and running.")
                attach_screenshot(sensors_page.page, title=f"Sensors Tree - Baseline {platform_sensor_name}")

            # --- Phase 4: Verify Druid Data Ingestion in rb_vault ---
            baseline_vault_count = ssh_client.query_druid_vault_count(
                sensor_name=platform_sensor_name, sensor_ip=sensor_ip
            )
            print(f"[E2E Vault] Baseline Druid rb_vault count for '{platform_sensor_name}' ({sensor_ip}): {baseline_vault_count}")
            print(f"[E2E Vault] Waiting for Syslog events from '{platform_sensor_name}' ({sensor_ip}) in Druid rb_vault...")
            ingested = False
            sample_logs = []
            for attempt in range(12):  # Poll for up to 60s
                time.sleep(5)
                current_vault_count = ssh_client.query_druid_vault_count(
                    sensor_name=platform_sensor_name, sensor_ip=sensor_ip
                )
                print(
                    f"[E2E Vault] Check {attempt + 1}/12: Druid rb_vault count for '{platform_sensor_name}' = {current_vault_count} "
                    f"(baseline = {baseline_vault_count})"
                )
                if current_vault_count > baseline_vault_count:
                    sample_logs = ssh_client.query_druid_sensor_vault_logs(sensor_name=platform_sensor_name, limit=3)
                    ingested = True
                    break

            assert ingested, (
                f"No new syslog events detected in Druid specifically for sensor '{platform_sensor_name}' ({sensor_ip})! "
                f"Initial: {baseline_vault_count}, Current: {ssh_client.query_druid_vault_count(sensor_name=platform_sensor_name, sensor_ip=sensor_ip)}"
            )

            print(f"[E2E Vault] Confirmed new syslog events for sensor '{platform_sensor_name}' ({sensor_ip}) in Druid rb_vault!")
            print(f"[E2E Vault] Sample Druid rb_vault record: {sample_logs[0] if sample_logs else 'N/A'}")

            # Verify that the ingested records match our sensor
            if sample_logs:
                assert sample_logs[0].get("sensor_name") == platform_sensor_name
                assert sample_logs[0].get("fromhost_ip") == sensor_ip

            # Capture tree screenshot after data verified
            attach_screenshot(sensors_page.page, title=f"Sensors Tree - Ingested {platform_sensor_name}")

        finally:
            # --- Phase 5: Resilient Teardown ---
            if not is_baseline_mode:
                teardown_errors = []
                try:
                    print(f"[E2E Vault Teardown] Stopping mock agent '{mock_sensor_name}'...")
                    ssh_client.stop_mock_sensor(mock_sensor_name)
                except Exception as e:
                    teardown_errors.append(f"stop_mock_sensor failed: {e}")

                try:
                    print(f"[E2E Vault Teardown] Deleting sensor '{platform_sensor_name}' from Web UI...")
                    sensors_page.open_tree()
                    sensors_page.page.wait_for_load_state("domcontentloaded")
                    if sensors_page.is_sensor_present(platform_sensor_name):
                        sensors_page.delete_sensor(platform_sensor_name)
                except Exception as e:
                    teardown_errors.append(f"delete_sensor failed: {e}")

                if teardown_errors:
                    import warnings
                    warnings.warn(f"Issues during teardown: {'; '.join(teardown_errors)}")
                else:
                    print("[E2E Vault Teardown] Teardown complete and verified.")
            else:
                print(f"[E2E Vault Teardown] Baseline mode active: preserving sensor '{platform_sensor_name}' in tree.")
