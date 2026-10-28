import time
import pytest
from playwright.sync_api import Page, expect

from config.settings import settings
from core.pages.login_page import LoginPage
from core.pages.sensors_page import SensorsPage
from core.pages.monitor_page import MonitorPage
from core.ssh_client import SSHClient


@pytest.fixture
def authenticated_monitor_page(page: Page, base_url: str) -> MonitorPage:
    """Logs into the Web UI and navigates to the Monitor module (/monitor)."""
    login_page = LoginPage(page, base_url)
    login_page.open()
    login_page.login(
        username=settings.web_user,
        password=settings.web_password,
    )
    page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

    monitor_page = MonitorPage(page, base_url)
    monitor_page.open_monitor()
    return monitor_page


@pytest.mark.web
class TestMonitor:
    """End-to-End suite verifying the Monitor module (/monitor):
    - Confirms baseline monitor sensor (SNMP / HTTP) in tree and verifies Druid rb_monitor ingestion.
    - Confirms monitor dashboard visibility in /monitor.
    - Tests active filtering by Sensor Name and Monitor dimension (e.g. cpu).
    - Saves the filter, verifies presence in /saved/monitor_filters, clears active filters, reuses/applies saved filter.
    - Tests switching analysis and infrastructure views: Hardware, Historicals, Kafka, Tops.
    - Tests switching chart types (Area, Line, Bars, Stacked).
    - Cleans up saved filter and active session filters.
    """

    def test_monitor_lifecycle_and_analysis(
        self,
        authenticated_monitor_page: MonitorPage,
        page: Page,
        base_url: str,
        ssh_client: SSHClient,
        require_redborder_sensors,
        attach_screenshot,
    ):
        monitor_page = authenticated_monitor_page
        sensors_page = SensorsPage(page, base_url)

        ts = int(time.time())
        saved_filter_title = f"Filter-Monitor-{ts}"
        saved_filter_id = None
        sensor_ip = "10.10.10.4"

        # Check if baseline testbed sensor already exists
        sensors_page.open_tree()
        sensors_page.expand_all_tree()
        if sensors_page.is_sensor_present("rb-snmp-test"):
            print("[Monitor Test] Detected baseline testbed sensor 'rb-snmp-test'. Reusing.")
            sensor_name = "rb-snmp-test"
            is_baseline_sensor = True
        else:
            print("[Monitor Test] Creating standalone SNMP sensor...")
            sensor_name = f"rb-snmp-{ts}"
            is_baseline_sensor = False
            sensors_page.create_snmp_sensor(name=sensor_name, ip=sensor_ip, community="public")
            sensors_page.ensure_sensor_in_tree(sensor_name)

        mock_sensor_name = "rb-snmp"

        try:
            # -------------------------------------------------------------
            # Pre-check: Ingestion into Druid rb_monitor
            # -------------------------------------------------------------
            print("[Monitor Test] Checking mock SNMP sensor process...")
            mock_running = ssh_client.is_mock_sensor_running(mock_sensor_name)
            if not mock_running:
                print(f"[Monitor Test] Starting mock SNMP sensor '{mock_sensor_name}'...")
                ssh_client.start_mock_sensor(
                    name=mock_sensor_name,
                    ip=sensor_ip,
                    agent_type="snmp",
                )

            # Check if monitor records exist in Druid rb_monitor
            total_monitor_records = ssh_client.query_druid_monitor_count()
            print(f"[Monitor Test] Total rb_monitor records in Druid: {total_monitor_records}")
            assert total_monitor_records > 0, "No monitor records found in Druid rb_monitor database"

            # Use active tree sensor to ensure it exists in Web UI search dropdown
            filter_sensor_name = sensor_name
            filter_monitor = "cpu"

            # Dynamically query Druid for the active monitor dimension across partitioned tables
            tables = ssh_client.get_druid_tables("rb_monitor")
            for tbl in tables:
                data = ssh_client.execute_druid_sql(
                    f'SELECT monitor, COUNT(*) as cnt '
                    f'FROM "{tbl}" '
                    f'WHERE monitor IS NOT NULL '
                    f'GROUP BY 1 '
                    f'ORDER BY cnt DESC '
                    f'LIMIT 1'
                )
                if data and len(data) > 0 and data[0].get("monitor"):
                    filter_monitor = data[0]["monitor"]
                    break

            print(f"[Monitor Test] Active filter parameters: sensor='{filter_sensor_name}', monitor='{filter_monitor}'")

            # -------------------------------------------------------------
            # Phase 1: Monitor Overview (/monitor)
            # -------------------------------------------------------------
            print("[Monitor Test] Navigating to /monitor and verifying monitor dashboard...")
            monitor_page.open_monitor()
            attach_screenshot(page, "01_monitor_overview")
            expect(monitor_page.monitor_article).to_be_visible(timeout=10000)
            expect(monitor_page.tabs_container).to_be_visible(timeout=10000)

            # -------------------------------------------------------------
            # Phase 2: Active Filtering by Sensor Name & Monitor
            # -------------------------------------------------------------
            print(f"[Monitor Test] Applying active filter: sensor_name={filter_sensor_name}...")
            monitor_page.apply_filter(dimension="sensor_name", value=filter_sensor_name)
            attach_screenshot(page, "02_monitor_filter_sensor_name")

            print(f"[Monitor Test] Applying active filter: monitor={filter_monitor}...")
            monitor_page.apply_filter(dimension="monitor", value=filter_monitor)
            attach_screenshot(page, "03_monitor_filter_both")

            # Verify active filter badge contains '2'
            active_badge = page.locator("li[data-step='1'] a.dropdown-toggle, li.filter-red a.dropdown-toggle, a.dropdown-toggle:has-text('Filters:')").first
            expect(active_badge).to_be_visible(timeout=5000)
            expect(active_badge).to_contain_text("2")

            # -------------------------------------------------------------
            # Phase 3: Tab Switching
            # -------------------------------------------------------------
            print("[Monitor Test] Switching tab to 'cpu'...")
            monitor_page.select_tab("cpu")
            attach_screenshot(page, "04_monitor_cpu_tab")

            # -------------------------------------------------------------
            # Phase 4: Saved Filter Lifecycle (Save, List, Clear, Reuse)
            # -------------------------------------------------------------
            print(f"[Monitor Test] Saving active filter as '{saved_filter_title}'...")
            saved_filter_id = monitor_page.save_current_filter(saved_filter_title, public=True, expected_count=2)
            assert saved_filter_id is not None, "Failed to extract saved monitor filter ID"
            print(f"[Monitor Test] Saved filter successfully created with ID: {saved_filter_id}")

            print("[Monitor Test] Verifying saved filter in /saved/monitor_filters...")
            monitor_page.open_saved_filters_page()
            attach_screenshot(page, "05_saved_filters_table")
            expect(page.locator(f"tr#saved_monitor_filter_{saved_filter_id}")).to_be_visible(timeout=8000)

            print("[Monitor Test] Clearing all active filters...")
            monitor_page.open_monitor()
            monitor_page.clear_all_filters()
            attach_screenshot(page, "06_filters_cleared")

            print(f"[Monitor Test] Reusing/applying saved filter ID {saved_filter_id} ('{saved_filter_title}')...")
            monitor_page.apply_saved_filter(saved_filter_id, filter_title=saved_filter_title)
            attach_screenshot(page, "07_monitor_saved_filter_reused")

            # Verify that both filters are restored
            filter_badge = page.locator("li[data-step='1'] a.dropdown-toggle, li.filter-red a.dropdown-toggle, a.dropdown-toggle:has-text('Filters:')").first
            expect(filter_badge).to_be_visible(timeout=5000)
            print(f"[Monitor Test] Active filter badge after reuse: {filter_badge.inner_text()}")
            expect(filter_badge).to_contain_text("2")

            # -------------------------------------------------------------
            # Phase 5: Switch Subviews (Hardware, Historicals, Kafka, Tops)
            # -------------------------------------------------------------
            print("[Monitor Test] Switching view to Hardware (/monitor/hardware)...")
            monitor_page.switch_view("hardware")
            attach_screenshot(page, "08_monitor_view_hardware")
            assert "hardware" in page.url

            print("[Monitor Test] Switching view to Historicals (/monitor/historicals)...")
            monitor_page.switch_view("historicals")
            attach_screenshot(page, "09_monitor_view_historicals")
            assert "historicals" in page.url

            print("[Monitor Test] Switching view to Kafka (/monitor/kafka)...")
            monitor_page.switch_view("kafka")
            attach_screenshot(page, "10_monitor_view_kafka")
            assert "kafka" in page.url

            print("[Monitor Test] Switching view back to Tops (/monitor)...")
            monitor_page.switch_view("tops")
            attach_screenshot(page, "11_monitor_view_tops")
            assert "/monitor" in page.url

            # -------------------------------------------------------------
            # Phase 6: Switch Chart Types
            # -------------------------------------------------------------
            chart_types = ["area", "line", "bars", "stacked"]
            for ct in chart_types:
                print(f"[Monitor Test] Switching chart type to '{ct}'...")
                monitor_page.set_chart_type(ct)
                active_ct = monitor_page.get_active_chart_type()
                print(f"[Monitor Test] Active chart type: {active_ct}")
                attach_screenshot(page, f"12_chart_type_{ct}")
                assert ct.lower() in active_ct.lower()

        finally:
            print("[Monitor Test Cleanup] Initiating teardown...")
            # 1. Delete saved filter if created
            if saved_filter_id:
                try:
                    monitor_page.delete_saved_filter(saved_filter_id)
                    print(f"[Monitor Test Cleanup] Saved filter {saved_filter_id} deleted.")
                except Exception as e:
                    print(f"[Monitor Test Cleanup Warning] Failed to delete saved filter {saved_filter_id}: {e}")

            # 2. Clear any active session filters
            try:
                monitor_page.open_monitor()
                monitor_page.clear_all_filters()
            except Exception as e:
                print(f"[Monitor Test Cleanup Warning] Failed to clear session filters: {e}")

            # 3. Clean up sensor if standalone
            if not is_baseline_sensor:
                try:
                    sensors_page.open_tree()
                    sensors_page.delete_sensor(sensor_name)
                    print(f"[Monitor Test Cleanup] Standalone sensor '{sensor_name}' deleted.")
                except Exception as e:
                    print(f"[Monitor Test Cleanup Warning] Failed to delete sensor '{sensor_name}': {e}")
