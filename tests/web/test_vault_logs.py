import time
import pytest
from playwright.sync_api import Page, expect

from config.settings import settings
from core.pages.login_page import LoginPage
from core.pages.sensors_page import SensorsPage
from core.pages.vault_page import VaultPage
from core.ssh_client import SSHClient


@pytest.fixture
def authenticated_vault_page(page: Page, base_url: str) -> VaultPage:
    """Logs into the Web UI and navigates to the Vault module (/vault)."""
    login_page = LoginPage(page, base_url)
    login_page.open()
    login_page.login(
        username=settings.web_user,
        password=settings.web_password,
    )
    page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

    vault_page = VaultPage(page, base_url)
    vault_page.open_tops()
    return vault_page


@pytest.mark.web
class TestVaultLogs:
    """End-to-End suite verifying the Vault (Logs / Events) module (/vault):
    - Ingests mock vault syslog telemetry via redborder-sensors and verifies Druid rb_vault.
    - Confirms vault sensor in tree and confirms data visibility in /vault.
    - Tests active filtering by Sensor Name and App Name.
    - Saves the filter, clears active filters, reuses/applies saved filter (testing sharing).
    - Tests switching analysis views: Raw (/vault), Compare (/vault/comparative), Unique (/vault/cardinality), and Tops (/vault/tops).
    - Cleans up sensor, filters, and mock sensor processes.
    """

    def test_vault_logs_lifecycle_and_analysis(
        self,
        authenticated_vault_page: VaultPage,
        page: Page,
        base_url: str,
        ssh_client: SSHClient,
        require_redborder_sensors,
        attach_screenshot,
    ):
        vault_page = authenticated_vault_page
        sensors_page = SensorsPage(page, base_url)

        ts = int(time.time())
        short_id = str(ts)[-5:]
        saved_filter_title = f"Filter-Vault-{ts}"
        saved_filter_id = None
        sensor_ip = "10.10.10.3"

        # Check if baseline testbed sensor already exists
        sensors_page.open_tree()
        sensors_page.expand_all_tree()
        if sensors_page.is_sensor_present("rb-vault-test"):
            sensor_name = "rb-vault-test"
            mock_sensor_name = "rb-vault"
            is_baseline_mode = True
        else:
            sensor_name = f"vault-logs-{ts}"
            mock_sensor_name = f"vt{short_id}"
            is_baseline_mode = False

        if not is_baseline_mode:
            # Pre-cleanup
            ssh_client.stop_mock_sensor(mock_sensor_name)

        try:
            if not is_baseline_mode:
                # -------------------------------------------------------------
                # Phase 1: Create Vault Sensor in Tree & Sync Manager
                # -------------------------------------------------------------
                print(f"\n[Vault Test] Creating Vault sensor '{sensor_name}' in Web UI tree...")
                sensors_page.open_tree()
                sensors_page.create_vault_sensor(
                    name=sensor_name,
                    ip=sensor_ip,
                )
                assert sensors_page.is_sensor_present(sensor_name), f"Sensor '{sensor_name}' was not created in tree"

                # -------------------------------------------------------------
                # Phase 2: Start Mock Telemetry Agent & Verify Ingestion
                # -------------------------------------------------------------
                print(f"[Vault Test] Starting mock vault sensor '{mock_sensor_name}'...")
                res_start = ssh_client.start_mock_sensor(
                    name=mock_sensor_name,
                    ip=sensor_ip,
                    agent_type="syslog",
                    extra_flags="-mode syslog -port 514 -rate 5",
                )
                assert res_start.ok, f"Failed to start mock vault sensor: {res_start.stderr}"
            else:
                print(f"[Vault Test] Baseline mode active: reusing sensor '{sensor_name}' and running sandbox '{mock_sensor_name}'.")
                if not ssh_client.is_mock_sensor_running(mock_sensor_name):
                    ssh_client.start_mock_sensor(
                        name=mock_sensor_name,
                        ip=sensor_ip,
                        agent_type="syslog",
                        extra_flags="-mode syslog -port 514 -rate 5",
                    )

            # Check if vault logs exist in Druid rb_vault
            total_vault_logs = ssh_client.query_druid_vault_count()
            print(f"[Vault Test] Total rb_vault records in Druid: {total_vault_logs}")
            assert total_vault_logs > 0, "No log events found in Druid rb_vault database"

            # Use the active tree sensor to ensure it exists in the Web UI search dropdown
            filter_sensor_name = sensor_name
            filter_app_name = "security-engine"

            # Dynamically query Druid for the active app_name across partitioned tables
            tables = ssh_client.get_druid_tables("rb_vault")
            for tbl in tables:
                data = ssh_client.execute_druid_sql(
                    f'SELECT app_name, COUNT(*) as cnt '
                    f'FROM "{tbl}" '
                    f'WHERE app_name IS NOT NULL '
                    f'GROUP BY 1 '
                    f'ORDER BY cnt DESC '
                    f'LIMIT 1'
                )
                if data and len(data) > 0 and data[0].get("app_name"):
                    filter_app_name = data[0]["app_name"]
                    break

            print(f"[Vault Test] Active filter parameters: sensor='{filter_sensor_name}', app='{filter_app_name}'")

            # -------------------------------------------------------------
            # Phase 3: Vault Overview (Tops View)
            # -------------------------------------------------------------
            print("[Vault Test] Navigating to /vault/tops and verifying vault dashboard...")
            vault_page.open_tops()
            attach_screenshot(page, "01_vault_logs_overview")
            expect(vault_page.tops_table).to_be_visible(timeout=10000)

            # -------------------------------------------------------------
            # Phase 4: Filtering by Sensor Name & App Name
            # -------------------------------------------------------------
            print(f"[Vault Test] Applying active filter: sensor_name={filter_sensor_name}...")
            vault_page.apply_filter(dimension="sensor_name", value=filter_sensor_name)
            attach_screenshot(page, "02_vault_filter_sensor_name")

            print(f"[Vault Test] Applying active filter: app_name={filter_app_name}...")
            vault_page.apply_filter(dimension="app_name", value=filter_app_name)

            # Verify that both active filters are registered in the toolbar badge
            active_badge = page.locator("li[data-step='1'] a.dropdown-toggle, li.filter-red a.dropdown-toggle, a.dropdown-toggle:has-text('Filters:')").first
            expect(active_badge).to_contain_text("2", timeout=5000)

            # Switch to App Name tab to view filtered statistics by App Name
            print("[Vault Test] Switching to 'App Name' tab...")
            vault_page.select_tab("app_name")
            attach_screenshot(page, "03_vault_filter_app_name_tab")

            # -------------------------------------------------------------
            # Phase 5: Save Filter, Clear Active, & Reuse/Load Saved Filter
            # -------------------------------------------------------------
            print(f"[Vault Test] Saving filter as '{saved_filter_title}' (public sharing enabled) via Web UI...")
            saved_filter_id = vault_page.save_current_filter(
                title=saved_filter_title,
                public=True,
                items=[
                    {"column": "sensor_name", "operator": "is", "value": filter_sensor_name},
                    {"column": "app_name", "operator": "is", "value": filter_app_name},
                ],
            )
            assert saved_filter_id is not None, "Failed to save filter"
            print(f"[Vault Test] Saved filter created with ID: {saved_filter_id}")

            print("[Vault Test] Verifying saved filter in /saved/vault_filters...")
            vault_page.open_saved_filters_page()
            attach_screenshot(page, "04_saved_filters_table")
            expect(page.locator(f"tr#saved_vault_filter_{saved_filter_id}")).to_be_visible(timeout=8000)

            print("[Vault Test] Clearing all active filters...")
            vault_page.open_tops()
            vault_page.clear_all_filters()
            attach_screenshot(page, "05_filters_cleared")

            print(f"[Vault Test] Reusing/applying saved filter ID {saved_filter_id} ('{saved_filter_title}')...")
            vault_page.apply_saved_filter(saved_filter_id, filter_title=saved_filter_title)
            attach_screenshot(page, "06_vault_saved_filter_reused")

            # Verify that both filters are restored
            filter_badge = page.locator("li[data-step='1'] a.dropdown-toggle, li.filter-red a.dropdown-toggle, a.dropdown-toggle:has-text('Filters:')").first
            expect(filter_badge).to_be_visible(timeout=5000)
            print(f"[Vault Test] Active filter badge after reuse: {filter_badge.inner_text()}")
            expect(filter_badge).to_contain_text("2")

            # -------------------------------------------------------------
            # Phase 6: Switch Analysis View Types (Raw, Compare, Unique, Tops)
            # -------------------------------------------------------------
            print("[Vault Test] Switching view to Raw Events (/vault)...")
            vault_page.switch_view("raw")
            attach_screenshot(page, "07_vault_view_raw")
            assert "/vault" in page.url and "tops" not in page.url

            print("[Vault Test] Switching view to Comparative Analysis (/vault/comparative)...")
            vault_page.switch_view("compare")
            attach_screenshot(page, "08_vault_view_compare")
            assert "comparative" in page.url

            print("[Vault Test] Switching view to Unique Cardinality (/vault/cardinality)...")
            vault_page.switch_view("unique")
            attach_screenshot(page, "09_vault_view_unique")
            assert "cardinality" in page.url

            print("[Vault Test] Switching view back to Tops (/vault/tops)...")
            vault_page.switch_view("tops")
            attach_screenshot(page, "10_vault_view_tops")
            assert "tops" in page.url

        finally:
            print("\n[Vault Test] Starting clean teardown...")
            # 1. Delete saved filter if created
            if saved_filter_id:
                try:
                    vault_page.delete_saved_filter(saved_filter_id)
                    print(f"[Vault Test] Deleted saved filter ID {saved_filter_id}")
                except Exception as e:
                    print(f"[Vault Test] Warning: Failed to delete saved filter {saved_filter_id}: {e}")

            # 2. Clear any active session filters
            try:
                vault_page.clear_all_filters()
            except Exception:
                pass

            # 3. Delete sensor from tree if not in baseline mode
            if not is_baseline_mode:
                try:
                    sensors_page.open_tree()
                    if sensors_page.is_sensor_present(sensor_name):
                        sensors_page.delete_sensor(sensor_name)
                        print(f"[Vault Test] Deleted sensor '{sensor_name}' from tree")
                except Exception as e:
                    print(f"[Vault Test] Warning: Failed to delete sensor '{sensor_name}': {e}")

                # 4. Stop mock sensor process
                try:
                    ssh_client.stop_mock_sensor(mock_sensor_name)
                    print(f"[Vault Test] Stopped mock sensor '{mock_sensor_name}'")
                except Exception as e:
                    print(f"[Vault Test] Warning: Failed to stop mock sensor: {e}")
            else:
                print(f"[Vault Test] Baseline mode active: preserving sensor '{sensor_name}' and sandbox '{mock_sensor_name}'.")
