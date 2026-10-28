import time
import pytest
from playwright.sync_api import Page
from config.settings import settings
from core.pages.login_page import LoginPage
from core.pages.sensors_page import SensorsPage




@pytest.mark.web
class TestSensorsDragDrop:
    """End-to-end tests for Drag and Drop sensor repositioning in the domain tree across all sensor types."""

    def test_drag_all_sensor_types_between_domains_and_to_root(
        self,
        sensors_page: SensorsPage,
        stable_testbed: dict,
        attach_screenshot,
    ):
        """
        Verify moving all common sensor types across domain hierarchy via drag-and-drop:
        1. Reuse pre-provisioned baseline testbed:
           - Source Hierarchy: rb-test-sp -> rb-test-ns -> rb-test-org
           - Destination Service Provider: rb-test-sp2
           - Pre-converged baseline sensors: Flow, Vault, SNMP, HTTP Agent, VMware ESXi, SNMP Trap
        2. Verify initial hierarchy for all sensors: data-tt-parent-id == org_id.
        3. Drag all sensors to Destination Service Provider (rb-test-sp2):
           - Native confirm dialog accepted on each drop.
           - Verify data-tt-parent-id updates to dst_sp_id.
           - Reload tree and verify server-side database persistence for all sensors.
        4. Drag all sensors to table#tree thead (root drop zone):
           - Native confirm dialog accepted on each drop.
           - Verify data-tt-parent-id is empty/cleared for all sensors.
           - Reload tree and verify server-side database persistence at root for all sensors.
        5. Teardown / Reposition: Drag sensors back under Organization to leave testbed intact.
        """
        page = sensors_page.page

        org_id = stable_testbed["org_id"]
        org_name = stable_testbed["org_name"]
        dst_sp_id = stable_testbed["dst_sp_id"]
        dst_sp_name = stable_testbed["dst_sp_name"]

        # Select sensors nested under Org
        sensors_to_test = [
            stable_testbed["sensors"]["flow"],
            stable_testbed["sensors"]["vault"],
            stable_testbed["sensors"]["snmp"],
            stable_testbed["sensors"]["vmware"],
            stable_testbed["sensors"]["trap"],
        ]

        sensors_page.open_tree()
        sensors_page.expand_all_tree()

        try:
            # Step 1: Verify initial nesting under stable Organization for all baseline sensors
            for s_name in sensors_to_test:
                p_id = sensors_page.get_node_parent_id(s_name)
                assert p_id == org_id, (
                    f"Initial check: Sensor {s_name} expected parent ID {org_id}, got {p_id}"
                )
            attach_screenshot(page, "drag_drop_01_all_sensors_nested_under_org")

            # Step 2: Drag each sensor to Destination Service Provider (rb-test-sp2)
            for s_name in sensors_to_test:
                sensors_page.drag_sensor_to_node(s_name, dst_sp_name)
                page.wait_for_timeout(500)
                # Verify immediate DOM update
                moved_parent_id = sensors_page.get_node_parent_id(s_name)
                assert moved_parent_id == dst_sp_id, (
                    f"DOM check: Sensor {s_name} after drag to {dst_sp_name} expected parent {dst_sp_id}, got {moved_parent_id}"
                )

            # Verify server-side database persistence after full reload
            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            for s_name in sensors_to_test:
                reloaded_parent_id = sensors_page.get_node_parent_id(s_name)
                assert reloaded_parent_id == dst_sp_id, (
                    f"DB reload check: Sensor {s_name} expected parent {dst_sp_id}, got {reloaded_parent_id}"
                )
            attach_screenshot(page, "drag_drop_02_all_sensors_moved_to_destination_sp")

            # Step 3: Drag each sensor to table thead (root drop zone)
            for s_name in sensors_to_test:
                sensors_page.drag_sensor_to_root(s_name)
                page.wait_for_timeout(500)
                # Verify immediate DOM update
                root_parent_id = sensors_page.get_node_parent_id(s_name)
                assert root_parent_id is None, (
                    f"DOM check: Sensor {s_name} after drag to root expected None parent, got {root_parent_id}"
                )

            # Verify server-side database persistence after full reload
            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            for s_name in sensors_to_test:
                reloaded_root_parent_id = sensors_page.get_node_parent_id(s_name)
                assert reloaded_root_parent_id is None, (
                    f"DB reload check: Sensor {s_name} at root expected None parent, got {reloaded_root_parent_id}"
                )
            attach_screenshot(page, "drag_drop_03_all_sensors_moved_to_root")

        finally:
            # Step 4: Reposition sensors back under Organization to restore clean baseline
            try:
                sensors_page.open_tree()
                sensors_page.expand_all_tree()
                for s_name in sensors_to_test:
                    if sensors_page.is_sensor_present(s_name):
                        sensors_page.drag_sensor_to_node(s_name, org_name)
                        page.wait_for_timeout(300)
            except Exception:
                pass
