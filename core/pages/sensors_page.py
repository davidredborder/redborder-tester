import re
from typing import Optional, Dict, Any
from playwright.sync_api import Locator, Page
from core.pages.base_page import BasePage
from config.settings import settings


class SensorsPage(BasePage):
    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)

    def open_tree(self) -> None:
        self.navigate("/sensors/tree")

    def open_flow(self) -> None:
        self.navigate("/sensors/flow")

    def open_ips(self) -> None:
        self.navigate("/sensors/ips")

    def open_snmp(self) -> None:
        self.navigate("/sensors/snmp")

    @property
    def tree_table(self) -> Locator:
        return self.page.locator("table#tree")

    @property
    def tree_rows(self) -> Locator:
        return self.page.locator("table#tree tbody tr")

    @property
    def add_sensor_dropdown(self) -> Locator:
        return self.page.locator("li.add-sensor > a.dropdown-toggle")

    @property
    def flow_sensor_option(self) -> Locator:
        return self.page.locator("li.add-sensor a.new-flow-sensor, li.add-sensor a[href='/sensors/new_flow']").first

    @property
    def vault_sensor_option(self) -> Locator:
        return self.page.locator("li.add-sensor a.new-vault-sensor, li.add-sensor a[href='/sensors/new_vault']").first

    @property
    def snmp_sensor_option(self) -> Locator:
        return self.page.locator("li.add-sensor a.new-snmp-sensor, li.add-sensor a[href='/sensors/new_snmp']").first

    @property
    def vmware_sensor_option(self) -> Locator:
        return self.page.locator("li.add-sensor a.new-vmware-exsi-sensor, li.add-sensor a[href='/sensors/new_vmware_exsi']").first

    @property
    def http_agent_sensor_option(self) -> Locator:
        return self.page.locator("li.add-sensor a.new-http-agent-sensor, li.add-sensor a[href='/sensors/new_http_agent']").first

    @property
    def trap_sensor_option(self) -> Locator:
        return self.page.locator("li.add-sensor a.new-trap-sensor, li.add-sensor a[href='/sensors/new_trap']").first

    @property
    def new_sensor_modal(self) -> Locator:
        return self.page.locator("#new_sensor_modal")

    @property
    def modal_title(self) -> Locator:
        return self.page.locator("#new_sensor_modal .modal-title")

    @property
    def modal_close_button(self) -> Locator:
        return self.page.locator("#new_sensor_modal button.close, #new_sensor_modal [data-dismiss='modal']").first

    def _wait_for_modal_settled(self) -> None:
        """Waits for Bootstrap modal transition to finish and backdrop to settle."""
        self.new_sensor_modal.wait_for(state="visible", timeout=settings.default_timeout_ms)
        # Ensure the Add Sensor dropdown menu is closed so it doesn't overlap the modal
        try:
            self.page.evaluate("""() => {
                const openDropdowns = document.querySelectorAll('li.add-sensor.open, li.dropdown.open');
                openDropdowns.forEach(el => el.classList.remove('open'));
            }""")
        except Exception:
            pass
        # Wait for Bootstrap 'in' class indicating the fade transition completed
        try:
            self.page.locator("#new_sensor_modal.in").wait_for(state="visible", timeout=settings.default_timeout_ms)
        except Exception:
            pass
        # Wait for CSS 300ms transition to finish completely
        self.page.wait_for_timeout(400)

    def open_new_flow_sensor_modal(self) -> None:
        self.add_sensor_dropdown.click()
        self.flow_sensor_option.wait_for(state="visible", timeout=settings.default_timeout_ms)
        self.flow_sensor_option.click()
        self._wait_for_modal_settled()

    def open_new_vault_sensor_modal(self) -> None:
        self.add_sensor_dropdown.click()
        self.vault_sensor_option.wait_for(state="visible", timeout=settings.default_timeout_ms)
        self.vault_sensor_option.click()
        self._wait_for_modal_settled()

    def open_new_snmp_sensor_modal(self) -> None:
        self.add_sensor_dropdown.click()
        self.snmp_sensor_option.wait_for(state="visible", timeout=settings.default_timeout_ms)
        self.snmp_sensor_option.click()
        self._wait_for_modal_settled()

    def create_vault_sensor(self, name: str, ip: str, parent_node_id: Optional[int] = None) -> None:
        """Opens modal, fills Vault (Syslog) sensor form, submits, and waits for modal to close."""
        if parent_node_id:
            self.page.evaluate(f"""() => {{
                const link = document.querySelector('table#tree tr[data-tt-id=\"{parent_node_id}\"] a.add-vault-sensor');
                if (link) link.click();
            }}""")
            self._wait_for_modal_settled()
        else:
            self.open_new_vault_sensor_modal()

        name_input = self.page.locator("#new_sensor_modal input[name='sensor[name]'], #new_sensor_modal #sensor_name").first
        name_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        name_input.fill(name)

        ip_input = self.page.locator("#new_sensor_modal input[name='sensor[ip]'], #new_sensor_modal #sensor_ip").first
        ip_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        ip_input.fill(ip)

        submit_btn = self.page.locator("#new_sensor_modal input[type='submit'], #new_sensor_modal button[type='submit']").first
        submit_btn.click()

        # Check if form submission produced a validation error alert (e.g. "IP must be unique")
        self.page.wait_for_timeout(1000)
        error_alert = self.page.locator("#new_sensor_modal .alert-danger, #new_sensor_modal .error-list").first
        if error_alert.is_visible():
            err_msg = error_alert.inner_text().strip().replace("\n", " ")
            raise AssertionError(f"Sensor creation rejected by platform: {err_msg}")

        self.new_sensor_modal.wait_for(state="hidden", timeout=settings.default_timeout_ms)
        self.page.wait_for_load_state("domcontentloaded")

    def create_snmp_sensor(
        self,
        name: str,
        ip: str,
        community: str = "public",
        version: str = "2c",
        parent_node_id: Optional[int] = None,
    ) -> None:
        """Opens modal, fills SNMP sensor form, submits, and waits for modal to close."""
        if parent_node_id:
            self.page.evaluate(f"""() => {{
                const link = document.querySelector('table#tree tr[data-tt-id=\"{parent_node_id}\"] a.add-snmp-sensor');
                if (link) link.click();
            }}""")
            self._wait_for_modal_settled()
        else:
            self.open_new_snmp_sensor_modal()

        name_input = self.page.locator("#new_sensor_modal input[name='sensor[name]'], #new_sensor_modal #sensor_name").first
        name_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        name_input.fill(name)

        ip_input = self.page.locator("#new_sensor_modal input[name='sensor[ip]'], #new_sensor_modal #sensor_ip").first
        ip_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        ip_input.fill(ip)

        comm_input = self.page.locator(
            "#new_sensor_modal input[name='sensor[snmp_community]'], #new_sensor_modal #sensor_snmp_community"
        ).first
        if comm_input.is_visible():
            comm_input.fill(community)

        version_select = self.page.locator(
            "#new_sensor_modal select[name='sensor[snmp_version]'], #new_sensor_modal #snmp_version_select"
        ).first
        if version_select.is_visible():
            version_select.select_option(value=version)

        submit_btn = self.page.locator("#new_sensor_modal input[type='submit'], #new_sensor_modal button[type='submit']").first
        submit_btn.click()

        self.page.wait_for_timeout(1000)
        error_alert = self.page.locator("#new_sensor_modal .alert-danger, #new_sensor_modal .error-list").first
        if error_alert.is_visible():
            err_msg = error_alert.inner_text().strip().replace("\n", " ")
            raise AssertionError(f"Sensor creation rejected by platform: {err_msg}")

        self.new_sensor_modal.wait_for(state="hidden", timeout=settings.default_timeout_ms)
        self.page.wait_for_load_state("domcontentloaded")

    def create_flow_sensor(
        self,
        name: str,
        ip: str,
        observation_id: Optional[str] = None,
        parent_node_id: Optional[int] = None,
    ) -> None:
        """Opens modal, fills Flow sensor form, submits, and waits for modal to close."""
        if parent_node_id:
            self.page.evaluate(f"""() => {{
                const link = document.querySelector('table#tree tr[data-tt-id=\"{parent_node_id}\"] a.add-flow-sensor');
                if (link) link.click();
            }}""")
            self._wait_for_modal_settled()
        else:
            self.open_new_flow_sensor_modal()

        name_input = self.page.locator("#new_sensor_modal input[name='sensor[name]'], #new_sensor_modal #sensor_name")
        name_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        name_input.fill(name)

        ip_input = self.page.locator("#new_sensor_modal input[name='sensor[ip]'], #new_sensor_modal #sensor_ip")
        ip_input.fill(ip)

        if observation_id:
            obs_input = self.page.locator(
                "#new_sensor_modal input[name='sensor[observation_id]'], #new_sensor_modal #sensor_observation_id"
            )
            if obs_input.is_visible():
                obs_input.fill(str(observation_id))

        submit_btn = self.page.locator("#new_sensor_modal input[type='submit'], #new_sensor_modal button[type='submit']").first
        submit_btn.click()

        self.page.wait_for_timeout(1000)
        error_alert = self.page.locator("#new_sensor_modal .alert-danger, #new_sensor_modal .error-list").first
        if error_alert.is_visible():
            err_msg = error_alert.inner_text().strip().replace("\n", " ")
            raise AssertionError(f"Sensor creation rejected by platform: {err_msg}")

    def open_new_vmware_sensor_modal(self) -> None:
        self.add_sensor_dropdown.click()
        self.vmware_sensor_option.wait_for(state="visible", timeout=settings.default_timeout_ms)
        self.vmware_sensor_option.click()
        self._wait_for_modal_settled()

    def open_new_http_agent_sensor_modal(self) -> None:
        self.add_sensor_dropdown.click()
        self.http_agent_sensor_option.wait_for(state="visible", timeout=settings.default_timeout_ms)
        self.http_agent_sensor_option.click()
        self._wait_for_modal_settled()

    def open_new_trap_sensor_modal(self) -> None:
        self.add_sensor_dropdown.click()
        self.trap_sensor_option.wait_for(state="visible", timeout=settings.default_timeout_ms)
        self.trap_sensor_option.click()
        self._wait_for_modal_settled()

    def create_vmware_sensor(
        self,
        name: str,
        ip: str,
        username: str = "root",
        password: str = "vmware",
        parent_node_id: Optional[int] = None,
    ) -> None:
        """Creates a VMware ESXi sensor either at root or nested under a parent domain/sensor."""
        if parent_node_id:
            self.page.evaluate(f"""() => {{
                const link = document.querySelector('table#tree tr[data-tt-id=\"{parent_node_id}\"] a.add-vmware-exsi-sensor');
                if (link) link.click();
            }}""")
            self._wait_for_modal_settled()
        else:
            self.open_new_vmware_sensor_modal()

        name_input = self.page.locator("#new_sensor_modal input[name='sensor[name]'], #new_sensor_modal #sensor_name").first
        name_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        name_input.fill(name)

        ip_input = self.page.locator("#new_sensor_modal input[name='sensor[ip]'], #new_sensor_modal #sensor_ip").first
        ip_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        ip_input.fill(ip)

        user_input = self.page.locator("#new_sensor_modal input[name='sensor[vmware_username]'], #new_sensor_modal #sensor_vmware_username").first
        if user_input.is_visible():
            user_input.fill(username)

        pwd_input = self.page.locator("#new_sensor_modal input[name='sensor[vmware_password]'], #new_sensor_modal #sensor_vmware_password").first
        if pwd_input.is_visible():
            pwd_input.fill(password)

        submit_btn = self.page.locator("#new_sensor_modal input[type='submit'], #new_sensor_modal button[type='submit']").first
        submit_btn.click()

        self.page.wait_for_timeout(1000)
        error_alert = self.page.locator("#new_sensor_modal .alert-danger, #new_sensor_modal .error-list").first
        if error_alert.is_visible():
            err_msg = error_alert.inner_text().strip().replace("\n", " ")
            raise AssertionError(f"Sensor creation rejected by platform: {err_msg}")

        self.new_sensor_modal.wait_for(state="hidden", timeout=settings.default_timeout_ms)
        self.page.wait_for_load_state("domcontentloaded")

    def create_http_agent_sensor(
        self,
        name: str,
        description: str = "HTTP Agent test sensor",
        parent_node_id: Optional[int] = None,
    ) -> None:
        """Creates an HTTP Agent sensor either at root or nested under a parent domain/sensor."""
        if parent_node_id:
            self.page.evaluate(f"""() => {{
                const link = document.querySelector('table#tree tr[data-tt-id=\"{parent_node_id}\"] a.add-http-agent-sensor');
                if (link) link.click();
            }}""")
            self._wait_for_modal_settled()
        else:
            self.open_new_http_agent_sensor_modal()

        name_input = self.page.locator("#new_sensor_modal input[name='sensor[name]'], #new_sensor_modal #sensor_name").first
        name_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        name_input.fill(name)

        desc_input = self.page.locator("#new_sensor_modal textarea[name='sensor[general_description]'], #new_sensor_modal #sensor_general_description").first
        if desc_input.is_visible():
            desc_input.fill(description)

        submit_btn = self.page.locator("#new_sensor_modal input[type='submit'], #new_sensor_modal button[type='submit']").first
        submit_btn.click()

        self.page.wait_for_timeout(1000)
        error_alert = self.page.locator("#new_sensor_modal .alert-danger, #new_sensor_modal .error-list").first
        if error_alert.is_visible():
            err_msg = error_alert.inner_text().strip().replace("\n", " ")
            raise AssertionError(f"Sensor creation rejected by platform: {err_msg}")

        self.new_sensor_modal.wait_for(state="hidden", timeout=settings.default_timeout_ms)
        self.page.wait_for_load_state("domcontentloaded")

    def create_trap_sensor(
        self,
        name: str,
        ip: str,
        community: str = "public",
        parent_node_id: Optional[int] = None,
    ) -> None:
        """Creates an SNMP Trap sensor either at root or nested under a parent domain/sensor."""
        if parent_node_id:
            self.page.evaluate(f"""() => {{
                const link = document.querySelector('table#tree tr[data-tt-id=\"{parent_node_id}\"] a.add-trap-sensor');
                if (link) link.click();
            }}""")
            self._wait_for_modal_settled()
        else:
            self.open_new_trap_sensor_modal()

        name_input = self.page.locator("#new_sensor_modal input[name='sensor[name]'], #new_sensor_modal #sensor_name").first
        name_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        name_input.fill(name)

        ip_input = self.page.locator("#new_sensor_modal input[name='sensor[ip]'], #new_sensor_modal #sensor_ip").first
        ip_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        ip_input.fill(ip)

        comm_input = self.page.locator("#new_sensor_modal input[name='sensor[trap_community]'], #new_sensor_modal #sensor_trap_community").first
        if comm_input.is_visible():
            comm_input.fill(community)

        submit_btn = self.page.locator("#new_sensor_modal input[type='submit'], #new_sensor_modal button[type='submit']").first
        submit_btn.click()

        self.page.wait_for_timeout(1000)
        error_alert = self.page.locator("#new_sensor_modal .alert-danger, #new_sensor_modal .error-list").first
        if error_alert.is_visible():
            err_msg = error_alert.inner_text().strip().replace("\n", " ")
            raise AssertionError(f"Sensor creation rejected by platform: {err_msg}")

        self.new_sensor_modal.wait_for(state="hidden", timeout=settings.default_timeout_ms)
        self.page.wait_for_load_state("domcontentloaded")

    def create_domain(
        self,
        name: str,
        domain_type: int = 6,
        parent_id: Optional[int] = None,
    ) -> None:
        """
        Creates a domain node:
          - domain_type=6: Service Provider (created at root via Add Domain header or under cluster)
          - domain_type=8: Namespace (created under a Service Provider)
          - domain_type=2: Organization (created under a Namespace or Service Provider)
        """
        if not self.tree_table.is_visible():
            self.open_tree()
            self.page.wait_for_load_state("domcontentloaded")

        if domain_type == 6 and parent_id is None:
            # Service Provider at root
            self.page.evaluate("""() => {
                const openMenus = document.querySelectorAll('.dropdown.open, .btn-group.open');
                openMenus.forEach(m => m.classList.remove('open'));
            }""")
            self.page.wait_for_timeout(200)

            # Check if li.add-domain is open, if not click dropdown toggle
            domain_toggle = self.page.locator("li[data-step='3'] > a.dropdown-toggle, li.add-domain > a.dropdown-toggle, a:has-text('Add Domain')").first
            if domain_toggle.is_visible():
                domain_toggle.click()
                self.page.wait_for_timeout(300)

            sp_opt = self.page.locator("ul.add-domain-menu a[href*='domain_type=6']").first
            if not sp_opt.is_visible():
                # Direct trigger via JS fallback to open the modal
                self.page.evaluate("""() => {
                    const spLink = document.querySelector("ul.add-domain-menu a[href*='domain_type=6']");
                    if (spLink) {
                        spLink.click();
                    } else {
                        $('#default_large').modal('show');
                        $.get('/domain/new?domain_type=6', function(data) {
                            $('#default_large').html(data);
                        });
                    }
                }""")
            else:
                sp_opt.click()
        elif parent_id is not None:
            # Trigger via specific parent node
            css_class = "add-namespace" if domain_type == 8 else "add-organization"
            self.page.evaluate(f"""() => {{
                const link = document.querySelector('table#tree tr[data-tt-id=\"{parent_id}\"] a.{css_class}') ||
                             document.querySelector('table#tree tr[data-tt-id=\"{parent_id}\"] a[href*=\"domain_type={domain_type}\"]');
                if (link) {{
                    link.click();
                }} else {{
                    $('#default_large').modal('show');
                    $.get('/domain/new?domain_type={domain_type}&id={parent_id}', function(data) {{
                        $('#default_large').html(data);
                    }});
                }}
            }}""")
        else:
            raise ValueError("domain_type other than 6 requires parent_id")

        modal = self.page.locator("#default_large")
        modal.wait_for(state="visible", timeout=settings.default_timeout_ms)
        self.page.wait_for_timeout(500)

        name_input = modal.locator("#sensor_name, input[name='sensor[name]']").first
        name_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        name_input.fill(name)

        submit_btn = modal.locator("input[type='submit'], button[type='submit']").first
        submit_btn.click()

        self.page.wait_for_timeout(1000)
        error_alert = modal.locator(".alert-danger, .error-list").first
        if error_alert.is_visible():
            err_msg = error_alert.inner_text().strip().replace("\n", " ")
            raise AssertionError(f"Domain creation rejected: {err_msg}")

        modal.wait_for(state="hidden", timeout=settings.default_timeout_ms)
        self.page.wait_for_load_state("domcontentloaded")

    def ensure_domain_hierarchy(
        self,
        sp_name: str = "rb-test-sp",
        ns_name: str = "rb-test-ns",
        org_name: str = "rb-test-org",
        sp2_name: Optional[str] = "rb-test-sp2",
    ) -> Dict[str, Any]:
        """Ensures a stable domain hierarchy (SP -> NS -> Org, plus optional destination SP2) exists in tree,
        creating missing levels only if not already present.

        Returns dictionary with node IDs and names:
          {'sp_name': str, 'sp_id': int, 'ns_name': str, 'ns_id': int, 'org_name': str, 'org_id': int,
           'dst_sp_name': Optional[str], 'dst_sp_id': Optional[int]}.
        """
        self.open_tree()
        self.expand_all_tree()

        # 1. Primary Service Provider (domain_type=6)
        sp_id = self.get_node_id(sp_name)
        if not sp_id:
            self.create_domain(name=sp_name, domain_type=6)
            self.open_tree()
            self.expand_all_tree()
            sp_id = self.get_node_id(sp_name)
            assert sp_id is not None, f"Failed to ensure Service Provider '{sp_name}'"

        # 2. Namespace (domain_type=8) under Service Provider
        ns_id = self.get_node_id(ns_name)
        if not ns_id:
            self.create_domain(name=ns_name, domain_type=8, parent_id=sp_id)
            self.open_tree()
            self.expand_all_tree()
            ns_id = self.get_node_id(ns_name)
            assert ns_id is not None, f"Failed to ensure Namespace '{ns_name}'"

        # 3. Organization (domain_type=2) under Namespace
        org_id = self.get_node_id(org_name)
        if not org_id:
            self.create_domain(name=org_name, domain_type=2, parent_id=ns_id)
            self.open_tree()
            self.expand_all_tree()
            org_id = self.get_node_id(org_name)
            assert org_id is not None, f"Failed to ensure Organization '{org_name}'"

        # 4. Optional Secondary Service Provider (for drag-and-drop / domain moves)
        sp2_id = None
        if sp2_name:
            sp2_id = self.get_node_id(sp2_name)
            if not sp2_id:
                self.create_domain(name=sp2_name, domain_type=6)
                self.open_tree()
                self.expand_all_tree()
                sp2_id = self.get_node_id(sp2_name)
                assert sp2_id is not None, f"Failed to ensure secondary Service Provider '{sp2_name}'"

        return {
            "sp_name": sp_name,
            "sp_id": sp_id,
            "ns_name": ns_name,
            "ns_id": ns_id,
            "org_name": org_name,
            "org_id": org_id,
            "dst_sp_name": sp2_name,
            "dst_sp_id": sp2_id,
        }

    def cleanup_domain_hierarchy(
        self,
        sp_name: str = "rb-test-sp",
        ns_name: str = "rb-test-ns",
        org_name: str = "rb-test-org",
        sp2_name: Optional[str] = "rb-test-sp2",
    ) -> None:
        """Deletes the domain hierarchy in reverse order (Org -> NS -> SP -> SP2)."""
        self.open_tree()
        self.expand_all_tree()
        nodes_to_clean = [org_name, ns_name, sp_name]
        if sp2_name:
            nodes_to_clean.append(sp2_name)

        for node_name in nodes_to_clean:
            if self.is_sensor_present(node_name):
                try:
                    self.delete_node(node_name)
                except Exception as e:
                    print(f"Warning: Failed to delete node '{node_name}': {e}")

    def ensure_full_testbed(
        self,
        sp_name: str = "rb-test-sp",
        ns_name: str = "rb-test-ns",
        org_name: str = "rb-test-org",
        sp2_name: str = "rb-test-sp2",
    ) -> Dict[str, Any]:
        """Provisions the full, unified baseline testbed in the Web UI:
        1. Domain hierarchy (SP -> NS -> Org, plus destination SP2).
        2. Custom tabs and monitor categories (Web Latency custom tab, HTTP Agent category, SNMP CPU category).
        3. All standard baseline sensors:
           - rb-flow-test (IP 10.10.10.2, nested under Org)
           - rb-vault-test (IP 10.10.10.3, nested under Org)
           - rb-snmp-test (IP 10.10.10.4, community 'redBorder', nested under Org)
           - rb-http-test (IP 10.10.10.50, nested under Org)
           - rb-vmware-test (IP 10.30.1.4, nested under Org)
           - rb-trap-test (IP 10.30.1.5, nested under Org)
        4. Attaches custom monitor categories to the corresponding sensors.

        Returns dictionary containing all provisioned metadata and node IDs.
        """
        # 1. Ensure domain hierarchy
        hierarchy = self.ensure_domain_hierarchy(
            sp_name=sp_name,
            ns_name=ns_name,
            org_name=org_name,
            sp2_name=sp2_name,
        )
        org_id = hierarchy["org_id"]

        # 2. Custom Tab: Web Latency
        custom_tab_name = "Web Latency"
        custom_tab_key = "custom_web_latency"
        try:
            self.create_custom_tab(custom_tab_name, units="ms")
        except Exception:
            pass

        # 3. Custom Monitor Categories
        # A. HTTP Agent category
        http_cat_name = "rb-test-http-cat"
        try:
            self.create_custom_http_agent_monitor_category(
                name=http_cat_name,
                url="http://10.10.10.50/",
                method="GET",
                expected_status=200,
                category=custom_tab_key,
                default_category=False,
            )
        except Exception:
            pass

        # B. SNMP CPU category
        snmp_cat_name = "rb-test-cpu-cat"
        try:
            self.create_custom_snmp_monitor_category(
                name=snmp_cat_name,
                oid="1.3.6.1.4.1.9.9.109.1.1.1.1.5.1",
                category="cpu",
                description="Baseline CPU poller for redborder-tester",
            )
        except Exception:
            pass

        # 4. Provision baseline sensors under Organization
        self.open_tree()
        self.expand_all_tree()

        # A. Flow sensor
        flow_sensor = "rb-flow-test"
        if not self.is_sensor_present(flow_sensor):
            self.create_flow_sensor(name=flow_sensor, ip="10.10.10.2", parent_node_id=org_id)
            self.open_tree()
            self.expand_all_tree()

        # B. Vault sensor
        vault_sensor = "rb-vault-test"
        if not self.is_sensor_present(vault_sensor):
            self.create_vault_sensor(name=vault_sensor, ip="10.10.10.3", parent_node_id=org_id)
            self.open_tree()
            self.expand_all_tree()

        # C. SNMP sensor
        snmp_sensor = "rb-snmp-test"
        if not self.is_sensor_present(snmp_sensor):
            self.create_snmp_sensor(name=snmp_sensor, ip="10.10.10.4", community="redBorder", parent_node_id=org_id)
            self.open_tree()
            self.expand_all_tree()

        # D. HTTP Agent sensor (created at root level)
        http_sensor = "rb-http-test"
        if not self.is_sensor_present(http_sensor):
            self.create_http_agent_sensor(name=http_sensor)
            self.open_tree()
            self.expand_all_tree()

        # E. VMware ESXi sensor
        vmware_sensor = "rb-vmware-test"
        if not self.is_sensor_present(vmware_sensor):
            self.create_vmware_sensor(name=vmware_sensor, ip="10.30.1.4", username="root", password="password", parent_node_id=org_id)
            self.open_tree()
            self.expand_all_tree()

        # F. SNMP Trap sensor
        trap_sensor = "rb-trap-test"
        if not self.is_sensor_present(trap_sensor):
            self.create_trap_sensor(name=trap_sensor, ip="10.30.1.5", community="public", parent_node_id=org_id)
            self.open_tree()
            self.expand_all_tree()

        # 5. Attach monitor categories
        http_sensor_id = self.get_node_id(http_sensor)
        if http_sensor_id:
            try:
                self.attach_http_agent_monitor_category(sensor_id=http_sensor_id, category_keyword=http_cat_name)
            except Exception:
                pass

        snmp_sensor_id = self.get_node_id(snmp_sensor)
        if snmp_sensor_id:
            try:
                self.attach_cpu_monitor_category(sensor_id=snmp_sensor_id, category_keyword=snmp_cat_name)
            except Exception:
                pass

        return {
            **hierarchy,
            "custom_tab_name": custom_tab_name,
            "custom_tab_key": custom_tab_key,
            "http_cat_name": http_cat_name,
            "snmp_cat_name": snmp_cat_name,
            "sensors": {
                "flow": flow_sensor,
                "vault": vault_sensor,
                "snmp": snmp_sensor,
                "http": http_sensor,
                "vmware": vmware_sensor,
                "trap": trap_sensor,
            },
        }

    def cleanup_full_testbed(
        self,
        sp_name: str = "rb-test-sp",
        ns_name: str = "rb-test-ns",
        org_name: str = "rb-test-org",
        sp2_name: str = "rb-test-sp2",
    ) -> None:
        """Tears down the entire baseline testbed:
        1. Deletes all baseline sensors.
        2. Deletes custom monitor categories.
        3. Deletes custom tabs.
        4. Deletes domain hierarchy (Org -> NS -> SP, SP2).
        """
        # 1. Delete sensors
        self.open_tree()
        self.expand_all_tree()
        for s_name in [
            "rb-trap-test",
            "rb-vmware-test",
            "rb-http-test",
            "rb-snmp-test",
            "rb-vault-test",
            "rb-flow-test",
        ]:
            if self.is_sensor_present(s_name):
                try:
                    self.delete_sensor(s_name, timeout_seconds=15)
                except Exception:
                    pass

        # 2. Delete monitor categories
        for cat_name in ["rb-test-http-cat", "rb-test-cpu-cat"]:
            try:
                self.delete_monitor_category_by_name(cat_name)
            except Exception:
                pass

        # 3. Delete custom tabs
        try:
            self.delete_custom_tab_by_name("Web Latency")
        except Exception:
            pass

        # 4. Delete domains
        self.cleanup_domain_hierarchy(
            sp_name=sp_name,
            ns_name=ns_name,
            org_name=org_name,
            sp2_name=sp2_name,
        )


    def expand_all_tree(self) -> None:
        """Clicks Expand All toolbar button to reveal all nested tree nodes."""
        expand_btn = self.page.locator("a[href*='expand_all_tree'], a#expand-sensors, a.panel-button:has-text('Expand')").first
        if expand_btn.is_visible():
            expand_btn.click()
            # Wait for blockUI overlay or AJAX response to settle
            try:
                self.page.locator(".blockUI.blockOverlay").wait_for(state="hidden", timeout=10000)
            except Exception:
                pass
            # Allow jQuery treetable animation to unhide child rows
            try:
                self.page.wait_for_function(
                    "() => !document.querySelector('.blockUI.blockOverlay') && "
                    "(!document.querySelector('table#tree tr.branch.collapsed') || "
                    "document.querySelectorAll('table#tree tr.branch.expanded').length > 0)",
                    timeout=5000,
                )
            except Exception:
                pass
            self.page.wait_for_timeout(1000)

    def collapse_all_tree(self) -> None:
        """Clicks Collapse All toolbar button to hide all nested child tree nodes."""
        collapse_btn = self.page.locator("a#collapse-sensors, a.panel-button:has-text('Collapse')").first
        if collapse_btn.is_visible():
            collapse_btn.click()
            try:
                self.page.locator(".blockUI.blockOverlay").wait_for(state="hidden", timeout=10000)
            except Exception:
                pass
            try:
                self.page.wait_for_function(
                    "() => !document.querySelector('.blockUI.blockOverlay') && "
                    "(!document.querySelector('table#tree tr.branch.expanded') || "
                    "document.querySelectorAll('table#tree tr.branch.collapsed').length > 0)",
                    timeout=5000,
                )
            except Exception:
                pass
            self.page.wait_for_timeout(1000)


    def get_sensor_row(self, name: str) -> Locator:
        """Returns the locator for the table row matching exact sensor name in name cell."""
        name_pattern = re.compile(rf"^\s*{re.escape(name)}\s*$")
        return self.page.locator("table#tree tbody tr").filter(
            has=self.page.locator("td.name, td[data-label='Name'], td.name a, td.name span", has_text=name_pattern)
        ).first

    def get_sensor_id(self, name: str) -> Optional[int]:
        """Extracts the numeric sensor ID from the edit link or data attributes of the sensor row."""
        row = self.get_sensor_row(name)
        if not row.is_visible():
            self.expand_all_tree()
            row = self.get_sensor_row(name)
        if not row.is_visible():
            return None
        # Check data-tt-id attribute first
        tt_id = row.get_attribute("data-tt-id")
        if tt_id and tt_id.isdigit():
            return int(tt_id)
        # Look for edit link href like /sensors/50/edit
        edit_links = row.locator("a[href*='/sensors/'][href*='/edit']")
        if edit_links.count() > 0:
            href = edit_links.first.get_attribute("href") or ""
            m = re.search(r"/sensors/(\d+)/edit", href)
            if m:
                return int(m.group(1))
        # Check trash button or other links
        delete_btn = row.locator("a.sensor-delete, a[href*='/sensors/']")
        if delete_btn.count() > 0:
            href = delete_btn.first.get_attribute("href") or ""
            m = re.search(r"/sensors/(\d+)", href)
            if m:
                return int(m.group(1))
        return None

    def open_sensor_monitor_categories(self, sensor_id: int) -> None:
        """Navigates directly to the Monitor Categories management page for a sensor."""
        self.navigate(f"/sensors/{sensor_id}/monitor_categories")
        self.page.wait_for_load_state("domcontentloaded")

    def attach_cpu_monitor_category(self, sensor_id: int, category_keyword: str = "CPU") -> bool:
        """Opens 'Add Monitor' modal for the sensor and attaches the monitor category (if not already attached)."""
        self.open_sensor_monitor_categories(sensor_id)

        # Check if already attached to this sensor (check Monitor or Description or full row text)
        existing_rows = self.page.locator("table tbody tr")
        for i in range(existing_rows.count()):
            row_text = existing_rows.nth(i).inner_text()
            if category_keyword in row_text:
                return True

        # Click "+ Add Monitor" button
        add_btn = self.page.locator("a[href*='monitor_categories/new']").first
        if not add_btn.is_visible():
            return False
        add_btn.click()

        # Wait for modal #new_monitor_category_modal
        modal = self.page.locator("#new_monitor_category_modal")
        modal.wait_for(state="visible", timeout=settings.default_timeout_ms)
        self.page.wait_for_timeout(500)

        # Try filtering if search input is available
        search_input = modal.locator("#search_monitor_name")
        if search_input.is_visible():
            search_input.fill(category_keyword)
            self.page.wait_for_timeout(400)

        # Locate target row by category_keyword in modal table
        row = modal.locator(f"#add-monitor-table tbody tr:has-text('{category_keyword}')").first
        if not row.is_visible():
            # If search filtered it out or text format differs, clear search and look through all visible rows
            if search_input.is_visible():
                search_input.fill("")
                self.page.wait_for_timeout(300)
            row = modal.locator("#add-monitor-table tbody tr").filter(
                has=modal.locator(f"td:has-text('{category_keyword}')")
            ).first

        if not row.is_visible():
            # Modal might not list it if already added or not matching
            close_btn = modal.locator("button.close, [data-dismiss='modal']").first
            if close_btn.is_visible():
                close_btn.click()
                self.page.wait_for_timeout(300)
            # Double check if now visible in main table
            for i in range(existing_rows.count()):
                row_text = existing_rows.nth(i).inner_text()
                if category_keyword in row_text:
                    return True
            return False

        action_btn = row.locator("td[data-label='Action'] a.add-monitor-but, td[data-label='Action'] a.btn-success:not(.disabled)").first
        if action_btn.is_visible():
            action_btn.click()
            self.page.wait_for_timeout(1000)

        # Close the modal
        close_btn = modal.locator("button.close, [data-dismiss='modal']").first
        if close_btn.is_visible():
            close_btn.click()
            self.page.wait_for_timeout(500)

        return True

    def create_custom_snmp_monitor_category(
        self,
        name: str,
        oid: str,
        category: str = "cpu",
        description: str = "Custom CPU monitor for redborder-tester",
    ) -> bool:
        """Navigates to /monitor/list, opens 'New Monitor' modal, fills and creates a custom SNMP monitor category."""
        self.navigate("/monitor/list")
        self.page.wait_for_load_state("domcontentloaded")

        new_btn = self.page.locator("a[href*='new_monitor_category']").first
        new_btn.wait_for(state="visible", timeout=settings.default_timeout_ms)
        new_btn.click()

        modal = self.page.locator("#new_monitor_category_modal")
        modal.wait_for(state="visible", timeout=settings.default_timeout_ms)
        self.page.wait_for_timeout(500)

        # Name & description
        name_input = modal.locator("#monitor_category_name")
        name_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        name_input.fill(name)

        desc_input = modal.locator("#monitor_category_description")
        if desc_input.is_visible():
            desc_input.fill(description)

        # Technology: SNMP is default
        modal.evaluate("""() => {
            const tech = document.querySelector("#monitor_category_technology");
            if (tech) {
                tech.value = "snmp";
                $(tech).trigger('chosen:updated').trigger('change');
            }
        }""")
        self.page.wait_for_timeout(300)

        # Category / Tab: select 'cpu'
        modal.evaluate(f"""() => {{
            const cat = document.querySelector("#monitor_category_category");
            if (cat) {{
                cat.value = "{category}";
                $(cat).trigger('chosen:updated').trigger('change');
            }}
        }}""")
        self.page.wait_for_timeout(300)

        # OID input: #var_0
        oid_input = modal.locator("#var_0")
        oid_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        oid_input.fill(oid)

        # Default checkbox & sensor types
        default_cb = modal.locator("#monitor_category_default")
        if default_cb.is_visible() and not default_cb.is_checked():
            default_cb.check()
            self.page.wait_for_timeout(300)

        # Select SNMP sensor type (18)
        modal.evaluate("""() => {
            const types = document.querySelector("select[name='monitor_category[sensor_types][]']");
            if (types) {
                for (let opt of types.options) {
                    if (opt.value === '18') opt.selected = true;
                }
                $(types).trigger('chosen:updated').trigger('change');
            }
        }""")

        # Submit form
        submit_btn = modal.locator("input[type='submit'], button[type='submit']").first
        submit_btn.click()

        modal.wait_for(state="hidden", timeout=settings.default_timeout_ms)
        self.page.wait_for_load_state("domcontentloaded")
        return True

    def create_custom_http_agent_monitor_category(
        self,
        name: str,
        url: str,
        method: str = "GET",
        expected_status: int = 200,
        category: str = "http_latency",
        description: str = "Custom HTTP Agent monitor for redborder-tester",
        auth_type: str = "none",
        username: str = "",
        password: str = "",
        timeout: str = "5s",
        default_category: bool = False,
    ) -> bool:
        """Navigates to /monitor/list, opens 'New Monitor' modal, fills and creates a custom HTTP Agent monitor category."""
        self.navigate("/monitor/list")
        self.page.wait_for_load_state("domcontentloaded")

        new_btn = self.page.locator("a[href*='new_monitor_category']").first
        new_btn.wait_for(state="visible", timeout=settings.default_timeout_ms)
        new_btn.click()

        modal = self.page.locator("#new_monitor_category_modal")
        modal.wait_for(state="visible", timeout=settings.default_timeout_ms)
        self.page.wait_for_timeout(500)

        # Name & description
        name_input = modal.locator("#monitor_category_name")
        name_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        name_input.fill(name)

        desc_input = modal.locator("#monitor_category_description")
        if desc_input.is_visible():
            desc_input.fill(description)

        # Technology: select 'http_agent'
        modal.evaluate("""() => {
            const tech = document.querySelector("#monitor_category_technology");
            if (tech) {
                tech.value = "http_agent";
                $(tech).trigger('chosen:updated').trigger('change');
            }
        }""")
        self.page.wait_for_timeout(400)

        # Category / Tab: select target category tab
        if category:
            modal.evaluate(f"""() => {{
                const cat = document.querySelector("#monitor_category_category");
                if (cat) {{
                    cat.value = "{category}";
                    $(cat).trigger('chosen:updated').trigger('change');
                }}
            }}""")
            self.page.wait_for_timeout(300)

        # Fill HTTP Agent URL
        url_input = modal.locator("#monitor_category_http_agent_url, input[name='monitor_category[http_agent_url]']").first
        url_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        url_input.fill(url)

        # Select HTTP method
        modal.evaluate(f"""() => {{
            const reqType = document.querySelector("#monitor_category_http_agent_request_type");
            if (reqType) {{
                reqType.value = "{method.upper()}";
                $(reqType).trigger('chosen:updated').trigger('change');
            }}
        }}""")

        # Status code
        status_input = modal.locator("#monitor_category_http_agent_required_status_code")
        if status_input.is_visible():
            status_input.fill(str(expected_status))

        # Timeout
        timeout_input = modal.locator("#monitor_category_http_agent_timeout")
        if timeout_input.is_visible():
            timeout_input.fill(timeout)

        # Authentication if basic
        if auth_type.lower() == "basic" and username and password:
            modal.evaluate(f"""() => {{
                const authSel = document.querySelector("#monitor_category_http_agent_http_authentication");
                if (authSel) {{
                    authSel.value = "basic";
                    $(authSel).trigger('chosen:updated').trigger('change');
                }}
            }}""")
            self.page.wait_for_timeout(300)
            u_input = modal.locator("#monitor_category_http_agent_username")
            p_input = modal.locator("#monitor_category_http_agent_password")
            if u_input.is_visible():
                u_input.fill(username)
            if p_input.is_visible():
                p_input.fill(password)

        # Default checkbox & sensor types
        default_cb = modal.locator("#monitor_category_default")
        if default_category:
            if default_cb.is_visible() and not default_cb.is_checked():
                default_cb.check()
                self.page.wait_for_timeout(300)
        else:
            if default_cb.is_visible() and default_cb.is_checked():
                default_cb.uncheck()
                self.page.wait_for_timeout(300)

        # Select HTTP Agent sensor type (23)
        modal.evaluate("""() => {
            const types = document.querySelector("select[name='monitor_category[sensor_types][]']");
            if (types) {
                for (let opt of types.options) {
                    if (opt.value === '23') opt.selected = true;
                }
                $(types).trigger('chosen:updated').trigger('change');
            }
        }""")

        # Submit form
        submit_btn = modal.locator("input[type='submit'], button[type='submit']").first
        submit_btn.click()

        modal.wait_for(state="hidden", timeout=settings.default_timeout_ms)
        self.page.wait_for_load_state("domcontentloaded")
        return True

    def attach_http_agent_monitor_category(self, sensor_id: int, category_keyword: str) -> bool:
        """Navigates to the HTTP Agent sensor edit page and attaches the monitor category."""
        return self.attach_cpu_monitor_category(sensor_id=sensor_id, category_keyword=category_keyword)

    def delete_monitor_category_by_name(self, name: str) -> bool:
        """Navigates to /monitor/list and deletes custom monitor category by name."""
        self.navigate(f"/monitor/list?q={name}")
        self.page.wait_for_load_state("domcontentloaded")

        row = self.page.locator("table#monitor-list-table tbody tr").filter(has_text=name).first
        if not row.is_visible():
            return False

        # Set up dialog handler for window.confirm
        self.page.once("dialog", lambda dialog: dialog.accept())

        trash_link = row.locator("a[href*='delete_monitor_category']").first
        if trash_link.is_visible():
            trash_link.click()
            self.page.wait_for_timeout(1000)
            return True
        return False

    def is_sensor_present(self, name: str) -> bool:
        """Checks if a sensor with given exact name exists in tree table."""
        row = self.get_sensor_row(name)
        return row.is_visible()

    def delete_sensor(self, name: str, timeout_seconds: int = 30) -> bool:
        """Deletes sensor by name using the row trash button and confirming modal,
        polling to ensure background delayed jobs and tree removal complete."""
        import time

        # Ensure we are on the tree view
        if not self.tree_table.is_visible():
            self.open_tree()
            self.page.wait_for_load_state("domcontentloaded")

        row = self.get_sensor_row(name)
        if not row.is_visible():
            return False

        node_id = self.get_node_id(name)

        delete_btn = row.locator("a.sensor-delete").first
        delete_btn.scroll_into_view_if_needed()
        delete_btn.click()

        # Wait for confirmation modal
        confirm_modal = self.page.locator("#default_large")
        confirm_modal.wait_for(state="visible", timeout=settings.default_timeout_ms)
        self.page.wait_for_timeout(400)

        confirm_btn = self.page.locator("#default_large a.confirmed-delete-sensor").first
        confirm_btn.wait_for(state="visible", timeout=settings.default_timeout_ms)
        confirm_btn.click()

        # Wait for modal to hide
        try:
            confirm_modal.wait_for(state="hidden", timeout=settings.default_timeout_ms)
        except Exception:
            pass

        # Poll until the sensor/domain row is no longer visible in tree (allowing delayed_job to complete)
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            self.page.wait_for_timeout(1000)
            if not self.get_sensor_row(name).is_visible():
                return True

            # If still present after 4s, reload tree page
            if (time.time() - start_time) > 4:
                self.open_tree()
                self.expand_all_tree()
                if not self.get_sensor_row(name).is_visible():
                    return True

        # Fallback: if node_id is known, attempt direct API DELETE call
        if node_id:
            try:
                csrf_token = self.page.locator("meta[name='csrf-token']").get_attribute("content") or ""
                self.page.evaluate(f"""() => {{
                    return fetch('/sensors/{node_id}', {{
                        method: 'DELETE',
                        headers: {{
                            'X-CSRF-Token': '{csrf_token}',
                            'Accept': 'application/json'
                        }}
                    }}).then(r => r.json()).catch(() => ({{}}));
                }}""")
                self.page.wait_for_timeout(2000)
                self.open_tree()
                self.expand_all_tree()
                if not self.get_sensor_row(name).is_visible():
                    return True
            except Exception:
                pass

        row = self.get_sensor_row(name)
        assert not row.is_visible(), f"Sensor {name} still present after deletion (waited {timeout_seconds}s for delayed job)"
        return True

    def get_node_id(self, name: str) -> Optional[int]:
        """Extracts the numeric ID (data-tt-id) of any tree row (domain or sensor)."""
        row = self.get_sensor_row(name)
        if not row.is_visible():
            return None
        tt_id = row.get_attribute("data-tt-id")
        if tt_id and tt_id.isdigit():
            return int(tt_id)
        return self.get_sensor_id(name)

    def get_node_parent_id(self, name: str) -> Optional[int]:
        """Extracts the parent numeric ID (data-tt-parent-id) of any tree row."""
        row = self.get_sensor_row(name)
        if not row.is_visible():
            return None
        tt_parent = row.get_attribute("data-tt-parent-id")
        if tt_parent and tt_parent.isdigit():
            return int(tt_parent)
        return None

    def delete_node(self, name: str) -> bool:
        """Alias for delete_sensor that deletes any tree row (sensor or domain node)."""
        return self.delete_sensor(name)

    def drag_sensor_to_node(self, sensor_name: str, target_node_name: str) -> None:
        """Drags a sensor to a target domain node row in the tree table and confirms the dialog."""
        sensor_row = self.get_sensor_row(sensor_name)
        target_row = self.get_sensor_row(target_node_name)
        assert sensor_row.is_visible(), f"Source sensor {sensor_name} not visible in tree"
        assert target_row.is_visible(), f"Target node {target_node_name} not visible in tree"

        # The draggable element is typically a span/a inside the sensor td
        drag_handle = sensor_row.locator("span.sensor, span.flow, span.vault, span.snmp, span.trap, span.vmware_exsi, td:nth-child(2)").first
        if not drag_handle.is_visible():
            drag_handle = sensor_row.locator("td").first

        # Ensure hover to trigger jQuery UI mouseenter binding if needed
        drag_handle.hover()
        self.page.wait_for_timeout(200)

        # Listen for native confirmation dialog: confirm("Are you sure...?")
        def handle_dialog(dialog):
            dialog.accept()

        self.page.once("dialog", handle_dialog)

        # Drag and drop onto target row, waiting for change_parent AJAX response
        try:
            with self.page.expect_response(
                lambda response: "change_parent" in response.url and response.status == 200,
                timeout=5000,
            ):
                drag_handle.drag_to(target_row)
        except Exception:
            pass

        self.page.wait_for_timeout(1000)

    def drag_sensor_to_root(self, sensor_name: str, max_retries: int = 3) -> None:
        """Drags a sensor to the table thead (root drop zone) to move it to root domain."""
        for attempt in range(max_retries):
            sensor_row = self.get_sensor_row(sensor_name)
            assert sensor_row.is_visible(), f"Source sensor {sensor_name} not visible in tree"

            root_drop_zone = self.page.locator("table#tree thead")
            assert root_drop_zone.is_visible(), "Table header root drop zone not visible"

            drag_handle = sensor_row.locator("span.sensor, span.flow, span.vault, span.snmp, span.trap, span.vmware_exsi, td:nth-child(2)").first
            if not drag_handle.is_visible():
                drag_handle = sensor_row.locator("td").first

            drag_handle.hover()
            self.page.wait_for_timeout(200)

            def handle_dialog(dialog):
                dialog.accept()

            self.page.once("dialog", handle_dialog)

            try:
                with self.page.expect_response(
                    lambda response: "change_parent" in response.url and response.status == 200,
                    timeout=5000,
                ):
                    drag_handle.drag_to(root_drop_zone)
            except Exception:
                pass

            self.page.wait_for_timeout(1000)

            # Check if parent is now root (None or empty)
            current_parent = self.get_node_parent_id(sensor_name)
            if current_parent is None:
                return

            # If still not None and not last attempt, pause briefly and retry
            if attempt < max_retries - 1:
                self.page.wait_for_timeout(1000)

    def create_custom_tab(self, name: str, units: str = "ms") -> str:
        """Navigates to /custom_tabs, creates a custom tab, and returns its registered tab key."""
        self.navigate("/custom_tabs")
        self.page.wait_for_load_state("domcontentloaded")

        new_btn = self.page.locator("a[data-target='#new_custom_tab_modal'], a[href*='new_custom_tab']").first
        new_btn.wait_for(state="visible", timeout=settings.default_timeout_ms)
        new_btn.click()

        modal = self.page.locator("#new_custom_tab_modal")
        modal.wait_for(state="visible", timeout=settings.default_timeout_ms)
        self.page.wait_for_timeout(400)

        name_input = modal.locator("#custom_tab_name, input[name='custom_tab[name]']").first
        name_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        name_input.fill(name)

        unit_input = modal.locator("#custom_tab_units, input[name='custom_tab[units]']").first
        if unit_input.is_visible() and units:
            unit_input.fill(units)

        submit_btn = modal.locator("input[type='submit'], button[type='submit']").first
        submit_btn.click()

        modal.wait_for(state="hidden", timeout=settings.default_timeout_ms)
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_timeout(500)

        # Tab name is category (lowercase 'custom') + '_' + name lowercase sanitized
        clean_name = name.lower().strip().replace(" ", "_")
        return f"custom_{clean_name}"

    def delete_custom_tab_by_name(self, name: str) -> bool:
        """Navigates to /custom_tabs and deletes custom tab by name."""
        self.navigate("/custom_tabs")
        self.page.wait_for_load_state("domcontentloaded")

        row = self.page.locator("article#custom_tabs table tbody tr").filter(has_text=name).first
        if not row.is_visible():
            return False

        self.page.once("dialog", lambda dialog: dialog.accept())

        trash_link = row.locator("a[data-method='delete'], a[href*='/custom_tabs/'] i.fa-trash").first
        if trash_link.is_visible():
            trash_link.click()
            self.page.wait_for_timeout(1000)
            return True
        return False

    def open_monitor_tab(self, tab_key: str) -> None:
        """Navigates to /monitor with ?category={tab_key} or activates tab from dropdown/tabs list."""
        self.navigate(f"/monitor?category={tab_key}")
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_timeout(500)

        # Check if tab exists in active tabs bar
        tab_link = self.page.locator(f"ul.nav-tabs.monitor li a[href='#tab_{tab_key}']").first
        if not tab_link.is_visible():
            # Open Add Tab dropdown to activate it
            add_tab_btn = self.page.locator("a.dropdown-toggle:has(i.fa-tags), li[data-step='6'] > a.dropdown-toggle").first
            if add_tab_btn.is_visible():
                add_tab_btn.click()
                self.page.wait_for_timeout(300)
                tab_opt = self.page.locator(f"#tops a[id='{tab_key}'], #tops a[href*='add_tab/{tab_key}']").first
                if tab_opt.is_visible():
                    tab_opt.click()
                    self.page.wait_for_timeout(800)

        # Click the tab to make sure it is selected and active
        tab_link = self.page.locator(f"ul.nav-tabs.monitor li a[href='#tab_{tab_key}']").first
        if tab_link.is_visible():
            tab_link.click()
            self.page.wait_for_timeout(500)


