from typing import Optional, Dict, Any
from playwright.sync_api import Locator
from config.settings import settings
from core.pages.base_page import BasePage


class AlarmsPage(BasePage):
    """Page Object Model for Redborder Alarms module (/alarms)."""

    def open_alarms(self) -> None:
        """Navigates to /alarms and ensures page is ready."""
        self.navigate("/alarms")
        self.page.wait_for_load_state("domcontentloaded")

    def open_new_alarm(self) -> None:
        """Navigates to /alarms/new to create a new alarm."""
        self.navigate("/alarms/new")
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_selector("#alarm-form", timeout=settings.default_timeout_ms)

    def create_alarm(
        self,
        name: str,
        product_type: str = "monitor",
        monitor_tab: Optional[str] = "pkts_lost",
        domain_name: Optional[str] = "rb-test-org",
        sensor_name: Optional[str] = "rb-snmp-test",
        bottom_limit: Optional[int] = None,
        upper_limit: Optional[int] = 10,
        treat_missing_as_zero: bool = True,
        incident_enabled: bool = True,
        auto_reactivate: bool = False,
    ) -> bool:
        """Creates a new alarm via the /alarms/new form."""
        self.open_new_alarm()

        # Name
        name_input = self.page.locator("#alarm_name").first
        name_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
        name_input.fill(name)

        # Product Type
        self.page.evaluate(f"""(prod) => {{
            const sel = document.querySelector("#alarm-form-selector");
            if (sel) {{
                sel.value = prod;
                $(sel).trigger('chosen:updated').trigger('change');
            }}
        }}""", product_type)
        self.page.wait_for_timeout(400)

        # Monitor Tab (when product_type == "monitor")
        if monitor_tab and product_type == "monitor":
            self.page.evaluate(f"""(tab) => {{
                const sel = document.querySelector("#alarm_monitor_tab") || document.querySelector("#monitor-tab-selector");
                if (sel) {{
                    sel.value = tab;
                    $(sel).trigger('chosen:updated').trigger('change');
                }}
            }}""", monitor_tab)
            self.page.wait_for_timeout(300)

        # Domain scope
        self.page.evaluate(f"""(dName) => {{
            const sel = document.querySelector("#sensor_dropdown");
            if (sel) {{
                let matched = false;
                for (let opt of sel.options) {{
                    if (dName && opt.text.includes(dName)) {{
                        sel.value = opt.value;
                        $(sel).trigger('chosen:updated').trigger('change');
                        matched = true;
                        break;
                    }}
                }}
                if (!matched) {{
                    for (let opt of sel.options) {{
                        if (opt.value) {{
                            sel.value = opt.value;
                            $(sel).trigger('chosen:updated').trigger('change');
                            break;
                        }}
                    }}
                }}
            }}
        }}""", domain_name)
        self.page.wait_for_timeout(300)

        # Sensor filter rule
        if sensor_name:
            self.page.evaluate(f"""(sName) => {{
                if (window.rule && typeof rule.build === 'function') {{
                    rule.build(JSON.stringify({{
                        match_all: true,
                        items: {{
                            "0": {{
                                column: "sensor_name",
                                operator: "is",
                                value: sName,
                                enabled: true
                            }}
                        }}
                    }}));
                }}
            }}""", sensor_name)
            self.page.wait_for_timeout(300)

        # Bottom limit
        if bottom_limit is not None:
            chk_bottom = self.page.locator("#alarm_bottom_limit_enabled").first
            if not chk_bottom.is_checked():
                chk_bottom.check()
            val_bottom = self.page.locator("#alarm_bottom_limit").first
            val_bottom.wait_for(state="visible", timeout=settings.default_timeout_ms)
            val_bottom.fill(str(bottom_limit))

        # Upper limit
        if upper_limit is not None:
            chk_upper = self.page.locator("#alarm_upper_limit_enabled").first
            if not chk_upper.is_checked():
                chk_upper.check()
            val_upper = self.page.locator("#alarm_upper_limit").first
            val_upper.wait_for(state="visible", timeout=settings.default_timeout_ms)
            val_upper.fill(str(upper_limit))

        # Treat missing as zero
        if treat_missing_as_zero:
            chk_missing = self.page.locator("#alarm_treat_missing_as_zero").first
            if chk_missing.is_visible() and not chk_missing.is_checked():
                chk_missing.check()

        # Auto reactivate
        chk_auto = self.page.locator("#alarm_auto_reactivate").first
        if chk_auto.is_visible():
            if auto_reactivate and not chk_auto.is_checked():
                chk_auto.check()
            elif not auto_reactivate and chk_auto.is_checked():
                chk_auto.uncheck()

        # Incident enabled
        if incident_enabled:
            chk_incident = self.page.locator("#alarm_incident_enabled").first
            if chk_incident.is_visible() and not chk_incident.is_checked():
                chk_incident.check()

        # Submit form
        submit_btn = self.page.locator("button[type='submit'], input[type='submit']").first
        submit_btn.click()
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_timeout(1000)

        return self.is_alarm_present(name)

    def get_alarm_row(self, name: str) -> Locator:
        """Returns the table row Locator for the specified alarm."""
        return self.page.locator("table tbody tr").filter(
            has=self.page.locator(f"td[data-label='Name']:has-text('{name}')")
        ).first

    def is_alarm_present(self, name: str) -> bool:
        """Checks if an alarm row with the given name is present in the table."""
        if "/alarms" not in self.current_url:
            self.open_alarms()
        row = self.get_alarm_row(name)
        return row.is_visible()

    def is_alarm_fired(self, name: str) -> bool:
        """Checks if the alarm row has the 'Fired' badge."""
        row = self.get_alarm_row(name)
        if not row.is_visible():
            return False
        fired_cell = row.locator("td[data-label='Fired'] span.label-danger").first
        return fired_cell.is_visible() and "fired" in fired_cell.inner_text().lower()

    def get_alarm_status(self, name: str) -> Dict[str, Any]:
        """Returns details of the alarm row."""
        row = self.get_alarm_row(name)
        if not row.is_visible():
            return {"present": False}

        enabled_chk = row.locator("input.toggle_enabled").first
        fired_cell = row.locator("td[data-label='Fired']").first
        fired_badge = fired_cell.locator("span.label-danger").first
        is_fired = fired_badge.is_visible() and "fired" in fired_badge.inner_text().lower()
        incident_cell = row.locator("td[data-label='Incident'] i.fa-check").first

        return {
            "present": True,
            "name": name,
            "enabled": enabled_chk.is_checked() if enabled_chk.is_visible() else False,
            "fired": is_fired,
            "incident_enabled": incident_cell.is_visible(),
        }

    def reactivate_alarm(self, name: str, timeout_seconds: int = 15) -> bool:
        """Clicks the reactivate/rearm button on a fired alarm and waits for status to reset."""
        import time

        row = self.get_alarm_row(name)
        if not row.is_visible():
            return False

        reactivate_btn = row.locator("a.reactivate_alarm_button").first
        if not reactivate_btn.is_visible():
            return False

        reactivate_btn.click()

        # Poll until the fired badge is no longer visible
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            self.page.wait_for_timeout(1000)
            if not self.is_alarm_fired(name):
                return True

        return not self.is_alarm_fired(name)

    def delete_alarm(self, name: str) -> bool:
        """Deletes the specified alarm via the row delete action."""
        row = self.get_alarm_row(name)
        if not row.is_visible():
            return False

        self.page.once("dialog", lambda dialog: dialog.accept())

        trash_link = row.locator("a[href*='/alarms/'][data-method='delete'], a:has(i.fa-trash)").first
        if trash_link.is_visible():
            trash_link.click()
            self.page.wait_for_load_state("domcontentloaded")
            self.page.wait_for_timeout(1000)
            return True
        return False
