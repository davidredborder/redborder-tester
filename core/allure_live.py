import os
import subprocess
import threading
import time

_lock = threading.Lock()
_last_run_time = 0.0
_DEBOUNCE_INTERVAL = 4.0  # seconds

def _apply_branding(report_dir: str) -> None:
    """Applies redborder logo, custom branding CSS, and title to generated Allure report."""
    try:
        index_path = os.path.join(report_dir, "index.html")
        if not os.path.isfile(index_path):
            return

        branding_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "branding"))
        import shutil
        import base64
        import re

        # Read base64 data URI of the Redborder shield icon
        icon_path = os.path.join(branding_dir, "redborder-icon.png")
        data_uri = ""
        if os.path.isfile(icon_path):
            with open(icon_path, "rb") as bf:
                b64 = base64.b64encode(bf.read()).decode("utf-8")
                data_uri = f"data:image/png;base64,{b64}"

        # Copy icons and logo to report root
        for fname in ["redborder-logo.png", "redborder-icon.png", "favicon.ico"]:
            src = os.path.join(branding_dir, fname)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(report_dir, fname))

        assets_dir = os.path.join(report_dir, "assets")
        if os.path.isdir(assets_dir):
            fav_src = os.path.join(branding_dir, "favicon.ico")
            if os.path.isfile(fav_src):
                for f in os.listdir(assets_dir):
                    if f.startswith("favicon") and f.endswith(".ico"):
                        shutil.copy2(fav_src, os.path.join(assets_dir, f))

            for f in os.listdir(assets_dir):
                if f.endswith(".js"):
                    js_file = os.path.join(assets_dir, f)
                    try:
                        with open(js_file, "r", encoding="utf-8") as jf:
                            js_c = jf.read()
                        mod = js_c.replace("text:`Allure`", "text:`redborder-tester`")
                        mod = mod.replace('"data-ga4-event":`home_click`,href:`#`', '"data-ga4-event":`home_click`,href:``')
                        if mod != js_c:
                            with open(js_file, "w", encoding="utf-8") as jf:
                                jf.write(mod)
                    except Exception:
                        pass



        # Update index.html
        with open(index_path, "r", encoding="utf-8") as f:
            c = f.read()

        import re
        c = re.sub(r'<title>[^<]*</title>', '<title>redborder-tester · Quality &amp; Test Overview</title>', c)

        custom_style = """<style>
.side-nav__brand {
    padding: 16px 8px 14px 8px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
.side-nav__brand-icon {
    background: url("redborder-icon.png") center center / contain no-repeat !important;
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
</script>"""

        if custom_style not in c and "</head>" in c:
            c = c.replace("</head>", custom_style + "\n</head>")
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(c)
    except Exception:
        pass


def trigger_live_allure_update(results_dir: str = "reports/allure-results", report_dir: str = "reports/allure-report") -> None:
    """Debounced background generation of Allure report from live results.
    Runs asynchronously in a separate daemon thread to ensure pytest execution is not blocked.
    """
    global _last_run_time
    now = time.time()
    with _lock:
        if now - _last_run_time < _DEBOUNCE_INTERVAL:
            return
        _last_run_time = now

    def _worker():
        try:
            if not os.path.isdir(results_dir):
                return
            subprocess.run(
                ["allure", "generate", results_dir, "-o", report_dir, "--clean"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=20,
            )
            _apply_branding(report_dir)
        except Exception:
            pass

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

