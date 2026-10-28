#!/usr/bin/env python3
"""
Test report merger for Redborder Automated Test Platform.
Allows incremental re-running of individual tests while preserving and updating
their results in the comprehensive master test report (pytest-html) and Allure results.
"""

import os
import re
import json
import html
from typing import Dict, Any, Optional


def load_jsonblob_from_html(html_content: str) -> Optional[Dict[str, Any]]:
    """Extracts and parses data-jsonblob from pytest-html report content."""
    m = re.search(r'data-jsonblob=\"(\{.*?\})\"', html_content)
    if not m:
        return None
    try:
        raw_json = html.unescape(m.group(1))
        return json.loads(raw_json, strict=False)
    except Exception as e:
        print(f"Warning: Failed to parse data-jsonblob: {e}")
        return None


def merge_reports(master_report_path: str, new_report_path: str, output_path: str) -> bool:
    """
    Merges newly executed test results from `new_report_path` into `master_report_path`.
    Tests in `new_report_path` overwrite previous runs for matching test IDs.
    Returns True if successfully merged and written to `output_path`.
    """
    if not os.path.exists(master_report_path):
        if os.path.exists(new_report_path):
            with open(new_report_path, "r", encoding="utf-8") as f_in, open(output_path, "w", encoding="utf-8") as f_out:
                f_out.write(f_in.read())
            return True
        return False

    if not os.path.exists(new_report_path):
        return False

    with open(master_report_path, "r", encoding="utf-8") as f:
        master_html = f.read()

    with open(new_report_path, "r", encoding="utf-8") as f:
        new_html = f.read()

    master_blob = load_jsonblob_from_html(master_html)
    new_blob = load_jsonblob_from_html(new_html)

    if not master_blob or not new_blob:
        print("Warning: Missing or invalid jsonblob in master or new report. Fallback to new report.")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(new_html)
        return True

    # Merge tests: master_blob["tests"] updated with new_blob["tests"]
    master_tests = master_blob.get("tests", {})
    new_tests = new_blob.get("tests", {})

    for test_id, runs in new_tests.items():
        master_tests[test_id] = runs

    master_blob["tests"] = master_tests

    # Update environment properties with newest if present
    master_env = master_blob.get("environment", {})
    new_env = new_blob.get("environment", {})
    master_env.update(new_env)
    master_blob["environment"] = master_env

    # Recalculate summary counts
    total_tests = len(master_tests)
    passed_count = 0
    failed_count = 0
    skipped_count = 0

    for test_id, runs in master_tests.items():
        if not runs:
            continue
        res = runs[0].get("result", "").lower()
        if res == "passed":
            passed_count += 1
        elif res in ("failed", "error"):
            failed_count += 1
        elif res == "skipped":
            skipped_count += 1

    # Encode updated jsonblob
    updated_json_str = json.dumps(master_blob)
    escaped_json_str = html.escape(updated_json_str, quote=True)

    # Replace data-jsonblob in new_html (which has latest assets/styles/scripts)
    merged_html = re.sub(
        r'data-jsonblob=\"(\{.*?\})\"',
        lambda _: f'data-jsonblob="{escaped_json_str}"',
        new_html,
        count=1
    )

    # Update summary spans in merged HTML:
    # <p class="run-count">X tests took ...</p>
    merged_html = re.sub(
        r'<p class=\"run-count\">\d+\s+tests',
        f'<p class="run-count">{total_tests} tests',
        merged_html
    )

    # <span class="failed">X Failed,</span>
    merged_html = re.sub(
        r'<span class=\"failed\">\d+\s+Failed,</span>',
        f'<span class="failed">{failed_count} Failed,</span>',
        merged_html
    )

    # <span class="passed">X Passed,</span>
    merged_html = re.sub(
        r'<span class=\"passed\">\d+\s+Passed,</span>',
        f'<span class="passed">{passed_count} Passed,</span>',
        merged_html
    )

    # <span class="skipped">X Skipped,</span>
    merged_html = re.sub(
        r'<span class=\"skipped\">\d+\s+Skipped,</span>',
        f'<span class="skipped">{skipped_count} Skipped,</span>',
        merged_html
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(merged_html)

    return True


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: report_merger.py <master_report.html> <new_report.html> <output.html>")
        sys.exit(1)
    success = merge_reports(sys.argv[1], sys.argv[2], sys.argv[3])
    sys.exit(0 if success else 1)
