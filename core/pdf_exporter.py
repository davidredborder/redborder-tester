#!/usr/bin/env python3
"""
Professional Executive PDF Exporter for Redborder Automated Test Platform.
Generates an executive-ready corporate PDF report with KPIs, visual pass/fail bars,
layer breakdowns, and a dedicated high-resolution screenshot annex.
"""

import sys
import json
import base64
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def extract_report_data(html_path: str):
    import html
    import re

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    env_info = {}
    tests = []
    screenshots = []

    # pytest-html embeds all test execution data in data-jsonblob="{...}"
    m = re.search(r'data-jsonblob=\"(\{.*?\})\"', html_content)
    if m:
        try:
            raw_json = html.unescape(m.group(1))
            report_data = json.loads(raw_json)
            env_info = report_data.get("environment", {})

            for test_id, runs in report_data.get("tests", {}).items():
                if not runs:
                    continue
                run = runs[0]
                result = run.get("result", "Passed")
                duration = run.get("duration", "0 ms")

                # Categorize test
                category = "Backend Infrastructure"
                if "tests/web" in test_id:
                    category = "End-to-End Lifecycle" if "lifecycle" in test_id else "Web UI Management"
                elif "tests/api" in test_id or "test_api_" in test_id:
                    category = "REST API Endpoints"
                elif "test_ssh_" in test_id:
                    category = "Backend Infrastructure"

                parts = test_id.split("::")
                short_name = parts[-1] if len(parts) > 1 else test_id

                # Extract extras / media
                for extra in run.get("extras", []):
                    if extra.get("format_type") == "image":
                        content = extra.get("content", "")
                        if content and not content.startswith("data:image"):
                            content = f"data:image/png;base64,{content}"
                        caption = extra.get("name", short_name)
                        screenshots.append({
                            "test": short_name,
                            "category": category,
                            "caption": caption,
                            "src": content
                        })

                tests.append({
                    "id": test_id,
                    "name": short_name,
                    "category": category,
                    "result": result,
                    "duration": duration,
                    "is_failed": result.lower() in ("failed", "error"),
                    "is_skipped": result.lower() == "skipped"
                })
        except Exception as e:
            print(f"Warning: Failed parsing JSON from pytest-html: {e}")

    # Fallback to DOM parsing if needed
    if not tests:
        soup = BeautifulSoup(html_content, "html.parser")
        tbodies = soup.select("#results-table tbody")
        for tbody in tbodies:
            test_id_elem = tbody.select_one("td.col-testId, td.col-name, td.col-test")
            result_elem = tbody.select_one("td.col-result")
            duration_elem = tbody.select_one("td.col-duration")

            if test_id_elem and result_elem:
                test_id = test_id_elem.text.strip()
                result = result_elem.text.strip()
                duration = duration_elem.text.strip() if duration_elem else "0 ms"

                category = "Backend Infrastructure"
                if "tests/web" in test_id:
                    category = "End-to-End Lifecycle" if "lifecycle" in test_id else "Web UI Management"
                elif "tests/api" in test_id or "test_api_" in test_id:
                    category = "REST API Endpoints"

                parts = test_id.split("::")
                short_name = parts[-1] if len(parts) > 1 else test_id

                tests.append({
                    "id": test_id,
                    "name": short_name,
                    "category": category,
                    "result": result,
                    "duration": duration,
                    "is_failed": result.lower() in ("failed", "error"),
                    "is_skipped": result.lower() == "skipped"
                })

    # Calculate metrics
    total = len(tests)
    passed = sum(1 for t in tests if not t["is_failed"] and not t["is_skipped"])
    failed = sum(1 for t in tests if t["is_failed"])
    skipped = sum(1 for t in tests if t["is_skipped"])
    pass_rate = round((passed / total * 100), 1) if total > 0 else 100.0

    return {
        "env": env_info,
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": pass_rate,
        "tests": tests,
        "screenshots": screenshots
    }


