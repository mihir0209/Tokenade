"""
Detection Score Dashboard — generate HTML reports for stealth test results.

Provides visual score breakdown by category and detailed test results.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

from tokenade.core.browser.stealth_test import (
    StealthTestReport,
    DetectionTestResult,
    Verdict,
    JS_CHECKS,
)

logger = logging.getLogger(__name__)


# ─── HTML Template ────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tokenade Stealth Report</title>
<style>
:root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --text-dim: #8b949e; --accent: #58a6ff;
    --green: #3fb950; --red: #f85149; --yellow: #d29922;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 2rem; }
.header { text-align: center; margin-bottom: 2rem; }
.score-circle { width: 180px; height: 180px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem; font-size: 3rem; font-weight: 700; }
.score-a { background: conic-gradient(var(--green) 0% 90%, var(--border) 90%); }
.score-b { background: conic-gradient(var(--green) 0% 80%, var(--border) 80%); }
.score-c { background: conic-gradient(var(--yellow) 0% 70%, var(--border) 70%); }
.score-d { background: conic-gradient(var(--yellow) 0% 60%, var(--border) 60%); }
.score-f { background: conic-gradient(var(--red) 0% 50%, var(--border) 50%); }
.score-inner { width: 140px; height: 140px; border-radius: 50%; background: var(--bg); display: flex; align-items: center; justify-content: center; }
.grade { font-size: 2.5rem; font-weight: 700; }
.meta { color: var(--text-dim); margin-top: 0.5rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 1rem; margin-top: 2rem; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; }
.card h3 { margin-bottom: 1rem; color: var(--accent); }
.result { display: flex; align-items: center; padding: 0.4rem 0; border-bottom: 1px solid var(--border); }
.result:last-child { border-bottom: none; }
.icon { width: 24px; text-align: center; margin-right: 0.5rem; font-weight: 700; }
.pass { color: var(--green); }
.fail { color: var(--red); }
.warn { color: var(--yellow); }
.skip { color: var(--text-dim); }
.name { flex: 1; font-size: 0.9rem; }
.score { color: var(--text-dim); font-size: 0.85rem; margin-left: 0.5rem; }
.bar-bg { width: 100%; height: 6px; background: var(--border); border-radius: 3px; margin-top: 0.5rem; }
.bar-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
.summary { display: flex; gap: 2rem; justify-content: center; margin-top: 1rem; }
.summary-item { text-align: center; }
.summary-item .value { font-size: 1.5rem; font-weight: 700; }
.summary-item .label { color: var(--text-dim); font-size: 0.8rem; }
</style>
</head>
<body>
<div class="header">
    <h1>Tokenade Stealth Report</h1>
    <p class="meta">Browser: TOKENADE_BROWSER | Generated: TOKENADE_TIMESTAMP</p>
    <div class="score-circle score-SCORE_CLASS">
        <div class="score-inner">
            <span class="grade">GRADE</span>
        </div>
    </div>
    <p style="font-size:1.2rem; font-weight:600;">SCORE/100</p>
    <div class="summary">
        <div class="summary-item"><div class="value pass">PASSED</div><div class="label">Tests</div></div>
        <div class="summary-item"><div class="value fail">FAILED</div><div class="label">Tests</div></div>
        <div class="summary-item"><div class="value warn">WARNED</div><div class="label">Tests</div></div>
    </div>
</div>
<div class="grid">
    CARDS
</div>
</body>
</html>"""


def generate_html_report(report: StealthTestReport, output_path: Optional[str] = None) -> str:
    """Generate an HTML report from a StealthTestReport."""
    grade = report._grade().lower()

    # Build cards by category
    categories = _categorize_results(report.results)
    cards_html = ""
    for cat_name, cat_results in categories.items():
        cat_score = sum(r.score for r in cat_results) / max(len(cat_results), 1)
        results_html = ""
        for r in cat_results:
            icon_cls = r.verdict.value
            icon = {"pass": "✓", "fail": "✗", "warn": "!", "skip": "○"}[r.verdict.value]
            results_html += f"""
    <div class="result">
      <span class="icon {icon_cls}">{icon}</span>
      <span class="name">{r.name}</span>
      <span class="score">{r.score:.0f}</span>
    </div>"""

        cards_html += f"""
  <div class="card">
    <h3>{cat_name}</h3>
    {results_html}
    <div class="bar-bg"><div class="bar-fill" style="width:{cat_score:.0f}%; background:var({'--green' if cat_score >= 80 else '--yellow' if cat_score >= 60 else '--red'});"></div></div>
  </div>"""

    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(report.timestamp))

    html = HTML_TEMPLATE.replace("TOKENADE_BROWSER", report.browser)
    html = html.replace("TOKENADE_TIMESTAMP", ts)
    html = html.replace("SCORE_CLASS", grade)
    html = html.replace("GRADE", report._grade())
    html = html.replace("SCORE", f"{report.overall_score:.0f}")
    html = html.replace("PASSED", str(report.passed))
    html = html.replace("FAILED", str(report.failed))
    html = html.replace("WARNED", str(report.warned))
    html = html.replace("CARDS", cards_html)

    output = output_path or str(Path.home() / ".tokenade" / "stealth_report.html")
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        f.write(html)

    logger.info(f"Stealth report saved: {output}")
    return output


def generate_json_report(report: StealthTestReport, output_path: Optional[str] = None) -> str:
    """Generate a JSON report from a StealthTestReport."""
    data = {
        "overall_score": report.overall_score,
        "grade": report._grade(),
        "browser": report.browser,
        "timestamp": report.timestamp,
        "duration_ms": report.duration_ms,
        "passed": report.passed,
        "failed": report.failed,
        "warned": report.warned,
        "results": [
            {
                "name": r.name,
                "verdict": r.verdict.value,
                "score": r.score,
                "message": r.message,
                "duration_ms": r.duration_ms,
            }
            for r in report.results
        ],
    }

    output = output_path or str(Path.home() / ".tokenade" / "stealth_report.json")
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"JSON report saved: {output}")
    return output


def _categorize_results(results: List[DetectionTestResult]) -> Dict[str, List[DetectionTestResult]]:
    """Categorize results into display categories."""
    categories = {
        "JavaScript Properties": [],
        "Canvas & WebGL": [],
        "Automation Artifacts": [],
        "Browser Features": [],
        "Site Tests": [],
    }

    canvas_webgl = {"Canvas fingerprint", "WebGL vendor", "WebGL renderer", "WebGL consistency"}
    automation = {"No automation artifacts", "No headless detection", "window.automationControlled", "Function.toString shows no modifications"}

    for r in results:
        name_lower = r.name.lower()
        if any(k in name_lower for k in ["site:", "http"]):
            categories["Site Tests"].append(r)
        elif any(k in r.name for k in canvas_webgl) or "canvas" in name_lower or "webgl" in name_lower:
            categories["Canvas & WebGL"].append(r)
        elif r.name in automation:
            categories["Automation Artifacts"].append(r)
        else:
            categories["JavaScript Properties"].append(r)

    # Remove empty categories
    return {k: v for k, v in categories.items() if v}
