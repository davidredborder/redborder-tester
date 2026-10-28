import re
import time
import pytest
from playwright.sync_api import Page, expect

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
class TestSensorsWeb:
    def test_sensors_tree_loads(self, sensors_page: SensorsPage, attach_screenshot):
        """Verifies that the sensors tree page loads with title and table structure."""
        page = sensors_page.page
        expect(page).to_have_title(re.compile(r"sensors.*redborder", re.IGNORECASE))
        expect(sensors_page.tree_table).to_be_visible(timeout=10000)

        # Verify table header columns
        header_text = page.locator("table#tree thead").inner_text()
        assert "Name" in header_text
        assert "Status" in header_text
        attach_screenshot(page, title="Sensors Tree View")

    def test_sensor_tree_rows_present(self, sensors_page: SensorsPage, attach_screenshot):
        """Verifies that registered sensor nodes are displayed in the tree table."""
        expect(sensors_page.tree_table).to_be_visible()

        rows = sensors_page.tree_rows
        seed_created = False
        seed_name = f"seed-{int(time.time())}"

        # If freshly installed with 0 sensors, seed a temporary sensor to verify tree rendering
        if rows.count() == 0:
            print(f"\n[Sensors Web] Empty tree detected on fresh install. Creating seed sensor '{seed_name}'...")
            sensors_page.create_vault_sensor(name=seed_name, ip="10.10.10.99")
            seed_created = True
            rows = sensors_page.tree_rows

        try:
            # At least one sensor row exists and is visible
            expect(rows.first).to_be_visible(timeout=10000)

            # Check content of the first sensor row (contains valid status and details)
            first_row_text = rows.first.inner_text()
            assert any(k in first_row_text for k in ["OK", "Warning", "Error", "router", "10.", "seed"]), (
                f"Unexpected sensor row content: {first_row_text}"
            )
            attach_screenshot(sensors_page.page, title="Sensors Tree Rows Populated")
        finally:
            if seed_created:
                print(f"[Sensors Web] Cleaning up seed sensor '{seed_name}'...")
                sensors_page.open_tree()
                sensors_page.page.wait_for_load_state("domcontentloaded")
                if sensors_page.is_sensor_present(seed_name):
                    sensors_page.delete_sensor(seed_name)

    @pytest.mark.parametrize("sensor_type,open_method,expected_title", [
        ("Flow", "open_new_flow_sensor_modal", "Flow"),
        ("Vault", "open_new_vault_sensor_modal", "Vault"),
        ("SNMP", "open_new_snmp_sensor_modal", "SNMP"),
    ])
    def test_add_sensor_modal_opens(
        self,
        sensors_page: SensorsPage,
        sensor_type: str,
        open_method: str,
        expected_title: str,
        attach_screenshot,
    ):
        """Verifies clicking 'Add Sensor' -> type opens the creation modal."""
        getattr(sensors_page, open_method)()

        # Verify modal is visible with expected title
        expect(sensors_page.new_sensor_modal).to_be_visible()
        expect(sensors_page.modal_title).to_contain_text(expected_title, ignore_case=True)
        attach_screenshot(sensors_page.page, title=f"Add Sensor Modal ({sensor_type})")

        # Close the modal
        sensors_page.modal_close_button.click()
        expect(sensors_page.new_sensor_modal).not_to_be_visible(timeout=5000)

    @pytest.mark.parametrize("subview", ["flow", "ips", "snmp"])
    def test_sensor_module_tabs_render(self, sensors_page: SensorsPage, subview: str, attach_screenshot):
        """Verifies navigating to sensor module subviews (flow, ips, snmp) loads without error."""
        page = sensors_page.page
        method_map = {
            "flow": sensors_page.open_flow,
            "ips": sensors_page.open_ips,
            "snmp": sensors_page.open_snmp,
        }
        method_map[subview]()
        page.wait_for_load_state("domcontentloaded")

        assert f"/sensors/{subview}" in page.url
        # Verify the sensor table on the subview page is visible
        expect(sensors_page.tree_table).to_be_visible(timeout=10000)
        attach_screenshot(page, title=f"Sensors Module Tab - {subview.upper()}")
