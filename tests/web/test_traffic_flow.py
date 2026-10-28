import time
import pytest
from playwright.sync_api import Page, expect

from config.settings import settings
from core.pages.login_page import LoginPage
from core.pages.sensors_page import SensorsPage
from core.pages.traffic_page import TrafficPage
from core.ssh_client import SSHClient


@pytest.fixture
def authenticated_traffic_page(page: Page, base_url: str) -> TrafficPage:
    """Logs into the Web UI and navigates to the Traffic module (/flow)."""
    login_page = LoginPage(page, base_url)
    login_page.open()
    login_page.login(
        username=settings.web_user,
        password=settings.web_password,
    )
    page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

    traffic_page = TrafficPage(page, base_url)
    traffic_page.open_tops()
    return traffic_page


@pytest.mark.web
class TestTrafficFlow:
    """End-to-End suite verifying the Traffic module (/flow):
    - Ingests mock flow telemetry via redborder-sensors and verifies Druid rb_flow.
    - Creates flow sensor in tree and confirms data visibility in /flow.
    - Tests active filtering by Sensor Name and LAN IP.
    - Saves the filter, clears active filters, reuses/applies saved filter (testing sharing).
    - Tests switching analysis views: Raw (/flow), Compare (/flow/comparative), Unique (/flow/cardinality), and Tops (/flow/tops).
    - Tests switching metric aggregation units: bps, pkts (packets), pps (packets/sec), and bytes.
    - Cleans up sensor, filters, and mock sensor processes.
    """

    def test_traffic_flow_lifecycle_and_analysis(
        self,
        authenticated_traffic_page: TrafficPage,
        page: Page,
        base_url: str,
        ssh_client: SSHClient,
        require_redborder_sensors,
        attach_screenshot,
    ):
        traffic_page = authenticated_traffic_page
        sensors_page = SensorsPage(page, base_url)

        ts = int(time.time())
        short_id = str(ts)[-5:]
        saved_filter_title = f"Filter-Traffic-{ts}"
        saved_filter_id = None
        sensor_ip = "10.10.10.2"
        target_gw = "10.10.10.1"
        lan_ip = "10.10.10.2"

        # Check if baseline testbed sensor already exists
        sensors_page.open_tree()
        sensors_page.expand_all_tree()
        if sensors_page.is_sensor_present("rb-flow-test"):
            sensor_name = "rb-flow-test"
            mock_sensor_name = "rb-flow"
            is_baseline_mode = True
        else:
            sensor_name = f"flow-traffic-{ts}"
            mock_sensor_name = f"fl{short_id}"
            is_baseline_mode = False

        if not is_baseline_mode:
            # Pre-cleanup
            ssh_client.stop_mock_sensor(mock_sensor_name)

        try:
            if not is_baseline_mode:
                # -------------------------------------------------------------
                # Phase 1: Create Flow Sensor in Tree & Sync Manager
                # -------------------------------------------------------------
                print(f"\n[Traffic Test] Creating Flow sensor '{sensor_name}' in Web UI tree...")
                sensors_page.open_tree()
                sensors_page.create_flow_sensor(
                    name=sensor_name,
                    ip=sensor_ip,
                )
                assert sensors_page.is_sensor_present(sensor_name), f"Sensor '{sensor_name}' was not created in tree"

                # -------------------------------------------------------------
                # Phase 2: Start Mock Telemetry Agent & Verify Ingestion
                # -------------------------------------------------------------
                print(f"[Traffic Test] Starting mock flow sensor '{mock_sensor_name}'...")
                res_start = ssh_client.start_mock_sensor(
                    name=mock_sensor_name,
                    ip=sensor_ip,
                    target_ip=target_gw,
                    agent_type="telemetry-agent",
                )
                assert res_start.ok, f"Failed to start mock flow sensor: {res_start.stderr}"
            else:
                print(f"[Traffic Test] Baseline mode active: reusing sensor '{sensor_name}' and running sandbox '{mock_sensor_name}'.")
                if not ssh_client.is_mock_sensor_running(mock_sensor_name):
                    ssh_client.start_mock_sensor(name=mock_sensor_name, ip=sensor_ip, target_ip=target_gw, agent_type="telemetry-agent")

            # Check if router flows exist for rich filter testing
            total_flows = ssh_client.query_druid_flow_count()
            print(f"[Traffic Test] Total rb_flow records in Druid: {total_flows}")
            assert total_flows > 0, "No flow events found in Druid rb_flow database"

            # Use the active tree sensor to ensure it exists in the Web UI search dropdown
            filter_sensor_name = sensor_name
            filter_lan_ip = sensor_ip

            # Dynamically query Druid for the active LAN IP across partitioned tables
            tables = ssh_client.get_druid_tables("rb_flow")
            for tbl in tables:
                data = ssh_client.execute_druid_sql(
                    f'SELECT lan_ip, COUNT(*) as cnt '
                    f'FROM "{tbl}" '
                    f'WHERE lan_ip IS NOT NULL '
                    f'GROUP BY 1 '
                    f'ORDER BY cnt DESC '
                    f'LIMIT 1'
                )
                if data and len(data) > 0 and data[0].get("lan_ip"):
                    filter_lan_ip = data[0]["lan_ip"]
                    break

            print(f"[Traffic Test] Active filter parameters: sensor='{filter_sensor_name}', lan_ip='{filter_lan_ip}'")

            # -------------------------------------------------------------
            # Phase 3: Traffic Overview (Tops View)
            # -------------------------------------------------------------
            print("[Traffic Test] Navigating to /flow/tops and verifying traffic dashboard...")
            traffic_page.open_tops()
            attach_screenshot(page, "01_flow_traffic_overview")
            expect(traffic_page.tops_table).to_be_visible(timeout=10000)

            # -------------------------------------------------------------
            # Phase 4: Filtering by Sensor Name & LAN IP
            # -------------------------------------------------------------
            print(f"[Traffic Test] Applying active filter: sensor_name={filter_sensor_name}...")
            traffic_page.apply_filter(dimension="sensor_name", value=filter_sensor_name)
            attach_screenshot(page, "02_flow_filter_sensor_name")

            print(f"[Traffic Test] Applying active filter: lan_ip={filter_lan_ip}...")
            traffic_page.apply_filter(dimension="lan_ip", value=filter_lan_ip)

            # Verify that both active filters are registered in the toolbar badge
            active_badge = page.locator("li[data-step='1'] a.dropdown-toggle, li.filter-red a.dropdown-toggle, a.dropdown-toggle:has-text('Filters:')").first
            expect(active_badge).to_contain_text("2", timeout=5000)

            # Switch to LAN IP tab to view filtered statistics by LAN IP
            print("[Traffic Test] Switching to 'LAN IP' tab...")
            traffic_page.select_tab("lan_ip")
            attach_screenshot(page, "03_flow_filter_lan_ip_tab")

            # -------------------------------------------------------------
            # Phase 5: Save Filter, Clear Active, & Reuse/Load Saved Filter
            # -------------------------------------------------------------
            print(f"[Traffic Test] Saving filter as '{saved_filter_title}' (public sharing enabled) via Web UI...")
            saved_filter_id = traffic_page.save_current_filter(
                title=saved_filter_title,
                public=True,
                items=[
                    {"column": "sensor_name", "operator": "is", "value": filter_sensor_name},
                    {"column": "lan_ip", "operator": "is", "value": filter_lan_ip},
                ],
            )
            assert saved_filter_id is not None, "Failed to save filter"
            print(f"[Traffic Test] Saved filter created with ID: {saved_filter_id}")

            print("[Traffic Test] Verifying saved filter in /saved/flow_filters...")
            traffic_page.open_saved_filters_page()
            attach_screenshot(page, "04_saved_filters_table")
            expect(page.locator(f"tr#saved_traffic_filter_{saved_filter_id}")).to_be_visible(timeout=8000)

            print("[Traffic Test] Clearing all active filters...")
            traffic_page.open_tops()
            traffic_page.clear_all_filters()
            attach_screenshot(page, "05_filters_cleared")

            print(f"[Traffic Test] Reusing/applying saved filter ID {saved_filter_id} ('{saved_filter_title}')...")
            traffic_page.apply_saved_filter(saved_filter_id, filter_title=saved_filter_title)
            attach_screenshot(page, "06_flow_saved_filter_reused")


            # Verify that both filters are restored
            filter_badge = page.locator("li[data-step='1'] a.dropdown-toggle, li.filter-red a.dropdown-toggle, a.dropdown-toggle:has-text('Filters:')").first
            expect(filter_badge).to_be_visible(timeout=5000)
            print(f"[Traffic Test] Active filter badge after reuse: {filter_badge.inner_text()}")
            expect(filter_badge).to_contain_text("2")


            # -------------------------------------------------------------
            # Phase 6: Switch Analysis View Types (Raw, Compare, Unique, Tops)
            # -------------------------------------------------------------
            print("[Traffic Test] Switching view to Raw Events (/flow)...")
            traffic_page.switch_view("raw")
            attach_screenshot(page, "07_flow_view_raw")
            assert "/flow" in page.url and "tops" not in page.url

            print("[Traffic Test] Switching view to Comparative Analysis (/flow/comparative)...")
            traffic_page.switch_view("compare")
            attach_screenshot(page, "08_flow_view_compare")
            assert "comparative" in page.url

            print("[Traffic Test] Switching view to Unique Cardinality (/flow/cardinality)...")
            traffic_page.switch_view("unique")
            attach_screenshot(page, "09_flow_view_unique")
            assert "cardinality" in page.url

            print("[Traffic Test] Switching view back to Tops (/flow/tops)...")
            traffic_page.switch_view("tops")
            attach_screenshot(page, "10_flow_view_tops")
            assert "tops" in page.url

            # -------------------------------------------------------------
            # Phase 7: Switch Metric Aggregation Units (bps, pkts, pps, bytes)
            # -------------------------------------------------------------
            print("[Traffic Test] Setting metric aggregation unit to bps...")
            traffic_page.set_metric("bps")
            expect(page.locator("li#aggregations > a.dropdown-toggle")).to_contain_text("bps")
            attach_screenshot(page, "11_metric_bps")

            print("[Traffic Test] Setting metric aggregation unit to pkts (packets)...")
            traffic_page.set_metric("pkts")
            expect(page.locator("li#aggregations > a.dropdown-toggle")).to_contain_text("packets")
            attach_screenshot(page, "12_metric_packets")

            print("[Traffic Test] Setting metric aggregation unit to pps (packets/sec)...")
            traffic_page.set_metric("pps")
            expect(page.locator("li#aggregations > a.dropdown-toggle")).to_contain_text("packets/s")
            attach_screenshot(page, "13_metric_pps")

            print("[Traffic Test] Setting metric aggregation unit back to bytes...")
            traffic_page.set_metric("bytes")
            expect(page.locator("li#aggregations > a.dropdown-toggle")).to_contain_text("bytes")
            attach_screenshot(page, "14_metric_bytes")

        finally:
            print("\n[Traffic Test] Starting clean teardown...")
            # 1. Delete saved filter if created
            if saved_filter_id:
                try:
                    traffic_page.delete_saved_filter(saved_filter_id)
                    print(f"[Traffic Test] Deleted saved filter ID {saved_filter_id}")
                except Exception as e:
                    print(f"[Traffic Test] Warning: Failed to delete saved filter {saved_filter_id}: {e}")

            # 2. Clear any active session filters
            try:
                traffic_page.clear_all_filters()
            except Exception:
                pass

            # 3. Delete sensor from tree
            if not is_baseline_mode:
                try:
                    sensors_page.open_tree()
                    if sensors_page.is_sensor_present(sensor_name):
                        sensors_page.delete_sensor(sensor_name)
                        print(f"[Traffic Test] Deleted sensor '{sensor_name}' from tree")
                except Exception as e:
                    print(f"[Traffic Test] Warning: Failed to delete sensor '{sensor_name}': {e}")

                # 4. Stop mock sensor process
                try:
                    ssh_client.stop_mock_sensor(mock_sensor_name)
                    print(f"[Traffic Test] Stopped mock sensor '{mock_sensor_name}'")
                except Exception as e:
                    print(f"[Traffic Test] Warning: Failed to stop mock sensor: {e}")
            else:
                print(f"[Traffic Test] Baseline mode active: preserving sensor '{sensor_name}' and sandbox '{mock_sensor_name}'.")
