import os
from typing import Generator
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright

from config.settings import settings
from core.api_client import APIClient
from core.ssh_client import SSHClient


@pytest.fixture(scope="session")
def app_settings():
    return settings


@pytest.fixture(scope="session")
def base_url() -> str:
    return settings.base_url


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Override playwright browser context to ignore self-signed certificates."""
    return {
        **browser_context_args,
        "ignore_https_errors": True,
        "viewport": {"width": 1440, "height": 900},
    }


@pytest.fixture(scope="function")
def ssh_client() -> Generator[SSHClient, None, None]:
    client = SSHClient(
        host=settings.target_host,
        username=settings.ssh_user,
        password=settings.ssh_password,
        port=settings.ssh_port,
        timeout=settings.ssh_timeout,
    )
    with client:
        yield client


@pytest.fixture(scope="function")
def api_client() -> Generator[APIClient, None, None]:
    client = APIClient(
        base_url=settings.base_url,
        verify_ssl=settings.verify_ssl,
        timeout=float(settings.default_timeout_ms / 1000.0),
    )
    with client:
        yield client


@pytest.fixture(scope="function")
def authenticated_api_client(api_client: APIClient) -> APIClient:
    success = api_client.login(
        username=settings.web_user,
        password=settings.web_password,
    )
    assert success, f"Failed to authenticate API client against {settings.base_url} with user {settings.web_user}"
    return api_client


@pytest.fixture(scope="function")
def require_redborder_sensors(ssh_client: SSHClient):
    """Ensures redborder-sensors is installed on the appliance; attempts installation if missing, or skips test."""
    installed = ssh_client.ensure_redborder_sensors_installed()
    if not installed:
        pytest.skip(
            "redborder-sensors is not installed on target appliance and 'dnf install -y redborder-sensors' failed. "
            "Skipping test requiring mock sensor sandboxing."
        )
    return True


@pytest.fixture(scope="function")
def sensors_page(page: Page, base_url: str):
    """Fixture that logs into Redborder and navigates to the Sensors tree page."""
    from core.pages.login_page import LoginPage
    from core.pages.sensors_page import SensorsPage

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


@pytest.fixture(scope="function")
def alarms_page(page: Page, base_url: str):
    """Fixture that logs into Redborder and navigates to the /alarms page."""
    from core.pages.login_page import LoginPage
    from core.pages.alarms_page import AlarmsPage

    login_page = LoginPage(page, base_url)
    login_page.navigate("/overview")
    if "login" in page.url:
        login_page.open()
        login_page.login(
            username=settings.web_user,
            password=settings.web_password,
        )
        page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

    p = AlarmsPage(page, base_url)
    p.open_alarms()
    return p


@pytest.fixture(scope="function")
def incidents_page(page: Page, base_url: str):
    """Fixture that logs into Redborder and navigates to the /incidents page."""
    from core.pages.login_page import LoginPage
    from core.pages.incidents_page import IncidentsPage

    login_page = LoginPage(page, base_url)
    login_page.navigate("/overview")
    if "login" in page.url:
        login_page.open()
        login_page.login(
            username=settings.web_user,
            password=settings.web_password,
        )
        page.wait_for_url(lambda u: "/overview" in u or "/dashboard" in u or "login" not in u, timeout=15000)

    p = IncidentsPage(page, base_url)
    p.open_incidents()
    return p


@pytest.fixture(scope="function")
def stable_domain_hierarchy(sensors_page, ssh_client: SSHClient):
    """Provides a stable, pre-provisioned, and Chef/Druid converged domain hierarchy
    (rb-test-sp -> rb-test-ns -> rb-test-org, plus destination rb-test-sp2).
    """
    sensors_page.open_tree()

    hierarchy = sensors_page.ensure_domain_hierarchy(
        sp_name="rb-test-sp",
        ns_name="rb-test-ns",
        org_name="rb-test-org",
        sp2_name="rb-test-sp2",
    )

    converged = ssh_client.converge_chef_and_wait_druid(iterations=1, druid_timeout=60, chef_timeout=120)
    assert converged, "Failed to converge Chef or reach healthy Druid state during pre-phase setup"
    try:
        yield hierarchy
    finally:
        # Preserve hierarchy for subsequent tests when running in testbed mode.
        # Full teardown is performed by --post-phase at the end of the test run.
        pass


@pytest.fixture(scope="function")
def stable_testbed(sensors_page, ssh_client: SSHClient):
    """Provides the full unified baseline testbed:
    - Pre-starts all mock sandboxes (Flow, Vault, SNMP, HTTP Webserver) so routes and bridges settle
    - Provisions domains, custom tabs, monitor categories, and all baseline sensors in Web UI
    - Runs Chef convergence to settle PostgreSQL and configure all collectors
    - Verifies Druid readiness
    - Preserves testbed for subsequent tests (clean up performed by --post-phase)
    """
    # 1. Start mock sandboxes on appliance
    ssh_client.start_all_baseline_mock_sandboxes()

    # 2. Pre-converge once to ensure pg_hba.conf is generated for virtual bridge br-10
    ssh_client.run_chef_client(timeout=180)
    import time
    time.sleep(5)

    # 3. Provision Web UI testbed
    testbed = sensors_page.ensure_full_testbed(
        sp_name="rb-test-sp",
        ns_name="rb-test-ns",
        org_name="rb-test-org",
        sp2_name="rb-test-sp2",
    )

    # 4. Final Chef convergence for newly created sensors and categories
    converged = ssh_client.converge_chef_and_wait_druid(iterations=1, druid_timeout=90, chef_timeout=180)
    assert converged, "Failed to converge Chef or reach healthy Druid state for stable testbed"
    time.sleep(5)

    try:
        yield testbed
    finally:
        # Reposition sensors under Organization if modified, preserving testbed for subsequent tests.
        # Full teardown is performed by --post-phase.
        pass



def pytest_collection_modifyitems(items):
    """Automatically enrich test items with Allure Epics, Features, and Titles if allure is available."""
    try:
        import allure
        from allure_commons.types import LabelType

        for item in items:
            fspath = str(item.fspath)
            # Epics and Features based on directory and file
            if "tests/backend" in fspath:
                item.add_marker(allure.epic("Backend Infrastructure"))
                item.add_marker(allure.feature("Systemd Services & System Health"))
            elif "tests/api" in fspath:
                item.add_marker(allure.epic("REST API"))
                item.add_marker(allure.feature("API Authentication & Health Endpoints"))
            elif "tests/web" in fspath:
                item.add_marker(allure.epic("Web Management UI"))
                if "lifecycle" in fspath:
                    item.add_marker(allure.feature("End-to-End Sensor Lifecycles"))
                elif "sensors" in fspath:
                    item.add_marker(allure.feature("Sensors & Monitoring"))
                elif "dashboard" in fspath:
                    item.add_marker(allure.feature("Dashboard & Navigation"))
                elif "auth" in fspath:
                    item.add_marker(allure.feature("Authentication & Login"))
                else:
                    item.add_marker(allure.feature("Web UI Testing"))
            elif "tests/test_ssh_client" in fspath or "tests/test_api_client" in fspath:
                item.add_marker(allure.epic("Test Automation Platform"))
                item.add_marker(allure.feature("Core Client Drivers"))
    except Exception:
        pass


# --- Screenshot & Reporting Helpers ---

def _capture_page_screenshot_extra(page: Page, title: str = "Screenshot", full_page: bool = True):
    """Encodes a page screenshot to base64, attaches to allure if active, and returns a pytest-html image extra."""
    import base64
    from pytest_html import extras as html_extras

    png_bytes = page.screenshot(full_page=full_page)

    # Attach to Allure report if allure is present
    try:
        import allure
        allure.attach(
            png_bytes,
            name=title,
            attachment_type=allure.attachment_type.PNG
        )
    except Exception:
        pass

    b64_str = base64.b64encode(png_bytes).decode("utf-8")
    return html_extras.image(b64_str, name=title)


@pytest.fixture
def attach_screenshot(request, extras):
    """Fixture that captures a screenshot of a Playwright page and embeds it in pytest-html and Allure reports."""
    def _capture(page: Page, title: str = "Screenshot", full_page: bool = True):
        try:
            extra = _capture_page_screenshot_extra(page, title=title, full_page=full_page)
            extras.append(extra)
        except Exception as e:
            import warnings
            warnings.warn(f"Failed to capture screenshot '{title}': {e}")

    return _capture


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Hook to automatically capture a screenshot on test failure for web tests."""
    outcome = yield
    report = outcome.get_result()

    if report.when in ("setup", "call") and report.failed:
        # Dynamically discover page instance from item.funcargs
        page = None
        funcargs = getattr(item, "funcargs", {})
        if "page" in funcargs and hasattr(funcargs["page"], "screenshot"):
            page = funcargs["page"]
        else:
            for obj in funcargs.values():
                if hasattr(obj, "page") and hasattr(obj.page, "screenshot"):
                    page = obj.page
                    break

        if page:
            try:
                extra = _capture_page_screenshot_extra(page, title=f"Failure Screenshot ({report.when})")
                report.extras = getattr(report, "extras", []) + [extra]
            except Exception as e:
                import warnings
                warnings.warn(f"Failed to capture failure screenshot for {item.nodeid}: {e}")


