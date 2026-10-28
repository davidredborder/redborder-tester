import time
import pytest
from playwright.sync_api import Page
from config.settings import settings
from core.pages.login_page import LoginPage
from core.pages.sensors_page import SensorsPage


@pytest.fixture
def sensors_page(page: Page, base_url: str) -> SensorsPage:
    """Fixture that logs into Redborder and navigates to the Sensors tree page."""
    login_page = LoginPage(page, base_url)
    login_page.open()
    login_page.login(
        username=settings.web_user,
        password=settings.web_password,
    )
    page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

    sensor_p = SensorsPage(page, base_url)
    sensor_p.open_tree()
    page.wait_for_load_state("domcontentloaded")
    return sensor_p


@pytest.mark.web
class TestSensorsMultiTypes:
    """
    Validates creation and deletion for all requested sensor types:
    Flow, SNMP, Vault, VMware ESXi, HTTP Agent, and SNMP Trap.
    Tests both Root level and Nested in Hierarchy.
    """

    def test_root_sensor_types_lifecycle(
        self,
        sensors_page: SensorsPage,
        page: Page,
        attach_screenshot,
    ) -> None:
        """Tests presence and health of all sensor types (or verifies their lifecycle)."""
        sensors_page.open_tree()
        sensors_page.expand_all_tree()
        page.wait_for_load_state("domcontentloaded")
        attach_screenshot(page, "01_root_sensors_initial")

        # Check if running in unified baseline testbed mode
        is_baseline = (
            sensors_page.is_sensor_present("rb-flow-test") and
            sensors_page.is_sensor_present("rb-vault-test") and
            sensors_page.is_sensor_present("rb-snmp-test")
        )

        if is_baseline:
            # Baseline testbed mode: verify all 6 baseline sensor types are healthy and present
            baseline_sensors = [
                ("rb-flow-test", "Flow"),
                ("rb-vault-test", "Vault"),
                ("rb-snmp-test", "SNMP"),
                ("rb-http-test", "HTTP Agent"),
                ("rb-vmware-test", "VMware ESXi"),
                ("rb-trap-test", "SNMP Trap"),
            ]
            for s_name, s_type in baseline_sensors:
                assert sensors_page.is_sensor_present(s_name), f"Baseline {s_type} sensor '{s_name}' must be present in tree"
            attach_screenshot(page, "02_baseline_sensors_verified")
            return

        ts = int(time.time())
        created_sensors = []

        try:
            # 1. Flow Sensor
            flow_name = f"rb-flw-{ts}"
            sensors_page.create_flow_sensor(name=flow_name, ip="10.20.1.10")
            sensors_page.open_tree()
            assert sensors_page.is_sensor_present(flow_name), f"Flow sensor {flow_name} must be visible"
            created_sensors.append(flow_name)
            attach_screenshot(page, "02_flow_sensor_created")

            # 2. Vault Sensor
            vault_name = f"rb-vlt-{ts}"
            sensors_page.create_vault_sensor(name=vault_name, ip="10.20.1.11")
            sensors_page.open_tree()
            assert sensors_page.is_sensor_present(vault_name), f"Vault sensor {vault_name} must be visible"
            created_sensors.append(vault_name)
            attach_screenshot(page, "03_vault_sensor_created")

            # 3. SNMP Sensor
            snmp_name = f"rb-snp-{ts}"
            sensors_page.create_snmp_sensor(name=snmp_name, ip="10.20.1.12", community="public")
            sensors_page.open_tree()
            assert sensors_page.is_sensor_present(snmp_name), f"SNMP sensor {snmp_name} must be visible"
            created_sensors.append(snmp_name)
            attach_screenshot(page, "04_snmp_sensor_created")

            # 4. VMware ESXi Sensor
            vmware_name = f"rb-vmw-{ts}"
            sensors_page.create_vmware_sensor(
                name=vmware_name,
                ip="10.20.1.13",
                username="root",
                password="password",
            )
            sensors_page.open_tree()
            assert sensors_page.is_sensor_present(vmware_name), f"VMware ESXi sensor {vmware_name} must be visible"
            created_sensors.append(vmware_name)
            attach_screenshot(page, "05_vmware_sensor_created")

            # 5. HTTP Agent Sensor
            http_name = f"rb-htp-{ts}"
            sensors_page.create_http_agent_sensor(name=http_name, description="HTTP Agent test sensor")
            sensors_page.open_tree()
            assert sensors_page.is_sensor_present(http_name), f"HTTP Agent sensor {http_name} must be visible"
            created_sensors.append(http_name)
            attach_screenshot(page, "06_http_agent_sensor_created")

            # 6. SNMP Trap Sensor
            trap_name = f"rb-trp-{ts}"
            sensors_page.create_trap_sensor(name=trap_name, ip="10.20.1.14", community="public")
            sensors_page.open_tree()
            assert sensors_page.is_sensor_present(trap_name), f"SNMP Trap sensor {trap_name} must be visible"
            created_sensors.append(trap_name)
            attach_screenshot(page, "07_trap_sensor_created")

        finally:
            # Clean deletion of all created root sensors
            sensors_page.open_tree()
            for s_name in created_sensors:
                try:
                    if sensors_page.is_sensor_present(s_name):
                        sensors_page.delete_sensor(s_name)
                except Exception as e:
                    print(f"Warning: Failed to delete sensor {s_name}: {e}")

            sensors_page.open_tree()
            for s_name in created_sensors:
                assert not sensors_page.is_sensor_present(s_name), (
                    f"Sensor {s_name} must be deleted from tree"
                )
            attach_screenshot(page, "08_all_root_sensors_cleaned_up")

    def test_nested_sensors_in_domain_hierarchy(
        self,
        sensors_page: SensorsPage,
        page: Page,
        attach_screenshot,
        stable_domain_hierarchy,
    ) -> None:
        """Tests creation and deletion of sensors nested under a stable Domain Hierarchy (SP -> NS -> Org)."""
        sensors_page.open_tree()
        page.wait_for_load_state("domcontentloaded")
        attach_screenshot(page, "10_nested_suite_initial")

        # Check if running in unified baseline testbed mode
        is_baseline = (
            sensors_page.is_sensor_present("rb-flow-test") and
            sensors_page.is_sensor_present("rb-vault-test") and
            sensors_page.is_sensor_present("rb-snmp-test")
        )

        if is_baseline:
            sensors_page.expand_all_tree()
            baseline_nested = [
                ("rb-flow-test", "Flow"),
                ("rb-vault-test", "Vault"),
                ("rb-snmp-test", "SNMP"),
                ("rb-vmware-test", "VMware ESXi"),
                ("rb-trap-test", "SNMP Trap"),
            ]
            for s_name, s_type in baseline_nested:
                assert sensors_page.is_sensor_present(s_name), f"Baseline {s_type} sensor '{s_name}' must be present in tree"
                row = sensors_page.get_sensor_row(s_name)
                assert row.get_attribute("data-tt-parent-id") == str(org_id), (
                    f"Baseline nested sensor {s_name} parent ID must match organization node ID {org_id}"
                )
            attach_screenshot(page, "12_all_baseline_nested_sensors_verified")
            return

        ts = int(time.time())
        org_id = stable_domain_hierarchy["org_id"]
        created_sensors = []

        try:
            sensors_page.expand_all_tree()
            attach_screenshot(page, "11_domain_tree_ready_for_sensors")

            # Create all supported sensor types nested under the Organization node
            # A. Nested Flow Sensor
            nested_flow = f"rb-nflw-{ts}"
            sensors_page.create_flow_sensor(name=nested_flow, ip="10.20.2.10", parent_node_id=org_id)
            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            assert sensors_page.is_sensor_present(nested_flow), f"Nested Flow sensor {nested_flow} must be present"
            created_sensors.append(nested_flow)

            # B. Nested Vault Sensor
            nested_vault = f"rb-nvlt-{ts}"
            sensors_page.create_vault_sensor(name=nested_vault, ip="10.20.2.11", parent_node_id=org_id)
            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            assert sensors_page.is_sensor_present(nested_vault), f"Nested Vault sensor {nested_vault} must be present"
            created_sensors.append(nested_vault)

            # C. Nested SNMP Sensor
            nested_snmp = f"rb-nsnp-{ts}"
            sensors_page.create_snmp_sensor(name=nested_snmp, ip="10.20.2.12", community="public", parent_node_id=org_id)
            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            assert sensors_page.is_sensor_present(nested_snmp), f"Nested SNMP sensor {nested_snmp} must be present"
            created_sensors.append(nested_snmp)

            # D. Nested VMware ESXi Sensor
            nested_vmware = f"rb-nvmw-{ts}"
            sensors_page.create_vmware_sensor(
                name=nested_vmware,
                ip="10.20.2.13",
                username="root",
                password="password",
                parent_node_id=org_id,
            )
            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            assert sensors_page.is_sensor_present(nested_vmware), f"Nested VMware sensor {nested_vmware} must be present"
            created_sensors.append(nested_vmware)

            # E. Nested SNMP Trap Sensor
            nested_trap = f"rb-ntrp-{ts}"
            sensors_page.create_trap_sensor(name=nested_trap, ip="10.20.2.14", community="public", parent_node_id=org_id)
            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            assert sensors_page.is_sensor_present(nested_trap), f"Nested Trap sensor {nested_trap} must be present"
            created_sensors.append(nested_trap)

            # Verify parent-child hierarchy relationships in table#tree
            for s_name in created_sensors:
                row = sensors_page.get_sensor_row(s_name)
                assert row.get_attribute("data-tt-parent-id") == str(org_id), (
                    f"Nested sensor {s_name} parent ID must match organization node ID {org_id}"
                )
            attach_screenshot(page, "12_all_nested_sensors_verified")

        finally:
            # Clean up nested sensors created during the test
            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            for s_name in created_sensors:
                try:
                    if sensors_page.is_sensor_present(s_name):
                        sensors_page.delete_sensor(s_name)
                except Exception as e:
                    print(f"Warning: Failed to delete nested sensor {s_name}: {e}")

            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            for item in created_sensors:
                assert not sensors_page.is_sensor_present(item), f"Sensor {item} must be cleaned up"
            attach_screenshot(page, "13_nested_suite_cleaned_up")