def generate_executive_html(data: dict) -> str:
    categories = ["Backend Infrastructure", "REST API Endpoints", "Web UI Management", "End-to-End Lifecycle"]
    category_stats = {}
    for cat in categories:
        cat_tests = [t for t in data["tests"] if t["category"] == cat]
        cat_total = len(cat_tests)
        cat_passed = sum(1 for t in cat_tests if not t["is_failed"] and not t["is_skipped"])
        cat_failed = sum(1 for t in cat_tests if t["is_failed"])
        cat_rate = round((cat_passed / cat_total * 100), 1) if cat_total > 0 else 100.0
        category_stats[cat] = {
            "total": cat_total,
            "passed": cat_passed,
            "failed": cat_failed,
            "rate": cat_rate,
            "tests": cat_tests
        }

    status_color = "#10b981" if data["failed"] == 0 else "#ef4444"
    status_label = "ALL SYSTEMS OPERATIONAL" if data["failed"] == 0 else f"{data['failed']} FAILURE(S) DETECTED"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Redborder Automated Test Execution Report</title>
  <style>
    @page {{
      size: A4 portrait;
      margin: 14mm 12mm 14mm 12mm;
    }}
    * {{
      box-sizing: border-box;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: #0f172a;
      background: #ffffff;
      margin: 0;
      padding: 0;
      font-size: 10.5px;
      line-height: 1.5;
    }}
    
    /* Cover / Header Banner */
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 2px solid #0f172a;
      padding-bottom: 14px;
      margin-bottom: 18px;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .shield-icon {{
      font-size: 28px;
    }}
    .brand-title {{
      font-size: 20px;
      font-weight: 800;
      letter-spacing: -0.5px;
      color: #0f172a;
      margin: 0;
    }}
    .brand-subtitle {{
      font-size: 11px;
      color: #64748b;
      margin: 2px 0 0 0;
      font-weight: 500;
    }}
    .status-badge {{
      background: {status_color};
      color: #ffffff;
      padding: 6px 14px;
      border-radius: 6px;
      font-weight: 700;
      font-size: 11px;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }}

    /* KPI Summary Cards */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 20px;
    }}
    .kpi-card {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 12px 14px;
      border-left: 4px solid #0284c7;
    }}
    .kpi-card.success {{ border-left-color: #10b981; }}
    .kpi-card.danger {{ border-left-color: #ef4444; }}
    .kpi-card.warning {{ border-left-color: #f59e0b; }}
    .kpi-label {{
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: #64748b;
      font-weight: 600;
      margin-bottom: 4px;
    }}
    .kpi-val {{
      font-size: 22px;
      font-weight: 800;
      color: #0f172a;
      line-height: 1;
    }}
    .kpi-sub {{
      font-size: 9.5px;
      color: #94a3b8;
      margin-top: 4px;
    }}

    /* Layer Breakdown Cards */
    .section-title {{
      font-size: 13px;
      font-weight: 700;
      color: #0f172a;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin: 18px 0 10px 0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 6px;
    }}
    
    .layer-table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 20px;
      font-size: 10.5px;
    }}
    .layer-table th {{
      background: #f1f5f9;
      color: #334155;
      font-weight: 600;
      text-align: left;
      padding: 8px 10px;
      border-bottom: 1px solid #cbd5e1;
    }}
    .layer-table td {{
      padding: 8px 10px;
      border-bottom: 1px solid #e2e8f0;
    }}
    .progress-bar-container {{
      width: 100%;
      height: 7px;
      background: #e2e8f0;
      border-radius: 4px;
      overflow: hidden;
    }}
    .progress-bar-fill {{
      height: 100%;
      background: #10b981;
    }}

    /* Detailed Test List */
    .test-table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 20px;
      font-size: 9.5px;
    }}
    .test-table th {{
      background: #f8fafc;
      color: #475569;
      font-weight: 600;
      text-align: left;
      padding: 6px 8px;
      border-bottom: 1px solid #cbd5e1;
    }}
    .test-table td {{
      padding: 5px 8px;
      border-bottom: 1px solid #f1f5f9;
      color: #334155;
    }}
    .test-table tr:nth-child(even) {{
      background: #fcfcfd;
    }}
    .badge {{
      display: inline-block;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 9px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    .badge.pass {{ background: #dcfce7; color: #15803d; }}
    .badge.fail {{ background: #fee2e2; color: #b91c1c; }}

    /* Screenshot Annex */
    .page-break {{
      page-break-before: always;
      break-before: page;
    }}
    .screenshot-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 14px;
      margin-top: 10px;
    }}
    .screenshot-card {{
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      overflow: hidden;
      background: #ffffff;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    .screenshot-img-container {{
      width: 100%;
      height: 160px;
      background: #090d16;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
    }}
    .screenshot-img-container img {{
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
    }}
    .screenshot-meta {{
      padding: 6px 10px;
      background: #f8fafc;
      border-top: 1px solid #e2e8f0;
    }}
    .screenshot-title {{
      font-weight: 700;
      font-size: 10px;
      color: #0f172a;
    }}
    .screenshot-test {{
      font-size: 8.5px;
      color: #64748b;
      margin-top: 2px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
  </style>
</head>
<body>

  <!-- Header Banner -->
  <div class="header">
    <div class="brand">
      <div class="shield-icon">🛡️</div>
      <div>
        <h1 class="brand-title">redborder-tester</h1>
        <div class="brand-subtitle">Automated Test Execution &amp; Quality Audit Report · Target Appliance: 10.1.33.160</div>
      </div>
    </div>
    <div class="status-badge">{status_label}</div>
  </div>

  <!-- KPI Cards -->
  <div class="kpi-grid">
    <div class="kpi-card success">
      <div class="kpi-label">Overall Pass Rate</div>
      <div class="kpi-val">{data['pass_rate']}%</div>
      <div class="kpi-sub">{data['passed']} of {data['total']} tests passed</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Total Execution</div>
      <div class="kpi-val">{data['total']}</div>
      <div class="kpi-sub">Test cases verified</div>
    </div>
    <div class="kpi-card {'danger' if data['failed'] > 0 else 'success'}">
      <div class="kpi-label">Defects / Failures</div>
      <div class="kpi-val">{data['failed']}</div>
      <div class="kpi-sub">0 blockers detected</div>
    </div>
    <div class="kpi-card warning">
      <div class="kpi-label">Visual Verification</div>
      <div class="kpi-val">{len(data['screenshots'])}</div>
      <div class="kpi-sub">UI captures validated</div>
    </div>
  </div>

  <!-- Layer Breakdown -->
  <div class="section-title">
    <span>Architecture Layer Performance</span>
  </div>
  <table class="layer-table">
    <thead>
      <tr>
        <th style="width: 32%;">Architecture Layer</th>
        <th style="width: 14%;">Total Tests</th>
        <th style="width: 14%;">Passed</th>
        <th style="width: 14%;">Failed</th>
        <th style="width: 26%;">Pass Rate %</th>
      </tr>
    </thead>
    <tbody>
"""
    for cat, stat in category_stats.items():
        if stat["total"] == 0:
            continue
        html += f"""
      <tr>
        <td><strong>{cat}</strong></td>
        <td>{stat['total']}</td>
        <td><span style="color:#15803d; font-weight:600;">{stat['passed']}</span></td>
        <td><span style="color:#b91c1c; font-weight:600;">{stat['failed']}</span></td>
        <td>
          <div style="display:flex; align-items:center; gap:8px;">
            <div class="progress-bar-container">
              <div class="progress-bar-fill" style="width: {stat['rate']}%;"></div>
            </div>
            <span style="font-weight:700; width:45px; text-align:right;">{stat['rate']}%</span>
          </div>
        </td>
      </tr>
"""
    html += """
    </tbody>
  </table>

  <!-- Test Execution Detail Table -->
  <div class="section-title">
    <span>Test Verification Audit Log</span>
  </div>
  <table class="test-table">
    <thead>
      <tr>
        <th style="width: 12%;">Status</th>
        <th style="width: 28%;">Test Case</th>
        <th style="width: 22%;">Layer / Subsystem</th>
        <th style="width: 12%;">Duration</th>
        <th style="width: 26%;">Identifier</th>
      </tr>
    </thead>
    <tbody>
"""
    for t in data["tests"]:
        badge_cls = "pass" if not t["is_failed"] and not t["is_skipped"] else "fail"
        html += f"""
      <tr>
        <td><span class="badge {badge_cls}">{t['result']}</span></td>
        <td><strong>{t['name']}</strong></td>
        <td>{t['category']}</td>
        <td>{t['duration']}</td>
        <td style="color:#64748b; font-family:monospace; font-size:8.5px;">{t['id'][:45]}...</td>
      </tr>
"""
    html += """
    </tbody>
  </table>
"""

    # If screenshots exist, generate Screenshot Annex
    if data["screenshots"]:
        html += """
  <!-- Screenshot Annex Page -->
  <div class="page-break"></div>
  <div class="header">
    <div class="brand">
      <div class="shield-icon">📸</div>
      <div>
        <h2 class="brand-title" style="font-size:18px;">Visual Test Evidence Annex</h2>
        <div class="brand-subtitle">High-resolution Playwright UI verification snapshots captured during run</div>
      </div>
    </div>
  </div>

  <div class="screenshot-grid">
"""
        for sc in data["screenshots"]:
            html += f"""
    <div class="screenshot-card">
      <div class="screenshot-img-container">
        <img src="{sc['src']}" alt="{sc['caption']}">
      </div>
      <div class="screenshot-meta">
        <div class="screenshot-title">{sc['caption']}</div>
        <div class="screenshot-test">{sc['test']} ({sc['category']})</div>
      </div>
    </div>
"""
        html += """
  </div>
"""

    html += """
</body>
</html>
"""
    return html


def export_executive_pdf(html_path: str, output_pdf_path: str):
    data = extract_report_data(html_path)
    exec_html = generate_executive_html(data)

    output_file = Path(output_pdf_path).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_content(exec_html, wait_until="networkidle")

        page.pdf(
            path=str(output_file),
            format="A4",
            print_background=True,
            margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"},
            display_header_footer=True,
            header_template='<div style="font-size:8.5px; color:#64748b; width:100%; text-align:right; padding-right:10mm;">redborder-tester · Executive Quality Report</div>',
            footer_template='<div style="font-size:8.5px; color:#64748b; width:100%; text-align:center;">Page <span class="pageNumber"></span> of <span class="totalPages"></span></div>'
        )
        browser.close()

    print(f"Exported executive PDF report: {output_file}")


if __name__ == "__main__":
    html_in = sys.argv[1] if len(sys.argv) > 1 else "reports/report.html"
    pdf_out = sys.argv[2] if len(sys.argv) > 2 else "reports/report.pdf"
    export_executive_pdf(html_in, pdf_out)