def pytest_runtest_logreport(report):
    """Trigger real-time live Allure report update as tests finish."""
    if report.when in ("call", "setup") and (report.passed or report.failed or report.skipped):
        try:
            from core.allure_live import trigger_live_allure_update
            trigger_live_allure_update()
        except Exception:
            pass


def pytest_html_report_title(report):
    report.title = "Redborder Automated Test Platform Report"


def pytest_html_results_summary(prefix, summary, postfix, session):
    """Injects modern dark theme styling, polished badges, and lightbox viewer for screenshots."""
    prefix.append("""
<style>
  :root {
    --bg-main: #090d16;
    --bg-surface: #101623;
    --bg-card: #161f30;
    --bg-card-hover: #1c273c;
    --bg-card-active: #23314b;
    --border-color: #243046;
    --border-light: #344360;
    --text-primary: #f0f6fc;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent-blue: #38bdf8;
    --accent-blue-glow: rgba(56, 189, 248, 0.15);
    --accent-green: #22c55e;
    --accent-green-bg: rgba(34, 197, 94, 0.12);
    --accent-red: #ef4444;
    --accent-red-bg: rgba(239, 68, 68, 0.12);
    --accent-yellow: #f59e0b;
    --accent-yellow-bg: rgba(245, 158, 11, 0.12);
    --accent-purple: #a855f7;
  }

  /* Custom Sleek Scrollbars */
  ::-webkit-scrollbar {
    width: 7px;
    height: 7px;
  }
  ::-webkit-scrollbar-track {
    background: #090d16;
  }
  ::-webkit-scrollbar-thumb {
    background: #25334c;
    border-radius: 4px;
  }
  ::-webkit-scrollbar-thumb:hover {
    background: var(--accent-blue);
  }

  body {
    background-color: var(--bg-main) !important;
    color: var(--text-primary) !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
    margin: 0 !important;
    padding: 24px 36px 60px 36px !important;
    font-size: 13.5px !important;
    line-height: 1.6 !important;
  }

  h1#title {
    font-size: 26px !important;
    font-weight: 700 !important;
    letter-spacing: -0.5px !important;
    color: #ffffff !important;
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
    margin: 0 0 4px 0 !important;
  }
  h1#title::before {
    content: "🛡️";
    font-size: 28px;
    filter: drop-shadow(0 0 10px rgba(56, 189, 248, 0.4));
  }

  p:not(.log) {
    color: var(--text-secondary) !important;
    margin: 4px 0 20px 0 !important;
    font-size: 13px !important;
  }

  a {
    color: var(--accent-blue) !important;
    text-decoration: none !important;
    transition: color 0.15s ease !important;
  }
  a:hover {
    color: #7dd3fc !important;
    text-decoration: underline !important;
  }

  /* Section Headers */
  h2 {
    font-size: 15px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.8px !important;
    color: var(--text-secondary) !important;
    margin: 24px 0 12px 0 !important;
  }

  /* Environment Table */
  #environment {
    width: 100% !important;
    background: var(--bg-surface) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 8px !important;
    overflow: hidden !important;
    margin-bottom: 24px !important;
  }
  #environment td {
    border-color: var(--border-color) !important;
    padding: 8px 14px !important;
    color: var(--text-secondary) !important;
  }
  #environment tr:nth-child(odd) {
    background: var(--bg-card) !important;
  }
  #environment td:first-child {
    font-weight: 600 !important;
    color: var(--text-primary) !important;
    width: 200px !important;
  }

  /* Controls & Action Bar */
  .summary {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 12px !important;
    padding: 18px 24px !important;
    margin-bottom: 24px !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25) !important;
  }
  .summary h2 {
    margin-top: 0 !important;
  }

  .controls {
    display: flex !important;
    flex-wrap: wrap !important;
    justify-content: space-between !important;
    align-items: center !important;
    gap: 16px !important;
    padding-top: 14px !important;
    border-top: 1px solid var(--border-color) !important;
  }

  .filters {
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
    flex-wrap: wrap !important;
  }
  .filters input[type="checkbox"] {
    accent-color: var(--accent-blue) !important;
    cursor: pointer !important;
    width: 15px !important;
    height: 15px !important;
  }
  .filters span {
    font-size: 13px !important;
    font-weight: 600 !important;
    padding: 3px 10px !important;
    border-radius: 6px !important;
  }
  .filters span.passed {
    color: var(--accent-green) !important;
    background: var(--accent-green-bg) !important;
  }
  .filters span.failed {
    color: var(--accent-red) !important;
    background: var(--accent-red-bg) !important;
  }

  /* Quick Search and Category Navigation Bar */
  .report-toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 18px;
    flex-wrap: wrap;
  }

  .report-search-box {
    flex: 1 1 280px;
    max-width: 450px;
    position: relative;
  }
  .report-search-box input {
    width: 100%;
    box-sizing: border-box;
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    padding: 9px 14px 9px 36px;
    border-radius: 8px;
    font-size: 13.5px;
    outline: none;
    transition: all 0.2s ease;
  }
  .report-search-box input:focus {
    border-color: var(--accent-blue);
    box-shadow: 0 0 0 3px var(--accent-blue-glow);
  }
  .report-search-box::before {
    content: "🔍";
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 13px;
    opacity: 0.6;
  }

  .category-pill {
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    padding: 6px 14px;
    border-radius: 20px;
    cursor: pointer;
    font-size: 12.5px;
    font-weight: 500;
    transition: all 0.15s ease;
    user-select: none;
  }
  .category-pill:hover {
    color: #ffffff;
    border-color: var(--border-light);
    background: var(--bg-card);
  }
  .category-pill.active {
    background: var(--accent-blue);
    color: #050b14;
    font-weight: 600;
    border-color: var(--accent-blue);
  }

  /* Results Table Layout */
  #results-table {
    width: 100% !important;
    border-collapse: separate !important;
    border-spacing: 0 !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 10px !important;
    overflow: hidden !important;
    background: var(--bg-surface) !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2) !important;
  }

  #results-table th {
    background: #141c2c !important;
    color: var(--text-secondary) !important;
    font-size: 12px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.6px !important;
    font-weight: 600 !important;
    padding: 12px 16px !important;
    border-bottom: 1px solid var(--border-color) !important;
    border-top: none !important;
    border-left: none !important;
    border-right: none !important;
  }

  #results-table td {
    padding: 12px 16px !important;
    border-top: 1px solid var(--border-color) !important;
    border-bottom: none !important;
    border-left: none !important;
    border-right: none !important;
    color: var(--text-primary) !important;
    font-size: 13.5px !important;
  }

  tr.collapsible:hover td {
    background-color: var(--bg-card-hover) !important;
  }

  /* Status Badges */
  .col-result {
    width: 120px !important;
    font-weight: 700 !important;
    letter-spacing: 0.3px !important;
  }
  .passed .col-result {
    color: var(--accent-green) !important;
  }
  .failed .col-result, .error .col-result {
    color: var(--accent-red) !important;
  }
  .skipped .col-result {
    color: var(--accent-yellow) !important;
  }

  /* Extras & Expanded Details */
  .extras-row td {
    background: #090e18 !important;
    padding: 18px 24px !important;
  }

  .logwrapper {
    background-color: #05080f !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 8px !important;
    padding: 14px 18px !important;
    font-family: ui-monospace, SFMono-Regular, "SF Mono", Consolas, monospace !important;
    font-size: 12px !important;
    line-height: 1.6 !important;
    color: #cbd5e1 !important;
    max-height: 380px !important;
    overflow-y: auto !important;
  }

  .logexpander {
    color: var(--accent-blue) !important;
    cursor: pointer !important;
    font-weight: 600 !important;
  }

  /* Media & Screenshot Viewports */
  div.media {
    border: 1px solid var(--border-color) !important;
    background: var(--bg-surface) !important;
    border-radius: 8px !important;
    padding: 10px !important;
    width: 360px !important;
    height: 250px !important;
    float: right !important;
    margin: 0 0 12px 16px !important;
    box-shadow: 0 4px 14px rgba(0,0,0,0.4) !important;
  }

  .media__name {
    color: var(--accent-blue) !important;
    font-weight: 600 !important;
    font-size: 12.5px !important;
    margin-bottom: 6px !important;
  }

  .media-container__viewport img {
    border-radius: 6px !important;
    border: 1px solid var(--border-color) !important;
    cursor: zoom-in !important;
    transition: transform 0.2s ease, border-color 0.2s ease !important;
  }
  .media-container__viewport img:hover {
    border-color: var(--accent-blue) !important;
    transform: scale(1.02) !important;
  }

  /* Fullscreen Lightbox Modal */
  .report-screenshot-modal {
    display: none;
    position: fixed;
    z-index: 999999;
    left: 0;
    top: 0;
    width: 100vw;
    height: 100vh;
    background-color: rgba(3, 7, 18, 0.94);
    backdrop-filter: blur(6px);
    justify-content: center;
    align-items: center;
    flex-direction: column;
    cursor: zoom-out;
  }
  .report-screenshot-modal.active {
    display: flex;
  }
  .report-screenshot-modal img {
    max-width: 95vw;
    max-height: 88vh;
    box-shadow: 0 10px 40px rgba(0,0,0,0.95);
    border-radius: 8px;
    border: 1px solid var(--border-light);
  }
  .report-screenshot-hint {
    color: var(--text-secondary);
    font-size: 12px;
    margin-top: 12px;
    background: rgba(16, 22, 35, 0.9);
    padding: 6px 16px;
    border-radius: 20px;
    border: 1px solid var(--border-color);
  }

  /* Screenshot Gallery Banner Ribbon */
  .screenshot-gallery-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    margin-bottom: 24px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
  }
  .gallery-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 20px;
    cursor: pointer;
    background: var(--bg-card);
    transition: background 0.15s ease;
    user-select: none;
  }
  .gallery-header:hover {
    background: var(--bg-card-hover);
  }
  .gallery-title {
    font-size: 13.5px;
    font-weight: 600;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .gallery-badge {
    background: var(--accent-blue-glow);
    color: var(--accent-blue);
    border: 1px solid rgba(56, 189, 248, 0.3);
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 11.5px;
    font-weight: 600;
  }
  .gallery-toggle-btn {
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
    padding: 4px 12px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .gallery-toggle-btn:hover {
    border-color: var(--accent-blue);
    color: var(--accent-blue);
  }
  .gallery-drawer {
    padding: 16px 20px;
    border-top: 1px solid var(--border-color);
    background: #070b12;
  }
  /* Horizontal banner carousel/ribbon */
  .gallery-banner-ribbon {
    display: flex;
    flex-direction: row;
    gap: 16px;
    overflow-x: auto;
    overflow-y: hidden;
    padding-bottom: 10px;
    scroll-behavior: smooth;
    -webkit-overflow-scrolling: touch;
  }
  .gallery-item {
    flex: 0 0 280px;
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    overflow: hidden;
    cursor: zoom-in;
    transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
    display: flex;
    flex-direction: column;
  }
  .gallery-item:hover {
    transform: translateY(-2px);
    border-color: var(--accent-blue);
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.4);
  }
  .gallery-thumb-container {
    width: 100%;
    height: 155px;
    background: #030509;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }
  .gallery-thumb-container img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }
  .gallery-item-info {
    padding: 10px 12px;
    border-top: 1px solid var(--border-color);
    background: var(--bg-card);
  }
  .gallery-item-name {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .gallery-item-source {
    font-size: 10.5px;
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-top: 2px;
  }
</style>

<!-- Top Toolbar for Live Search and Module Filters -->
<div class="report-toolbar">
  <div class="report-search-box">
    <input type="text" id="reportLiveSearch" placeholder="Search tests, files, or errors..." />
  </div>
  <div class="category-pill active" data-filter="all">All Tests</div>
  <div class="category-pill" data-filter="web">Web UI</div>
  <div class="category-pill" data-filter="lifecycle">Lifecycle (E2E)</div>
  <div class="category-pill" data-filter="api">API</div>
  <div class="category-pill" data-filter="backend">Backend Services</div>
  <div class="category-pill" data-filter="failed">Failed Only</div>
</div>

<!-- Screenshot Gallery Banner -->
<div class="screenshot-gallery-card" id="screenshotGalleryCard" style="display:none;">
  <div class="gallery-header" id="galleryToggleHeader">
    <div class="gallery-title">
      <span>📸 Screenshot Gallery</span>
      <span class="gallery-badge" id="galleryCountBadge">0 captures</span>
    </div>
    <button class="gallery-toggle-btn" id="galleryToggleBtn">Show Gallery</button>
  </div>
  <div class="gallery-drawer" id="galleryDrawer" style="display:none;">
    <div class="gallery-banner-ribbon" id="galleryGrid"></div>
  </div>
</div>

<div id="reportScreenshotModal" class="report-screenshot-modal" onclick="this.classList.remove('active')">
  <img id="reportScreenshotModalImg" src="" alt="Screenshot" />
  <div class="report-screenshot-hint">Click anywhere to close · Ctrl+Click thumbnail to open in new tab</div>
</div>

<script>
(function() {
  function initReportEnhancements() {
    // 1. Lightbox modal
    var modal = document.getElementById('reportScreenshotModal');
    var modalImg = document.getElementById('reportScreenshotModalImg');

    function openModalWithSrc(src, e) {
      if (!src) return;
      if (modal && modalImg) {
        modalImg.src = src;
        modal.classList.add('active');
      }
      if (e && (e.ctrlKey || e.metaKey)) {
        var win = window.open('', '_blank');
        if (win) {
          win.document.write('<!DOCTYPE html><html><head><title>Screenshot</title></head><body style="margin:0;background:#090d16;display:flex;justify-content:center;align-items:center;min-height:100vh;"><img src="' + src + '" style="max-width:100%;max-height:100vh;display:block;margin:auto;" /></body></html>');
          win.document.close();
        }
      }
    }

    document.addEventListener('click', function(e) {
      var target = e.target;
      if (target && target.tagName === 'IMG' && target.closest('.media-container__viewport')) {
        e.stopImmediatePropagation();
        e.preventDefault();
        openModalWithSrc(target.src, e);
      }
    }, true);

    // 2. Populate Screenshot Gallery Banner (ONLY tests with valid screenshots)
    var galleryCard = document.getElementById('screenshotGalleryCard');
    var galleryGrid = document.getElementById('galleryGrid');
    var galleryBadge = document.getElementById('galleryCountBadge');
    var galleryDrawer = document.getElementById('galleryDrawer');
    var galleryBtn = document.getElementById('galleryToggleBtn');
    var galleryHeader = document.getElementById('galleryToggleHeader');

    function buildGallery() {
      // Query all media container images that have an actual valid non-empty data/url src
      var mediaContainers = document.querySelectorAll('#results-table .media');
      if (!mediaContainers || mediaContainers.length === 0) return;

      var validCaptures = [];
      mediaContainers.forEach(function(mediaElem) {
        var img = mediaElem.querySelector('img');
        if (!img) return;
        var src = (img.getAttribute('src') || '').trim();
        // Skip template placeholders or empty images
        if (!src || src === '""' || src === "''") return;

        var nameElem = mediaElem.querySelector('.media__name');
        var nameText = nameElem ? nameElem.innerText.trim() : 'Test Snapshot';

        var testRow = mediaElem.closest('tbody.results-table-row') || mediaElem.closest('tbody');
        var testTitle = '';
        if (testRow) {
          var testLink = testRow.querySelector('td.col-name, td.col-testId, td.col-test');
          if (testLink) {
            testTitle = testLink.innerText.trim();
            // Shorten suite path for concise display
            var parts = testTitle.split('::');
            if (parts.length > 1) {
              testTitle = parts[parts.length - 1];
            }
          }
        }

        validCaptures.push({
          src: src,
          name: nameText,
          test: testTitle
        });
      });

      if (validCaptures.length === 0) {
        galleryCard.style.display = 'none';
        return;
      }

      galleryCard.style.display = 'block';
      galleryBadge.textContent = validCaptures.length + ' captures';
      galleryGrid.innerHTML = '';

      validCaptures.forEach(function(cap) {
        var item = document.createElement('div');
        item.className = 'gallery-item';
        item.innerHTML = '<div class="gallery-thumb-container"><img src="' + cap.src + '" alt="' + cap.name + '" /></div>' +
                         '<div class="gallery-item-info">' +
                         '  <div class="gallery-item-name" title="' + cap.name + '">' + cap.name + '</div>' +
                         (cap.test ? ('  <div class="gallery-item-source" title="' + cap.test + '">' + cap.test + '</div>') : '') +
                         '</div>';

        item.addEventListener('click', function(ev) {
          openModalWithSrc(cap.src, ev);
        });

        galleryGrid.appendChild(item);
      });
    }

    if (galleryHeader) {
      galleryHeader.addEventListener('click', function() {
        var isHidden = galleryDrawer.style.display === 'none';
        galleryDrawer.style.display = isHidden ? 'block' : 'none';
        galleryBtn.textContent = isHidden ? 'Hide Gallery' : 'Show Gallery';
      });
    }

    // Build gallery on startup
    buildGallery();

    // 3. Live Search, Category Filtering, and Dynamic Summary Adapting
    var searchInput = document.getElementById('reportLiveSearch');
    var pills = document.querySelectorAll('.category-pill');
    var runCountElem = document.querySelector('p.run-count');
    var initialRunCountText = runCountElem ? runCountElem.innerText : '';
    // Extract timing if present
    var durationMatch = initialRunCountText.match(/took\s+([^.]+)\./);
    var durationText = durationMatch ? (' took ' + durationMatch[1] + '.') : '';

    var totalTestsCount = 0;
    var allRows = document.querySelectorAll('#results-table tbody');
    if (allRows) {
      totalTestsCount = allRows.length;
    }

    function updateSummaryCount(visibleCount, passedCount, failedCount, skippedCount) {
      if (runCountElem) {
        if (visibleCount === totalTestsCount) {
          runCountElem.textContent = totalTestsCount + ' tests' + durationText;
        } else {
          runCountElem.innerHTML = '<strong>' + visibleCount + '</strong> of ' + totalTestsCount + ' tests filtered' + durationText;
        }
      }

      // Update pytest-html result filter counters if present
      var passedSpan = document.querySelector('.controls .filters span.passed');
      var failedSpan = document.querySelector('.controls .filters span.failed');
      var skippedSpan = document.querySelector('.controls .filters span.skipped');
      if (passedSpan) passedSpan.textContent = passedCount + ' Passed,';
      if (failedSpan) failedSpan.textContent = failedCount + ' Failed,';
      if (skippedSpan) skippedSpan.textContent = skippedCount + ' Skipped,';
    }

    function applyFilters() {
      var query = (searchInput ? searchInput.value.toLowerCase().trim() : '');
      var activePill = document.querySelector('.category-pill.active');
      var filterCat = activePill ? activePill.getAttribute('data-filter') : 'all';

      var rows = document.querySelectorAll('#results-table tbody');
      var visibleCount = 0;
      var passedCount = 0;
      var failedCount = 0;
      var skippedCount = 0;

      rows.forEach(function(row) {
        var tr = row.querySelector('tr.collapsible') || row.querySelector('tr');
        if (!tr) return;

        var text = row.innerText.toLowerCase();
        var matchesSearch = !query || text.indexOf(query) !== -1;

        var matchesCat = true;
        if (filterCat === 'web') {
          matchesCat = text.indexOf('tests/web/') !== -1 && text.indexOf('lifecycle') === -1;
        } else if (filterCat === 'lifecycle') {
          matchesCat = text.indexOf('lifecycle') !== -1;
        } else if (filterCat === 'api') {
          matchesCat = text.indexOf('tests/api/') !== -1 || text.indexOf('test_api_') !== -1;
        } else if (filterCat === 'backend') {
          matchesCat = text.indexOf('tests/backend/') !== -1 || text.indexOf('test_ssh_') !== -1;
        } else if (filterCat === 'failed') {
          matchesCat = tr.classList.contains('failed') || tr.classList.contains('error');
        }

        if (matchesSearch && matchesCat) {
          row.style.display = '';
          visibleCount++;
          if (tr.classList.contains('failed') || tr.classList.contains('error')) {
            failedCount++;
          } else if (tr.classList.contains('skipped')) {
            skippedCount++;
          } else {
            passedCount++;
          }
        } else {
          row.style.display = 'none';
        }
      });

      updateSummaryCount(visibleCount, passedCount, failedCount, skippedCount);
    }

    if (searchInput) {
      searchInput.addEventListener('input', applyFilters);
    }

    pills.forEach(function(pill) {
      pill.addEventListener('click', function() {
        pills.forEach(function(p) { p.classList.remove('active'); });
        pill.classList.add('active');
        applyFilters();
      });
    });

    // 4. Preserve filters across pytest-html redraws (e.g. clicking a test to expand details)
    var isApplyingFilters = false;
    var tableObserver = new MutationObserver(function() {
      if (isApplyingFilters) return;
      isApplyingFilters = true;
      requestAnimationFrame(function() {
        applyFilters();
        isApplyingFilters = false;
      });
    });

    var tableParent = document.getElementById('results-table') ? document.getElementById('results-table').parentElement : document.body;
    if (tableParent) {
      tableObserver.observe(tableParent, { childList: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initReportEnhancements);
  } else {
    initReportEnhancements();
  }
})();
</script>

""")
