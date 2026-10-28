#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

REPORT_DIR="${SCRIPT_DIR}/reports"

# Quick exit for clean or help before environment checks
if [ $# -gt 0 ]; then
    case "$1" in
        clean|--clean)
            echo " Cleaning all reports, Allure results, and test artifacts..."
            rm -rf "${REPORT_DIR}"/*
            echo " Reports directory cleaned."
            exit 0
            ;;
        -h|--help)
            # Usage will be displayed below after function definition
            ;;
    esac
fi

# Add common user binary paths to PATH if present
for p in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    if [ -d "$p" ] && [[ ":$PATH:" != *":$p:"* ]]; then
        export PATH="$p:$PATH"
    fi
done

# Self-heal incompatible .venv (e.g. copied from a different Linux distro with incompatible shared libs)
if [ -f "${SCRIPT_DIR}/.venv/bin/python" ] && ! "${SCRIPT_DIR}/.venv/bin/python" -c "import sys" >/dev/null 2>&1; then
    echo "=========================================================="
    echo " [!] Detected an incompatible .venv/ (copied from another OS or missing libraries)."
    echo "     Removing stale .venv/ so it can be cleanly recreated for this machine..."
    rm -rf "${SCRIPT_DIR}/.venv"
    echo "=========================================================="
fi

# Check for uv and resolve Python & Pytest runners
if command -v uv >/dev/null 2>&1; then
    PY_CMD="uv run python"
    PYTEST_CMD="uv run pytest"
else
    echo "=========================================================="
    echo " [!] 'uv' is not installed or not found in your PATH."
    echo ""
    echo " To install 'uv' (recommended fast package manager):"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "   source \$HOME/.local/bin/env  # or: export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo " Then set up dependencies and Playwright browser binaries:"
    echo "   uv sync"
    echo "   uv run playwright install chromium"
    echo "=========================================================="
    if [ -f "${SCRIPT_DIR}/.venv/bin/python" ] && [ -f "${SCRIPT_DIR}/.venv/bin/pytest" ]; then
        echo " -> Falling back to existing local virtual environment (.venv/)..."
        echo ""
        PY_CMD="${SCRIPT_DIR}/.venv/bin/python"
        PYTEST_CMD="${SCRIPT_DIR}/.venv/bin/pytest"
    else
        echo " Alternatively, you can use standard Python venv & pip:"
        echo "   python3 -m venv .venv"
        echo "   source .venv/bin/activate"
        echo "   pip install -r requirements.txt"
        echo "   playwright install chromium"
        echo "=========================================================="
        exit 127
    fi
fi
mkdir -p "${REPORT_DIR}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_FILE="${REPORT_DIR}/test_report_${TIMESTAMP}.html"
PDF_FILE="${REPORT_DIR}/test_report_${TIMESTAMP}.pdf"
LATEST_REPORT="${REPORT_DIR}/report.html"
LATEST_PDF="${REPORT_DIR}/report.pdf"
ALLURE_RESULTS="${REPORT_DIR}/allure-results"
ALLURE_REPORT="${REPORT_DIR}/allure-report"

# Flags
EXPORT_PDF=true
GENERATE_ALLURE=true
SERVE_ALLURE=false
UPDATE_REPORT=false
RUN_PRE_PHASE=false

# Ensure report and pdf are copied to latest even if pytest fails
cleanup_and_export() {
    if [ -f "${REPORT_FILE}" ]; then
        if [ "${UPDATE_REPORT}" = true ] && [ -f "${LATEST_REPORT}" ] && [ "${REPORT_FILE}" != "${LATEST_REPORT}" ]; then
            echo " Merging test results into master report..."
            $PY_CMD core/report_merger.py "${LATEST_REPORT}" "${REPORT_FILE}" "${LATEST_REPORT}" >/dev/null 2>&1 || cp "${REPORT_FILE}" "${LATEST_REPORT}"
        else
            cp "${REPORT_FILE}" "${LATEST_REPORT}"
        fi
    fi

    # Generate Allure Report if allure results exist
    if [ "${GENERATE_ALLURE}" = true ] && [ -d "${ALLURE_RESULTS}" ]; then
        if command -v allure >/dev/null 2>&1; then
            echo " Generating Allure test overview report..."

            # 1. Inject Environment Properties
            cat << EOF > "${ALLURE_RESULTS}/environment.properties"
Target.Appliance=10.1.33.160
Platform.OS=AlmaLinux / Redborder Appliance
Platform.Kernel=5.14.0-687.47.1.el9_8
Test.Framework=redborder-tester (Pytest + Playwright + Paramiko)
Test.Runner=redborder-tester
Execution.Environment=Redborder Appliance Integration
EOF

            # 2. Inject Categories Definition
            cat << 'EOF' > "${ALLURE_RESULTS}/categories.json"
[
  {
    "name": "Product Defects",
    "matchedStatuses": ["failed"],
    "messageRegex": ".*AssertionError.*"
  },
  {
    "name": "Infrastructure & Systemd Failures",
    "matchedStatuses": ["failed", "broken"],
    "messageRegex": ".*(systemctl|is-active|inactive|service|failed).*|.*ConnectionError.*|.*TimeoutError.*"
  },
  {
    "name": "UI & DOM Regressions",
    "matchedStatuses": ["broken"],
    "messageRegex": ".*(Timeout|waiting for locator|strict mode violation).*|.*Playwright.*"
  },
  {
    "name": "Telemetry & Ingestion Timeouts",
    "matchedStatuses": ["failed", "broken"],
    "messageRegex": ".*(Druid|rsyslog|snmpwalk|sensor-ctl).*|.*Timed out waiting for.*"
  }
]
EOF

            # 3. Inject Executor metadata
            cat << EOF > "${ALLURE_RESULTS}/executor.json"
{
  "name": "redborder-tester",
  "type": "local",
  "reportName": "Redborder Automated Test Platform Report",
  "buildName": "Redborder Appliance Integration Test",
  "reportUrl": "reports/allure-report/index.html"
}
EOF

            allure generate "${ALLURE_RESULTS}" -o "${ALLURE_REPORT}" --clean >/dev/null 2>&1 || true

            # 4. Rebrand Allure Report title, logo, and header brand
            if [ -f "${ALLURE_REPORT}/index.html" ]; then
                # Copy redborder logo & icon & favicon
                cp "core/branding/redborder-logo.png" "${ALLURE_REPORT}/redborder-logo.png" 2>/dev/null || true
                cp "core/branding/redborder-icon.png" "${ALLURE_REPORT}/redborder-icon.png" 2>/dev/null || true
                cp "core/branding/favicon.ico" "${ALLURE_REPORT}/favicon.ico" 2>/dev/null || true
                for fav in "${ALLURE_REPORT}"/assets/favicon*.ico; do
                    if [ -f "${fav}" ]; then
                        cp "core/branding/favicon.ico" "${fav}" 2>/dev/null || true
                    fi
                done

                python3 -c "
with open('${ALLURE_REPORT}/index.html') as f:
    c = f.read()
import re
c = re.sub(r'<title>[^<]*</title>', '<title>redborder-tester · Quality &amp; Test Overview</title>', c)
# Inject custom logo stylesheet and clean layout
custom_css = '''<style>
.side-nav__brand {
    padding: 16px 8px 14px 8px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
.side-nav__brand-icon {
    background: url(\"redborder-icon.png\") center center / contain no-repeat !important;
    min-width: 38px !important;
    width: 38px !important;
    height: 38px !important;
    flex-shrink: 0 !important;
    filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.15)) !important;
}
.side-nav__brand-text {
    display: none !important;
}
</style>
<script>
(function() {
    function cleanEmptyWidgets() {
        document.querySelectorAll('.widget').forEach(function(w) {
            var text = (w.innerText || '');
            if (text.indexOf('Trend') !== -1 || text.indexOf('Categories') !== -1) {
                w.style.display = 'none';
            }
        });
        document.querySelectorAll('.side-nav__item').forEach(function(item) {
            if (item.innerText && item.innerText.indexOf('Categories') !== -1) {
                item.style.display = 'none';
            }
        });
    }

    function handleBrandNavigation() {
        document.querySelectorAll('.side-nav__brand').forEach(function(el) {
            if (!el.dataset.brandNavBound) {
                el.dataset.brandNavBound = 'true';
                el.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (window.location.hash !== '' && window.location.hash !== '#') {
                        window.location.hash = '';
                    } else {
                        window.dispatchEvent(new HashChangeEvent('hashchange'));
                    }
                }, true);
            }
        });
    }

    function initObserver() {
        cleanEmptyWidgets();
        handleBrandNavigation();
        var target = document.body || document.documentElement;
        if (target) {
            var observer = new MutationObserver(function() {
                cleanEmptyWidgets();
                handleBrandNavigation();
            });
            observer.observe(target, { childList: true, subtree: true });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initObserver);
    } else {
        initObserver();
    }
})();
</script>'''
if '</head>' in c:
    c = c.replace('</head>', custom_css + '\n</head>')
with open('${ALLURE_REPORT}/index.html', 'w') as f:
    f.write(c)
" 2>/dev/null || true
            fi
            # Rebrand sidebar text and fix logo navigation in generated assets
            for js_file in "${ALLURE_REPORT}"/assets/*.js; do
                if [ -f "${js_file}" ]; then
                    sed -i 's|text:`Allure`|text:`redborder-tester`|g' "${js_file}" 2>/dev/null || true
                    sed -i 's|"data-ga4-event":`home_click`,href:`#`|"data-ga4-event":`home_click`,href:``|g' "${js_file}" 2>/dev/null || true
                fi
            done
        else
            echo " [Notice] 'allure' CLI is not installed; skipped compiling Allure HTML dashboard."
            echo "          To view Allure reports, install allure (e.g. npm install -g allure-commandline)."
            echo "          Meanwhile, the self-contained HTML report is available at: ${LATEST_REPORT}"
        fi
    fi

    # Export PDF report
    if [ "${EXPORT_PDF}" = true ] && [ -f "${REPORT_FILE}" ]; then
        echo " Exporting executive PDF test report..."
        $PY_CMD core/pdf_exporter.py "${REPORT_FILE}" "${PDF_FILE}" >/dev/null 2>&1 || true
        if [ -f "${PDF_FILE}" ]; then
            cp "${PDF_FILE}" "${LATEST_PDF}"
        fi
    fi

    # Optionally serve allure report
    if [ "${SERVE_ALLURE}" = true ] && [ -d "${ALLURE_RESULTS}" ]; then
        if command -v allure >/dev/null 2>&1; then
            echo " Opening Allure interactive report..."
            allure open "${ALLURE_REPORT}" || true
        fi
    fi
}

usage() {
    cat << EOF
Usage: ./run_tests.sh [OPTIONS]

Redborder Automated Test Platform Runner

Options:
  --all             Run all test suites (Backend, API, Web UI)
  --backend         Run backend infrastructure & systemd service tests
  --api             Run REST API & HTTP endpoint tests
  --web             Run Playwright browser UI end-to-end tests
  --smoke           Run quick smoke tests across all layers
  --headed          Run web tests in headed browser mode (visible UI)
  --allure          Generate Allure detailed test drill-down report
  --serve           Serve and open Allure report in default browser
  --update          Update/merge test results into existing report rather than starting fresh
  --pdf             Export report to PDF (enabled by default)
  --pre-phase       Run pre-phase environment preparation (ensure stable hierarchy, converge Chef, verify Druid)
  --with-pre-phase  Run pre-phase before the test suite automatically
  --post-phase      Run post-phase teardown (clean test domains, rebuild tree bounds, final Chef pass)
  clean, --clean    Clean all previous test reports and Allure results/reports
  -k EXPRESSION     Run tests matching given keyword expression
  -h, --help        Show this help message

Examples:
  ./run_tests.sh --pre-phase
  ./run_tests.sh --post-phase
  ./run_tests.sh --backend
  ./run_tests.sh --api
  ./run_tests.sh --web
  ./run_tests.sh --smoke
  ./run_tests.sh --all
  ./run_tests.sh --web --serve
  ./run_tests.sh --update -k "test_sensors_drag_drop"
EOF
    exit 0
}

TARGET_SUITE=""
EXTRA_ARGS=()

while [ $# -gt 0 ]; do
    case "$1" in
        --all)
            TARGET_SUITE="tests/"
            shift
            ;;
        --backend)
            TARGET_SUITE="tests/backend/"
            shift
            ;;
        --api)
            TARGET_SUITE="tests/api/"
            shift
            ;;
        --web)
            TARGET_SUITE="tests/web/"
            shift
            ;;
        --smoke)
            EXTRA_ARGS+=("-m" "smoke")
            shift
            ;;
        --headed)
            EXTRA_ARGS+=("--headed")
            shift
            ;;
        --allure)
            GENERATE_ALLURE=true
            shift
            ;;
        --serve)
            GENERATE_ALLURE=true
            SERVE_ALLURE=true
            shift
            ;;
        --update|--append)
            UPDATE_REPORT=true
            shift
            ;;
        --pdf)
            EXPORT_PDF=true
            shift
            ;;
        --no-pdf)
            EXPORT_PDF=false
            shift
            ;;
        --with-pre-phase)
            RUN_PRE_PHASE=true
            shift
            ;;
        --pre-phase)
            echo "=========================================================="
            echo " Running Pre-Phase: Environment Preparation & Stabilization"
            echo "=========================================================="
            $PY_CMD -c "
import sys
import time
from playwright.sync_api import sync_playwright
from config.settings import settings
from core.ssh_client import SSHClient
from core.pages.login_page import LoginPage
from core.pages.sensors_page import SensorsPage

print('[Pre-Phase] Connecting to appliance via SSH...')
ssh = SSHClient(host=settings.target_host, username=settings.ssh_user, password=settings.ssh_password)
with ssh:
    print('[Pre-Phase] Ensuring redborder-sensors package...')
    ssh.ensure_redborder_sensors_installed()

    print('[Pre-Phase] Starting all baseline mock sandboxes (Flow, Vault, SNMP, HTTP)...')
    ssh.start_all_baseline_mock_sandboxes()

    print('[Pre-Phase] Running initial Chef convergence for virtual network interfaces...')
    ssh.run_chef_client(timeout=180)
    time.sleep(5)

    print('[Pre-Phase] Launching browser to provision baseline Web UI testbed...')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(ignore_https_errors=True, viewport={'width': 1440, 'height': 900})
        page = ctx.new_page()
        login = LoginPage(page, settings.base_url)
        login.open()
        login.login(settings.web_user, settings.web_password)
        sensors = SensorsPage(page, settings.base_url)
        testbed = sensors.ensure_full_testbed(
            sp_name='rb-test-sp',
            ns_name='rb-test-ns',
            org_name='rb-test-org',
            sp2_name='rb-test-sp2',
        )
        print(f'[Pre-Phase] Baseline testbed ready: {testbed.get(\"sensors\", {})}')
        browser.close()

    print('[Pre-Phase] Running Chef convergence loop and verifying Druid readiness...')
    ok = ssh.converge_chef_and_wait_druid(iterations=1, druid_timeout=90, chef_timeout=180)
    if not ok:
        print('[Pre-Phase] Error: Chef convergence or Druid stabilization failed!', file=sys.stderr)
        sys.exit(1)
    print('[Pre-Phase] Environment successfully stabilized!')
"
            exit $?
            ;;
        --post-phase)
            echo "=========================================================="
            echo " Running Post-Phase: Teardown & Environment Normalization"
            echo "=========================================================="
            $PY_CMD -c "
import sys
from playwright.sync_api import sync_playwright
from config.settings import settings
from core.ssh_client import SSHClient
from core.pages.login_page import LoginPage
from core.pages.sensors_page import SensorsPage

print('[Post-Phase] Connecting to appliance via SSH...')
ssh = SSHClient(host=settings.target_host, username=settings.ssh_user, password=settings.ssh_password)
with ssh:
    print('[Post-Phase] Launching browser to clean baseline Web UI testbed...')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(ignore_https_errors=True, viewport={'width': 1440, 'height': 900})
        page = ctx.new_page()
        login = LoginPage(page, settings.base_url)
        login.open()
        login.login(settings.web_user, settings.web_password)
        sensors = SensorsPage(page, settings.base_url)
        sensors.cleanup_full_testbed(
            sp_name='rb-test-sp',
            ns_name='rb-test-ns',
            org_name='rb-test-org',
            sp2_name='rb-test-sp2',
        )
        browser.close()

    print('[Post-Phase] Stopping all mock sandboxes...')
    ssh.stop_all_baseline_mock_sandboxes()

    print('[Post-Phase] Rebuilding PostgreSQL sensor tree bounds...')
    ssh.rebuild_sensor_tree()

    print('[Post-Phase] Running final Chef convergence pass...')
    ssh.run_chef_client(timeout=180)
    ssh.wait_for_druid_ready(timeout=60)
    print('[Post-Phase] Environment cleanup completed successfully!')
"
            exit $?
            ;;
        clean|--clean)
            echo " Cleaning all reports, Allure results, and test artifacts..."
            rm -rf "${REPORT_DIR}"/*
            echo " Reports directory cleaned."
            exit 0
            ;;
        -k)
            if [ $# -lt 2 ]; then
                echo "Error: -k requires an expression argument." >&2
                usage
            fi
            EXTRA_ARGS+=("-k" "$2")
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

if [ -z "$TARGET_SUITE" ]; then
    TARGET_SUITE="tests/"
fi

# Automatically run pre-phase if requested
if [ "${RUN_PRE_PHASE}" = true ]; then
    echo "=========================================================="
    echo " [Pre-Phase] Running environment preparation before test suite..."
    echo "=========================================================="
    "${SCRIPT_DIR}/run_tests.sh" --pre-phase
    echo ""
fi

trap cleanup_and_export EXIT

echo "=========================================================="
echo " Starting Redborder Test Suite"
echo " Target: ${TARGET_SUITE}"
echo " Report: ${REPORT_FILE}"
if [ "${UPDATE_REPORT}" = true ]; then
    echo " Mode:   Incremental Update (merge into existing report)"
fi
echo "=========================================================="

# Clean previous Allure results only if not in incremental update mode
if [ "${UPDATE_REPORT}" != true ]; then
    rm -rf "${ALLURE_RESULTS}"
fi
mkdir -p "${ALLURE_RESULTS}"

# Run pytest allowing exit status to propagate after trap copies latest report
set +e
$PYTEST_CMD "${TARGET_SUITE}" \
    --alluredir="${ALLURE_RESULTS}" \
    --html="${REPORT_FILE}" \
    --self-contained-html \
    "${EXTRA_ARGS[@]}"
TEST_EXIT_CODE=$?
set -e

echo ""
echo "=========================================================="
if [ ${TEST_EXIT_CODE} -eq 0 ]; then
    echo " Tests completed successfully!"
else
    echo " Tests finished with failures (exit code: ${TEST_EXIT_CODE})"
fi
echo " HTML Report:   ${LATEST_REPORT}"
if [ "${EXPORT_PDF}" = true ] && [ -f "${LATEST_PDF}" ]; then
    echo " PDF Export:    ${LATEST_PDF}"
fi
if [ -d "${ALLURE_REPORT}" ]; then
    echo " Allure Report: ${ALLURE_REPORT}/index.html (run './run_tests.sh --serve' or 'allure open ${ALLURE_REPORT}')"
fi
echo "=========================================================="

exit ${TEST_EXIT_CODE}
