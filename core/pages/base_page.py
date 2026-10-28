from typing import Optional
from playwright.sync_api import Page, Response, Locator


class BasePage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url.rstrip("/")

    def navigate(self, path: str = "/", retries: int = 3, delay: float = 2.0) -> Optional[Response]:
        import time
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        last_error = None
        for attempt in range(retries):
            try:
                response = self.page.goto(url, wait_until="domcontentloaded")
                if response is not None and response.status >= 500:
                    raise AssertionError(
                        f"Server error {response.status} when navigating to {url}. "
                        "The page returned an internal server error."
                    )
                # Check if Redborder rendered custom 500 error page
                if "Error: 500!" in self.page.content():
                    raise AssertionError(
                        f"Page rendered 'Error: 500!' when navigating to {url}. "
                        "The server encountered an internal error or misconfiguration."
                    )
                return response
            except AssertionError:
                raise
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    time.sleep(delay)
                    continue
                raise last_error

    @property
    def current_url(self) -> str:
        return self.page.url

    @property
    def title(self) -> str:
        return self.page.title()

    def wait_for_url_contains(self, fragment: str, timeout: int = 10000) -> None:
        self.page.wait_for_url(lambda u: fragment in u, timeout=timeout)

    def get_alert_text(self) -> Optional[str]:
        alert = self.page.locator(".alert, .alert-danger, .alert-warning, .notice, .flash-message").first
        if alert.is_visible():
            return alert.inner_text().strip()
        return None

    def take_screenshot(self, path: str) -> None:
        self.page.screenshot(path=path, full_page=True)

    def select_active_namespace(self, name: str = "All") -> bool:
        """Selects the active namespace in the top navigation bar and applies the selection.

        If name == 'All', selects all available namespaces.
        Otherwise, unchecks all and checks the namespace matching the given name.
        """
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        menu = self.page.locator("li.namespace-menu").first
        if not menu.is_visible():
            return False

        # Open dropdown if closed
        toggle = menu.locator("a.dropdown-toggle").first
        dropdown = menu.locator("ul.dropdown-menu").first
        if not dropdown.is_visible():
            toggle.click()
            self.page.wait_for_timeout(300)

        if name.lower() == "all":
            all_checkbox = menu.locator("#namespace_all").first
            if all_checkbox.is_visible() and not all_checkbox.is_checked():
                all_checkbox.click()
            # Guarantee all namespace checkboxes are checked and change events fired
            self.page.evaluate("""() => {
                $('.namespace-menu .dropdown-menu li input[type="checkbox"]').prop('checked', true).trigger('change');
                $('#namespace_all').prop('checked', true).trigger('change');
            }""")
        else:
            # Uncheck all first
            self.page.evaluate("""() => {
                $('.namespace-menu .dropdown-menu li input[type="checkbox"]').prop('checked', false).trigger('change');
            }""")
            # Check target namespace by data-namespace-name or label text
            target_chk = menu.locator(
                f"li.namespace[data-namespace-name='{name}'] input[type='checkbox'], "
                f"li.namespace[data-namespace-name*='{name}'] input[type='checkbox'], "
                f"li.namespace:has-text('{name}') input[type='checkbox']"
            ).first
            if not target_chk.is_visible():
                return False
            if not target_chk.is_checked():
                target_chk.click()

        apply_btn = menu.locator("a.apply-namespaces").first
        if not apply_btn.is_visible():
            return False

        try:
            with self.page.expect_response(
                lambda r: "/namespaces" in r.url and r.status == 200,
                timeout=10000,
            ):
                apply_btn.click()
        except PlaywrightTimeoutError:
            # Request may have completed or was cached; verify DOM reload
            pass

        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_timeout(1000)
        return True

    def get_active_namespace(self) -> str:
        """Returns the currently active namespace text displayed in the top bar."""
        menu = self.page.locator("li.namespace-menu a.dropdown-toggle").first
        if not menu.is_visible():
            try:
                menu.wait_for(state="visible", timeout=3000)
            except Exception:
                return ""
        return menu.inner_text().strip()

