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
class TestTreeHierarchy:
    """
    Validates end-to-end Domain Hierarchy lifecycle on Redborder Web UI:
    Root -> Service Provider -> Namespace -> Organization -> Clean Teardown
    """

    def test_domain_hierarchy_create_and_delete(
        self,
        sensors_page: SensorsPage,
        page: Page,
        attach_screenshot,
        ssh_client,
    ) -> None:
        sensors_page.open_tree()
        page.wait_for_load_state("domcontentloaded")
        attach_screenshot(page, "01_initial_sensors_tree")

        # Check if the baseline testbed domain hierarchy already exists
        sensors_page.expand_all_tree()
        is_baseline = (
            sensors_page.is_sensor_present("rb-test-sp") and
            sensors_page.is_sensor_present("rb-test-ns") and
            sensors_page.is_sensor_present("rb-test-org")
        )

        if is_baseline:
            # Baseline mode: reuse the pre-converged stable hierarchy
            sp_name = "rb-test-sp"
            ns_name = "rb-test-ns"
            org_name = "rb-test-org"

            sp_row = sensors_page.get_sensor_row(sp_name)
            ns_row = sensors_page.get_sensor_row(ns_name)
            org_row = sensors_page.get_sensor_row(org_name)

            assert sp_row.is_visible(), f"Baseline Service Provider {sp_name} should be visible"
            assert ns_row.is_visible(), f"Baseline Namespace {ns_name} should be visible"
            assert org_row.is_visible(), f"Baseline Organization {org_name} should be visible"

            sp_id = sensors_page.get_node_id(sp_name)
            ns_id = sensors_page.get_node_id(ns_name)
            org_id = sensors_page.get_node_id(org_name)

            assert ns_row.get_attribute("data-tt-parent-id") == str(sp_id), (
                f"Namespace {ns_name} parent ID must be {sp_id}"
            )
            assert org_row.get_attribute("data-tt-parent-id") == str(ns_id), (
                f"Organization {org_name} parent ID must be {ns_id}"
            )
            attach_screenshot(page, "02_baseline_hierarchy_verified")

            # Verify Collapse All behavior on baseline hierarchy
            sensors_page.collapse_all_tree()
            sp_row = sensors_page.get_sensor_row(sp_name)
            ns_row = sensors_page.get_sensor_row(ns_name)
            org_row = sensors_page.get_sensor_row(org_name)
            assert sp_row.is_visible(), f"Root Service Provider {sp_name} should remain visible after Collapse All"
            assert not ns_row.is_visible(), f"Child Namespace {ns_name} should be collapsed/hidden after Collapse All"
            assert not org_row.is_visible(), f"Grandchild Organization {org_name} should be collapsed/hidden after Collapse All"
            attach_screenshot(page, "03_baseline_tree_collapsed_all")

            # Verify Expand All behavior on baseline hierarchy
            sensors_page.expand_all_tree()
            sp_row = sensors_page.get_sensor_row(sp_name)
            ns_row = sensors_page.get_sensor_row(ns_name)
            org_row = sensors_page.get_sensor_row(org_name)
            assert sp_row.is_visible(), f"Root Service Provider {sp_name} should be visible after Expand All"
            assert ns_row.is_visible(), f"Child Namespace {ns_name} should be visible after Expand All"
            assert org_row.is_visible(), f"Grandchild Organization {org_name} should be visible after Expand All"
            attach_screenshot(page, "04_baseline_tree_expanded_all")
            return

        ts = int(time.time())
        sp_name = f"rb-sp-{ts}"
        ns_name = f"rb-ns-{ts}"
        org_name = f"rb-org-{ts}"

        created_nodes = []

        try:
            # 1. Create Service Provider at root
            sensors_page.create_domain(name=sp_name, domain_type=6)
            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            sp_row = sensors_page.get_sensor_row(sp_name)
            assert sp_row.is_visible(), f"Service Provider {sp_name} should be present in tree"
            created_nodes.append(sp_name)
            sp_id = sensors_page.get_node_id(sp_name)
            assert sp_id is not None, f"Failed to retrieve ID for Service Provider {sp_name}"
            attach_screenshot(page, "02_service_provider_created")

            # 2. Create Namespace under Service Provider
            # Note: Creating a Namespace triggers Druid daemon restart/partitioning in Redborder.
            sensors_page.create_domain(name=ns_name, domain_type=8, parent_id=sp_id)
            ssh_client.wait_for_druid_ready(timeout=60)

            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            ns_row = sensors_page.get_sensor_row(ns_name)
            assert ns_row.is_visible(), f"Namespace {ns_name} should be present in tree"
            created_nodes.append(ns_name)
            ns_id = sensors_page.get_node_id(ns_name)
            assert ns_id is not None, f"Failed to retrieve ID for Namespace {ns_name}"
            # Verify tree parent-child relationship
            assert ns_row.get_attribute("data-tt-parent-id") == str(sp_id), (
                f"Namespace {ns_name} parent ID must be {sp_id}"
            )
            attach_screenshot(page, "03_namespace_created")

            # 3. Create Organization under Namespace
            sensors_page.create_domain(name=org_name, domain_type=2, parent_id=ns_id)
            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            org_row = sensors_page.get_sensor_row(org_name)
            assert org_row.is_visible(), f"Organization {org_name} should be present in tree"
            created_nodes.append(org_name)
            org_id = sensors_page.get_node_id(org_name)
            assert org_id is not None, f"Failed to retrieve ID for Organization {org_name}"
            # Verify tree parent-child relationship
            assert org_row.get_attribute("data-tt-parent-id") == str(ns_id), (
                f"Organization {org_name} parent ID must be {ns_id}"
            )
            attach_screenshot(page, "04_organization_created")

            # 4. Verify Collapse All and Expand All behavior on tree hierarchy
            sensors_page.collapse_all_tree()
            sp_row = sensors_page.get_sensor_row(sp_name)
            assert sp_row.is_visible(), f"Root Service Provider {sp_name} should remain visible after Collapse All"
            ns_row = sensors_page.get_sensor_row(ns_name)
            org_row = sensors_page.get_sensor_row(org_name)
            assert not ns_row.is_visible(), f"Child Namespace {ns_name} should be collapsed/hidden after Collapse All"
            assert not org_row.is_visible(), f"Grandchild Organization {org_name} should be collapsed/hidden after Collapse All"
            attach_screenshot(page, "05_tree_collapsed_all")

            # Expand All: all nested descendant nodes should become visible again
            sensors_page.expand_all_tree()
            sp_row = sensors_page.get_sensor_row(sp_name)
            ns_row = sensors_page.get_sensor_row(ns_name)
            org_row = sensors_page.get_sensor_row(org_name)
            assert sp_row.is_visible(), f"Root Service Provider {sp_name} should be visible after Expand All"
            assert ns_row.is_visible(), f"Child Namespace {ns_name} should be visible after Expand All"
            assert org_row.is_visible(), f"Grandchild Organization {org_name} should be visible after Expand All"
            attach_screenshot(page, "06_tree_expanded_all")

        finally:
            # Clean teardown in reverse hierarchical order (child -> parent)
            sensors_page.open_tree()
            sensors_page.expand_all_tree()

            for node in reversed(created_nodes):
                try:
                    row = sensors_page.get_sensor_row(node)
                    if row.is_visible():
                        sensors_page.delete_node(node)
                        if "rb-ns-" in node:
                            ssh_client.wait_for_druid_ready(timeout=60)
                except Exception as e:
                    print(f"Warning: Failed to clean up node {node}: {e}")

            sensors_page.open_tree()
            sensors_page.expand_all_tree()
            for node in created_nodes:
                assert not sensors_page.is_sensor_present(node), (
                    f"Node {node} must be completely deleted from tree"
                )
            attach_screenshot(page, "05_hierarchy_cleaned_up")

