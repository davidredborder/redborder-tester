import json
import re
from typing import Any, Dict, List, Optional
from playwright.sync_api import Locator, Page
from core.pages.base_page import BasePage
from config.settings import settings


class TrafficPage(BasePage):
    """Page object for Redborder Traffic Module (/flow)."""

    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)

    def open_tops(self) -> None:
        """Navigates to /flow/tops and waits for the view to stabilize."""
        self.navigate("/flow/tops")
        self.wait_for_loading_complete()

    def open_raw(self) -> None:
        """Navigates to /flow (raw events) and waits for table/list."""
        self.navigate("/flow")
        self.wait_for_loading_complete()

    def open_comparative(self) -> None:
        """Navigates to /flow/comparative and waits for comparative elements."""
        self.navigate("/flow/comparative")
        self.wait_for_loading_complete()

    def open_cardinality(self) -> None:
        """Navigates to /flow/cardinality (unique view) and waits for content."""
        self.navigate("/flow/cardinality")
        self.wait_for_loading_complete()

    def wait_for_loading_complete(self, timeout: int = 15000) -> None:
        """Waits for any blockUI overlay or spinner to disappear."""
        try:
            self.page.locator(".blockUI.blockOverlay").wait_for(state="hidden", timeout=timeout)
        except Exception:
            pass
        self.page.wait_for_load_state("domcontentloaded")

    def get_csrf_token(self) -> str:
        """Extracts the session CSRF token from the DOM."""
        meta = self.page.locator("meta[name='csrf-token']")
        if meta.count() > 0:
            return meta.get_attribute("content") or ""
        return ""

    # -------------------------------------------------------------
    # Analysis View Switching (Tops, Raw, Compare, Unique)
    # -------------------------------------------------------------

    def switch_view(self, view_name: str) -> None:
        """Switches the traffic analysis view type.
        
        Args:
            view_name: 'tops', 'raw', 'compare', or 'unique'
        """
        target = view_name.strip().lower()
        route_map = {
            "tops": "/flow/tops",
            "raw": "/flow",
            "compare": "/flow/comparative",
            "unique": "/flow/cardinality",
        }
        if target in route_map:
            # First try clicking through UI menu if visible
            actions_toggle = self.page.locator("li.actions.dropdown > a.dropdown-toggle")
            if actions_toggle.is_visible():
                try:
                    actions_toggle.click()
                    self.page.wait_for_timeout(300)
                    menu_link = self.page.locator(f"li.actions ul.dropdown-menu a[href*='{route_map[target]}']").first
                    if menu_link.is_visible():
                        menu_link.click()
                        self.wait_for_loading_complete()
                        return
                except Exception:
                    pass
            # Fallback to direct navigation
            self.navigate(route_map[target])
            self.wait_for_loading_complete()
        else:
            raise ValueError(f"Unknown traffic view: {view_name}. Options: tops, raw, compare, unique")

    def select_tab(self, tab_id: str) -> None:
        """Selects an active tab in /flow/tops (e.g. 'lan_ip', 'wan_ip', 'sensor_name')."""
        tab_key = tab_id.strip().lower()
        li_locator = self.page.locator(f"ul.nav-tabs li#{tab_key}")
        if li_locator.count() > 0:
            # The Redborder UI loads background tabs asynchronously via AJAX,
            # setting attr load='true' and data-toggle='tab' once ready.
            # Wait for load=true (or max 10s), then click the tab link.
            try:
                self.page.wait_for_selector(f"ul.nav-tabs li#{tab_key}[load='true']", timeout=10000)
            except Exception:
                pass
            tab_link = self.page.locator(f"ul.nav-tabs li#{tab_key} > a:not(.close)").first
            tab_link.click()
            self.wait_for_loading_complete()
            # Wait for tab-pane to become active
            try:
                self.page.wait_for_selector(f"div#tab_{tab_key}.active", timeout=8000)
            except Exception:
                pass
            self.page.wait_for_timeout(600)
            return

        # If tab is not in DOM, navigate with ?tab=<tab_key>
        current_path = self.page.evaluate("() => window.location.pathname")
        self.navigate(f"{current_path}?tab={tab_key}")
        self.wait_for_loading_complete()
        self.page.wait_for_timeout(600)

    # -------------------------------------------------------------
    # Metric / Aggregation Switching (Bytes, bps, Packets, pps)
    # -------------------------------------------------------------

    def set_metric(self, metric: str) -> None:
        """Switches the traffic aggregation metric unit.
        
        Args:
            metric: 'bytes', 'bps', 'pkts' (or 'packets'), 'pps' (or 'packets/sec')
        """
        metric_norm = metric.strip().lower()
        metric_aliases = {
            "bytes": "bytes",
            "b": "bytes",
            "bps": "bps",
            "pkts": "pkts",
            "packets": "pkts",
            "pps": "pps",
            "packets/sec": "pps",
        }
        val = metric_aliases.get(metric_norm, metric_norm)

        # In Redborder commons, replacing the active aggregation is done via
        # ?aggregation=<val>&aggregation_action=replace
        current_path = self.page.evaluate("() => window.location.pathname")
        self.navigate(f"{current_path}?aggregation={val}&aggregation_action=replace")
        self.wait_for_loading_complete()
        self.page.wait_for_timeout(600)

    def get_active_metric(self) -> str:
        """Returns the currently active metric/aggregation name displayed in the navbar."""
        agg_toggle = self.page.locator("li#aggregations > a.dropdown-toggle")
        if agg_toggle.is_visible():
            return agg_toggle.inner_text().strip()
        return ""

    # -------------------------------------------------------------
    # Active Filtering
    # -------------------------------------------------------------

    def apply_filter(self, dimension: str, value: str) -> None:
        """Applies a filter via the Redborder filters controller endpoint."""
        csrf = self.get_csrf_token()
        # Evaluate fetch PATCH in browser session and await completion
        script = f"""
            async () => {{
                await fetch('/filters/flow/' + encodeURIComponent({json.dumps(dimension)}) + '/add', {{
                    method: 'PATCH',
                    headers: {{
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRF-Token': {json.dumps(csrf)}
                    }},
                    body: new URLSearchParams({{
                        'authenticity_token': {json.dumps(csrf)},
                        'values[]': {json.dumps(value)}
                    }})
                }});
            }}
        """
        self.page.evaluate(script)
        # Reload / navigate to update view
        current_path = self.page.evaluate("() => window.location.pathname")
        self.navigate(current_path)
        self.wait_for_loading_complete()

    def clear_all_filters(self) -> None:
        """Clears all active filters via the Web UI dropdown."""
        # 1. UI Flow: Click the Filters dropdown badge in the toolbar
        filters_dropdown = self.page.locator("li[data-step='1'] a.dropdown-toggle, li.filter-red a.dropdown-toggle, a.dropdown-toggle:has-text('Filters')").first
        if filters_dropdown.is_visible():
            try:
                filters_dropdown.click()
                self.page.wait_for_timeout(300)
                # Target the 'All Filters' remove link in the dropdown menu
                all_remove_btn = self.page.locator("ul.dropdown-menu a[href*='/all/del'], ul.dropdown-menu li:has-text('All') a:has(i.fa-remove)").first
                if all_remove_btn.is_visible():
                    all_remove_btn.click()
                    self.wait_for_loading_complete()
                    return
            except Exception as e:
                print(f"Warning: UI clear filters failed ({e}), falling back...")

        # Fallback to direct navigation / request if dropdown is closed
        csrf = self.get_csrf_token()
        script = f"""
            async () => {{
                await fetch('/filters/flow/all/del', {{
                    method: 'PATCH',
                    headers: {{
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRF-Token': {json.dumps(csrf)}
                    }},
                    body: new URLSearchParams({{
                        'authenticity_token': {json.dumps(csrf)}
                    }})
                }});
            }}
        """
        self.page.evaluate(script)
        current_path = self.page.evaluate("() => window.location.pathname")
        self.navigate(current_path)
        self.wait_for_loading_complete()


    def has_filter_applied(self, text_or_value: str) -> bool:
        """Checks if a given filter text/value is currently active in the filters dropdown badge/menu."""
        # 1. Check filter button badge / dropdown
        filters_dropdown = self.page.locator("li[data-step='1'] a.dropdown-toggle, li.filter-red a.dropdown-toggle")
        if filters_dropdown.count() > 0:
            badge_text = filters_dropdown.first.inner_text()
            # If active, badge usually shows 'Filters 1' or 'Filters 2'
            content = self.page.content()
            if text_or_value in content and "filter-value" in content:
                return True
        return False

    # -------------------------------------------------------------
    # Saved Filters Management (Save, Load, Reuse, Delete)
    # -------------------------------------------------------------

    def save_current_filter(
        self,
        title: str,
        column: Optional[str] = None,
        value: Optional[str] = None,
        operator: str = "is",
        public: bool = True,
        items: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[int]:
        """Saves current flow filters via the Web UI save modal.
        Navigates to /flow/search (Advanced Filter), opens the 'Save' modal,
        fills the title and public option, and clicks 'Save Filter'.
        Redborder's frontend rule.pack() automatically includes ALL active filters.
        """
        csrf = self.get_csrf_token()

        # 1. UI Flow: open Advanced Search page and click Save Filter modal
        try:
            self.navigate("/flow/search")
            self.page.wait_for_load_state("domcontentloaded")

            # Wait for search rule boxes to be constructed in DOM
            expected_count = len(items) if items else 1
            try:
                self.page.wait_for_function(
                    f"() => typeof rule !== 'undefined' && typeof rule.pack === 'function' && Object.keys(rule.pack().items || {{}}).length >= {expected_count}",
                    timeout=8000,
                )
            except Exception:
                pass

            # Click '+ Save' in title actions
            save_link = self.page.locator("a[data-target='#new_saved_traffic_filter_modal'], a[href*='new_saved_traffic_filter']").first
            if save_link.is_visible():
                save_link.click()
                modal = self.page.locator("#new_saved_traffic_filter_modal").first
                modal.wait_for(state="visible", timeout=settings.default_timeout_ms)

                title_input = modal.locator("input#saved_traffic_filter_title")
                title_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
                title_input.fill(title)

                public_checkbox = modal.locator("input#saved_traffic_filter_public")
                if public_checkbox.is_visible():
                    if public and not public_checkbox.is_checked():
                        public_checkbox.check()
                    elif not public and public_checkbox.is_checked():
                        public_checkbox.uncheck()

                save_btn = modal.locator("button.new-saved-search-record").first
                # Intercept the POST response to get the saved filter ID
                with self.page.expect_response(
                    lambda r: "/saved_flow_filters/create" in r.url and r.request.method == "POST",
                    timeout=10000,
                ) as resp_info:
                    save_btn.click()

                resp = resp_info.value
                if resp.status in (200, 201):
                    data = resp.json()
                    if isinstance(data, dict) and "id" in data:
                        return int(data["id"])
        except Exception as e:
            print(f"Warning: UI save modal failed ({e}), falling back to API payload...")

        # 2. Resilient Fallback: If UI save modal encountered an issue, build items dict
        filter_items = {}
        if items:
            for idx, item in enumerate(items):
                filter_items[str(idx)] = {
                    "enabled": True,
                    "column": item.get("column", "sensor_name"),
                    "operator": item.get("operator", "is"),
                    "value": item.get("value", ""),
                }
        elif column and value:
            filter_items["0"] = {
                "enabled": True,
                "column": column,
                "operator": operator,
                "value": value,
            }

        payload = {
            "authenticity_token": csrf,
            "filter": {
                "title": title,
                "public": public,
                "filter": {
                    "items": filter_items
                }
            }
        }
        payload_json = json.dumps(payload)
        script = f"""
            async () => {{
                const res = await fetch('/saved_flow_filters/create', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': {json.dumps(csrf)}
                    }},
                    body: JSON.stringify({payload_json})
                }});
                return await res.json();
            }}
        """
        res = self.page.evaluate(script)
        if isinstance(res, dict) and "id" in res:
            return int(res["id"])
        return None

    def apply_saved_filter(self, filter_id: int, filter_title: Optional[str] = None) -> None:
        """Applies an existing saved filter by clicking it in the Filters dropdown in the Web UI."""
        # 1. UI Flow: Click the Filters dropdown badge in the toolbar
        filters_dropdown = self.page.locator("li[data-step='1'] a.dropdown-toggle, li.filter-red a.dropdown-toggle, a.dropdown-toggle:has-text('Filters')").first
        if filters_dropdown.is_visible():
            try:
                filters_dropdown.click()
                self.page.wait_for_timeout(400)

                # If inside a submenu (Saved Filters or Public filters), hover first
                submenu = self.page.locator("ul.dropdown-menu li.dropdown-submenu:has-text('Saved Filters'), ul.dropdown-menu li.dropdown-submenu:has-text('Public filters')").first
                if submenu.is_visible():
                    submenu.hover()
                    self.page.wait_for_timeout(200)

                # Look for link matching filter_id or title
                saved_link = self.page.locator(f"ul.dropdown-menu a[href*='/saved_flow_filter/{filter_id}/add']").first
                if not saved_link.is_visible() and filter_title:
                    saved_link = self.page.locator(f"ul.dropdown-menu a:has-text('{filter_title}')").first

                if saved_link.count() > 0:
                    if not saved_link.first.is_visible():
                        saved_link.first.dispatch_event("click")
                    else:
                        saved_link.first.click()
                    self.wait_for_loading_complete()
                    return
            except Exception as e:
                print(f"Warning: UI apply saved filter failed ({e}), falling back...")

        # Fallback to direct request
        csrf = self.get_csrf_token()
        script = f"""
            async () => {{
                await fetch('/saved_flow_filter/{filter_id}/add', {{
                    method: 'PATCH',
                    headers: {{
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRF-Token': {json.dumps(csrf)}
                    }},
                    body: new URLSearchParams({{
                        'authenticity_token': {json.dumps(csrf)}
                    }})
                }});
            }}
        """
        self.page.evaluate(script)
        current_path = self.page.evaluate("() => window.location.pathname")
        self.navigate(current_path)
        self.wait_for_loading_complete()

    def delete_saved_filter(self, filter_id: int) -> None:
        """Deletes a saved filter record by navigating to /saved/flow_filters and clicking its delete trash button."""
        # 1. UI Flow: navigate to saved filters page and click delete button on row
        try:
            self.open_saved_filters_page()
            row = self.page.locator(f"tr#saved_traffic_filter_{filter_id}, tr[data-id='{filter_id}']").first
            if row.is_visible():
                delete_btn = row.locator("a i.fa-trash, a[data-method='delete']").first
                if delete_btn.is_visible():
                    self.page.once("dialog", lambda dialog: dialog.accept())
                    delete_btn.click()
                    self.page.wait_for_timeout(1000)
                    return
        except Exception as e:
            print(f"Warning: UI delete saved filter failed ({e}), falling back...")

        # Fallback to direct DELETE
        csrf = self.get_csrf_token()
        script = f"""
            async () => {{
                await fetch('/saved_flow_filters/{filter_id}', {{
                    method: 'DELETE',
                    headers: {{
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRF-Token': {json.dumps(csrf)}
                    }},
                    body: new URLSearchParams({{
                        'authenticity_token': {json.dumps(csrf)}
                    }})
                }});
            }}
        """
        self.page.evaluate(script)

    def open_saved_filters_page(self) -> None:
        """Navigates to /saved/flow_filters."""
        self.navigate("/saved/flow_filters")
        self.wait_for_loading_complete()


    # -------------------------------------------------------------
    # DOM Queries
    # -------------------------------------------------------------

    @property
    def tops_table(self) -> Locator:
        return self.page.locator("table.table-events:visible, .tab-table:visible table, table.table-striped:visible").first

    @property
    def raw_thumbnails(self) -> Locator:
        return self.page.locator("ul.thumbnails li.raw, table.table-events")

    @property
    def comparative_container(self) -> Locator:
        return self.page.locator("#comparative, article#flow, div.tab-pane.active")

    @property
    def cardinality_container(self) -> Locator:
        return self.page.locator("#cardinality, article#flow, div.tab-pane.active")
