import json
from typing import Any, Dict, List, Optional
from playwright.sync_api import Page, Locator

from config.settings import settings
from core.pages.base_page import BasePage


class MonitorPage(BasePage):
    """Page Object Model for Redborder's Monitor module (/monitor):
    - Subview navigation (Hardware, Historicals, Indexing, Segments, Kafka, PSQL Nodes, HTTP Agents, Diagram, Tops).
    - Monitor categories / tabs selection and activation.
    - Active filter management (apply, clear, check).
    - Saved filter lifecycle (save via modal /monitor/search, list on /saved/monitor_filters, reuse, delete).
    - Chart type switching (stacked, area, line, bars, sbars).
    """

    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)

    # -------------------------------------------------------------
    # Locators
    # -------------------------------------------------------------

    @property
    def monitor_article(self) -> Locator:
        return self.page.locator("article#monitor")

    @property
    def tabs_container(self) -> Locator:
        return self.page.locator("div.tabbable ul.nav-tabs.monitor")

    @property
    def filters_dropdown(self) -> Locator:
        return self.page.locator("li[data-step='1'] a.dropdown-toggle, li.filter-red a.dropdown-toggle, a.dropdown-toggle:has-text('Filters')").first

    @property
    def actions_dropdown(self) -> Locator:
        return self.page.locator("li[data-step='2'] a.dropdown-toggle, li.actions a.dropdown-toggle").first

    @property
    def chart_types_dropdown(self) -> Locator:
        return self.page.locator("li#chart_types a.dropdown-toggle").first

    @property
    def granularities_dropdown(self) -> Locator:
        return self.page.locator("li#granularities a.dropdown-toggle").first

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
    # Navigation & Views
    # -------------------------------------------------------------

    def open_monitor(self) -> None:
        """Navigates to the main Monitor dashboard (/monitor)."""
        self.navigate("/monitor")
        self.wait_for_loading_complete()

    def open_subview(self, subview: str) -> None:
        """Navigates to a specific Monitor subview."""
        subviews = {
            "tops": "/monitor",
            "hardware": "/monitor/hardware",
            "historicals": "/monitor/historicals",
            "indexing": "/monitor/indexing",
            "segments": "/monitor/segments",
            "psql_nodes": "/monitor/psql_nodes",
            "kafka": "/monitor/kafka",
            "http_agents": "/monitor/http_agents",
            "diagram": "/monitor/diagram",
            "indexed_data": "/monitor/indexed_data",
            "druid_query_logging": "/monitor/druid_query_logging",
            "zookeeper_nodes": "/monitor/zookeeper_nodes",
        }
        target_path = subviews.get(subview.lower(), f"/monitor/{subview}")
        self.navigate(target_path)
        self.wait_for_loading_complete()

    def switch_view(self, view_name: str) -> None:
        """Switches between Monitor views (tops, hardware, historicals, kafka, etc.)."""
        self.open_subview(view_name)

    # -------------------------------------------------------------
    # Tab Navigation
    # -------------------------------------------------------------

    def select_tab(self, tab_key: str) -> None:
        """Selects and activates a specific category tab on /monitor."""
        # 1. Check if tab link exists in active tabs bar
        tab_link = self.page.locator(f"ul.nav-tabs.monitor li a[href='#tab_{tab_key}']").first
        if not tab_link.is_visible():
            # Try activating it from Add Tab dropdown
            add_tab_btn = self.page.locator("a.dropdown-toggle:has(i.fa-tags), li[data-step='6'] > a.dropdown-toggle").first
            if add_tab_btn.is_visible():
                add_tab_btn.click()
                self.page.wait_for_timeout(300)
                tab_opt = self.page.locator(f"#tops a[id='{tab_key}'], #tops a[href*='add_tab/{tab_key}']").first
                if tab_opt.is_visible():
                    tab_opt.click()
                    self.wait_for_loading_complete()
                    self.page.wait_for_timeout(800)

        # 2. Re-locate tab link and click
        tab_link = self.page.locator(f"ul.nav-tabs.monitor li a[href='#tab_{tab_key}']").first
        if tab_link.is_visible():
            # If tab requires background AJAX load, wait for load="true"
            try:
                self.page.wait_for_function(
                    f"() => {{ const el = document.querySelector('ul.nav-tabs.monitor li#{tab_key}'); return !el || el.getAttribute('load') === 'true'; }}",
                    timeout=5000,
                )
            except Exception:
                pass

            tab_link.click()
            self.wait_for_loading_complete()
            try:
                self.page.wait_for_selector(f"div#tab_{tab_key}.active", timeout=8000)
            except Exception:
                pass
            self.page.wait_for_timeout(500)
            return

        # 3. Fallback: navigate with ?category=<tab_key>
        self.navigate(f"/monitor?category={tab_key}")
        self.wait_for_loading_complete()
        self.page.wait_for_timeout(500)

    # -------------------------------------------------------------
    # Chart Types
    # -------------------------------------------------------------

    def get_active_chart_type(self) -> str:
        """Returns the current active chart type label from the UI."""
        toggle = self.chart_types_dropdown
        if toggle.is_visible():
            return toggle.inner_text().strip()
        return ""

    def set_chart_type(self, chart_type: str) -> None:
        """Changes the active chart type (stacked, area, line, bars, sbars)."""
        toggle = self.chart_types_dropdown
        if toggle.is_visible():
            toggle.click()
            self.page.wait_for_timeout(300)
            item = self.page.locator(f"li#chart_types ul.dropdown-menu a[href*='chart_type={chart_type.lower()}']").first
            if item.is_visible():
                item.click()
                self.wait_for_loading_complete()
                self.page.wait_for_timeout(500)
                return

        # Fallback via PATCH
        csrf = self.get_csrf_token()
        script = f"""
            async () => {{
                await fetch('/monitor/change_chart_type/index?chart_type=' + encodeURIComponent({json.dumps(chart_type.lower())}), {{
                    method: 'PATCH',
                    headers: {{
                        'X-CSRF-Token': {json.dumps(csrf)}
                    }}
                }});
            }}
        """
        self.page.evaluate(script)
        current_path = self.page.evaluate("() => window.location.pathname")
        self.navigate(current_path)
        self.wait_for_loading_complete()

    # -------------------------------------------------------------
    # Active Filtering
    # -------------------------------------------------------------

    def apply_filter(self, dimension: str, value: str, operator: str = "is") -> None:
        """Applies a filter via the Redborder filters controller endpoint."""
        csrf = self.get_csrf_token()
        # Evaluate fetch PATCH in browser session and await completion
        script = f"""
            async () => {{
                await fetch('/filters/monitor/' + encodeURIComponent({json.dumps(dimension)}) + '/add', {{
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
        current_path = self.page.evaluate("() => window.location.pathname")
        self.navigate(current_path)
        self.wait_for_loading_complete()

    def clear_all_filters(self) -> None:
        """Clears all active filters via the Web UI dropdown."""
        filters_dropdown = self.filters_dropdown
        if filters_dropdown.is_visible():
            try:
                filters_dropdown.click()
                self.page.wait_for_timeout(300)
                all_remove_btn = self.page.locator(
                    "ul.dropdown-menu a[href*='/filters/monitor/all/del'], ul.dropdown-menu a[href*='/all/del'], ul.dropdown-menu li:has-text('All') a:has(i.fa-remove)"
                ).first
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
                await fetch('/filters/monitor/all/del', {{
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
        filters_dropdown = self.page.locator("li[data-step='1'] a.dropdown-toggle, li.filter-red a.dropdown-toggle")
        if filters_dropdown.count() > 0:
            content = self.page.content()
            if text_or_value in content and "filter-value" in content:
                return True
        return False

    # -------------------------------------------------------------
    # Saved Filters Management (Save, Load, Reuse, Delete)
    # -------------------------------------------------------------

    def open_saved_filters_page(self) -> None:
        """Navigates directly to the Saved Monitor Filters list page (/saved/monitor_filters)."""
        self.navigate("/saved/monitor_filters")
        self.wait_for_loading_complete()

    def save_current_filter(
        self,
        title: str,
        column: Optional[str] = None,
        value: Optional[str] = None,
        operator: str = "is",
        public: bool = True,
        items: Optional[List[Dict[str, Any]]] = None,
        expected_count: int = 1,
        is_public: Optional[bool] = None,
    ) -> Optional[int]:
        """Saves current monitor filters via the Web UI save modal.
        Navigates to /monitor/search (Advanced Filter), opens the 'Save' modal,
        fills the title and public option, and clicks 'Save Filter'.
        """
        if is_public is not None:
            public = is_public
        csrf = self.get_csrf_token()

        # 1. UI Flow: open Advanced Search page and click Save Filter modal
        try:
            self.navigate("/monitor/search")
            self.page.wait_for_load_state("domcontentloaded")

            # Wait for search rule boxes to be constructed in DOM
            req_count = len(items) if items else expected_count
            try:
                self.page.wait_for_function(
                    f"() => typeof rule !== 'undefined' && typeof rule.pack === 'function' && Object.keys(rule.pack().items || {{}}).length >= {req_count}",
                    timeout=8000,
                )
            except Exception:
                pass

            # Click '+ Save' in title actions
            save_link = self.page.locator("a[data-target='#new_saved_monitor_filter_modal'], a[href*='new_saved_monitor_filter']").first
            if save_link.is_visible():
                save_link.click()
                modal = self.page.locator("#new_saved_monitor_filter_modal").first
                modal.wait_for(state="visible", timeout=settings.default_timeout_ms)

                title_input = modal.locator("input#saved_monitor_filter_title, input[name*='title']").first
                title_input.wait_for(state="visible", timeout=settings.default_timeout_ms)
                title_input.fill(title)

                public_checkbox = modal.locator("input#saved_monitor_filter_public, input[name*='public']").first
                if public_checkbox.is_visible():
                    if public and not public_checkbox.is_checked():
                        public_checkbox.check()
                    elif not public and public_checkbox.is_checked():
                        public_checkbox.uncheck()

                save_btn = modal.locator("button.new-saved-search-record").first
                # Intercept the POST response to get the saved filter ID
                with self.page.expect_response(
                    lambda r: "/saved_monitor_filters/create" in r.url and r.request.method == "POST",
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
        res = self.page.request.post(
            f"{self.base_url}/saved_monitor_filters/create",
            data=payload,
            headers={
                "X-CSRF-Token": csrf,
                "Content-Type": "application/json"
            }
        )
        if res.ok:
            data = res.json()
            if isinstance(data, dict) and "id" in data:
                return int(data["id"])
        return None

    def apply_saved_filter(self, filter_id: int, filter_title: Optional[str] = None) -> None:
        """Applies a previously saved filter from the filters dropdown submenu or directly via PATCH."""
        # 1. UI Flow: Hover over 'Saved Filters' or 'Public Filters' submenu in Filters dropdown
        filters_dropdown = self.filters_dropdown
        if filters_dropdown.is_visible() and filter_title:
            try:
                filters_dropdown.click()
                self.page.wait_for_timeout(300)
                saved_submenu = self.page.locator("li.dropdown-submenu:has(a:has-text('Saved filters')), li.dropdown-submenu:has(a:has-text('Public filters'))").first
                if saved_submenu.is_visible():
                    saved_submenu.hover()
                    self.page.wait_for_timeout(300)
                    filter_link = self.page.locator(f"a:has-text('{filter_title}'), a[href*='/saved_monitor_filter/{filter_id}/add']").first
                    if filter_link.is_visible():
                        filter_link.click()
                        self.wait_for_loading_complete()
                        return
            except Exception as e:
                print(f"Warning: UI apply saved filter failed ({e}), falling back...")

        # 2. Resilient Fallback: Evaluate fetch PATCH directly
        csrf = self.get_csrf_token()
        script = f"""
            async () => {{
                await fetch('/saved_monitor_filter/{filter_id}/add', {{
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

    def delete_saved_filter(self, filter_id: int) -> bool:
        """Deletes a saved filter from /saved/monitor_filters."""
        self.open_saved_filters_page()
        row = self.page.locator(f"tr#saved_monitor_filter_{filter_id}")
        if not row.is_visible():
            row = self.page.locator(f"tr:has(a[href*='/saved_monitor_filters/{filter_id}']), tr:has(a[href*='/saved/monitor_filters/{filter_id}'])").first

        if row.is_visible():
            delete_link = row.locator("a[data-method='delete'], a:has(i.fa-trash)").first
            if delete_link.is_visible():
                self.page.once("dialog", lambda dialog: dialog.accept())
                delete_link.click()
                self.wait_for_loading_complete()
                self.page.wait_for_timeout(1000)
                return True
        return False
