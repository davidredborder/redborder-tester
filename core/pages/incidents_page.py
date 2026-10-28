from typing import Optional
from playwright.sync_api import Locator, TimeoutError as PlaywrightTimeoutError
from core.pages.base_page import BasePage


class IncidentsPage(BasePage):
    """Page Object Model for Redborder Incidents module (/incidents)."""

    def open_incidents(self) -> None:
        """Navigates to /incidents and waits for page load."""
        self.navigate("/incidents")
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_timeout(500)

    def get_incident_row(self, name: str) -> Locator:
        """Returns the table row Locator for an incident matching the name."""
        return self.page.locator("table#incidents-table tbody tr").filter(
            has=self.page.locator(f"td[data-label='Name'] .incident-name-text:has-text('{name}')")
        ).first

    def is_incident_present(self, name: str, timeout_ms: int = 5000) -> bool:
        """Checks if an incident with the given name exists in the table."""
        if "/incidents" not in self.current_url:
            self.open_incidents()
        row = self.get_incident_row(name)
        try:
            row.wait_for(state="visible", timeout=timeout_ms)
            return True
        except PlaywrightTimeoutError:
            return False

    def get_incident_status(self, name: str) -> Optional[str]:
        """Returns the status text of the specified incident."""
        row = self.get_incident_row(name)
        if not row.is_visible():
            return None
        status_cell = row.locator("td[data-label='Status']").first
        if not status_cell.is_visible():
            return None

        # Check if status is a dropdown select
        selected_option = status_cell.locator("select option:checked")
        if selected_option.count() > 0:
            return selected_option.first.inner_text().strip()
        return status_cell.inner_text().strip()

    def delete_incident(self, name: str) -> bool:
        """Deletes the specified incident using the row trash action."""
        row = self.get_incident_row(name)
        if not row.is_visible():
            return False

        self.page.once("dialog", lambda dialog: dialog.accept())

        trash_link = row.locator("a[data-method='delete']:has(i.fa-trash), td.menu a:has(i.fa-trash)").first
        if trash_link.is_visible():
            trash_link.click()
            self.page.wait_for_load_state("domcontentloaded")
            self.page.wait_for_timeout(1000)
            return True
        return False
