from __future__ import annotations

import json
from html import escape
from datetime import timezone
from pathlib import Path

from app.core.config import settings
from app.database.models import TestRun, TestStepResult


class ReportGenerator:
    """Produces a visual HTML evidence report with screenshots and execution metrics."""

    def generate(self, run: TestRun, steps: list[TestStepResult]) -> str:
        settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = settings.REPORTS_DIR / f"{run.id}.html"
        report_path.write_text(self._render_html(run, steps), encoding="utf-8")
        return str(report_path)

    def _render_html(self, run: TestRun, steps: list[TestStepResult]) -> str:
        total = max(run.total_steps, len(steps), 1)
        passed = sum(1 for step in steps if step.status == "passed")
        failed = sum(1 for step in steps if step.status == "failed")
        pass_percent = round((passed / total) * 100)
        radius = 54
        circumference = 2 * 3.14159 * radius
        dash = (pass_percent / 100) * circumference
        step_cards = "\n".join(self._render_step_card(step) for step in steps) or self._empty_state()
        timeline = "\n".join(self._render_timeline_bar(step) for step in steps)
        status_class = "pass" if run.status == "passed" else "fail"
        duration = self._duration_label(run)

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>HINSA AI Evidence Report - {escape(run.id)}</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #050816; color: #edf3ff; }}
    body::before {{ content:""; position:fixed; inset:0; pointer-events:none; background:
      linear-gradient(135deg, rgba(56, 189, 248, .12), transparent 34%, rgba(52, 211, 153, .10) 72%, transparent 100%),
      linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px); background-size:auto,44px 44px,44px 44px; }}
    main {{ position:relative; max-width: 1240px; margin: 0 auto; padding: 34px 18px 56px; }}
    .hero {{ display:grid; grid-template-columns: 1fr auto; gap:22px; align-items:center; border:1px solid #263754; background:rgba(13, 20, 36, .88); border-radius: 8px; padding: 28px; box-shadow:0 24px 70px rgba(0,0,0,.35); }}
    .brand {{ color:#67e8f9; font-weight:800; letter-spacing:.14em; font-size:12px; text-transform:uppercase; }}
    h1 {{ margin:.4rem 0 .65rem; font-size:clamp(30px, 5vw, 58px); line-height:1.02; letter-spacing:0; }}
    h2 {{ margin:0 0 14px; font-size:18px; }}
    p {{ color:#b6c2d6; line-height:1.6; }}
    .status {{ display:inline-flex; padding:7px 11px; border-radius:999px; font-size:12px; font-weight:800; text-transform:uppercase; }}
    .pass {{ color:#06281a; background:#75f0ae; }}
    .fail {{ color:#3c0606; background:#ffa4a4; }}
    .donut {{ width:142px; height:142px; }}
    .donut text {{ fill:#edf3ff; font-size:22px; font-weight:800; text-anchor:middle; dominant-baseline:middle; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin:18px 0; }}
    .metric, .panel {{ border:1px solid #263754; background:rgba(15,23,42,.82); border-radius:8px; }}
    .metric {{ padding:16px; }}
    .metric span {{ display:block; color:#8fa1ba; font-size:12px; }}
    .metric strong {{ display:block; margin-top:6px; font-size:28px; }}
    .panel {{ padding:18px; margin-top:16px; }}
    .timeline {{ display:grid; grid-template-columns:repeat({max(len(steps), 1)}, minmax(34px,1fr)); gap:6px; }}
    .tick {{ height:14px; border-radius:999px; background:#ef4444; }}
    .tick.pass-bar {{ background:linear-gradient(90deg,#34d399,#67e8f9); }}
    .steps {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; margin-top:16px; }}
    .step {{ overflow:hidden; border:1px solid #263754; border-radius:8px; background:#0b1220; }}
    .step-header {{ display:flex; justify-content:space-between; gap:12px; padding:14px 14px 10px; }}
    .step-title {{ font-weight:800; }}
    .step small {{ color:#8fa1ba; }}
    .message {{ padding:0 14px 14px; color:#cbd5e1; font-size:13px; line-height:1.55; }}
    .evidence {{ display:block; border-top:1px solid #263754; background:#020617; }}
    .evidence img {{ display:block; width:100%; height:250px; object-fit:cover; object-position:top left; }}
    code {{ color:#bfdbfe; word-break:break-word; }}
    .empty {{ border:1px dashed #385273; border-radius:8px; padding:24px; color:#8fa1ba; text-align:center; }}
    @media (max-width: 720px) {{ .hero {{ grid-template-columns:1fr; }} .donut {{ width:116px; height:116px; }} }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <div>
      <div class="brand">HINSA AI Evidence Report</div>
      <h1>Autonomous Browser Test</h1>
      <span class="status {status_class}">{escape(run.status)}</span>
      <p>{escape(run.prompt)}</p>
    </div>
    <svg class="donut" viewBox="0 0 140 140" role="img" aria-label="Pass rate">
      <circle cx="70" cy="70" r="{radius}" fill="none" stroke="#1e293b" stroke-width="16" />
      <circle cx="70" cy="70" r="{radius}" fill="none" stroke="#5eead4" stroke-width="16" stroke-linecap="round"
        stroke-dasharray="{dash} {circumference}" transform="rotate(-90 70 70)" />
      <text x="70" y="70">{pass_percent}%</text>
    </svg>
  </section>
  <section class="grid">
    <div class="metric"><span>Total steps</span><strong>{len(steps)}</strong></div>
    <div class="metric"><span>Passed</span><strong>{passed}</strong></div>
    <div class="metric"><span>Failed</span><strong>{failed}</strong></div>
    <div class="metric"><span>Duration</span><strong>{escape(duration)}</strong></div>
    <div class="metric"><span>Browser</span><strong>{escape(run.browser)}</strong></div>
  </section>
  <section class="panel">
    <h2>Execution Timeline</h2>
    <div class="timeline">{timeline}</div>
  </section>
  <section class="panel">
    <h2>Step Evidence</h2>
    <div class="steps">{step_cards}</div>
  </section>
</main>
</body>
</html>"""

    def _render_step_card(self, step: TestStepResult) -> str:
        screenshot = '<div class="empty">No screenshot captured for this step.</div>'
        if step.screenshot_path:
            filename = Path(step.screenshot_path).name
            screenshot = f'<a class="evidence" href="/static/screenshots/{filename}"><img src="/static/screenshots/{filename}" alt="Evidence for step {step.step_index}" /></a>'

        status_class = "pass" if step.status == "passed" else "fail"
        value = escape(json.dumps(step.value, ensure_ascii=False)) if step.value is not None else ""
        return f"""<article class="step">
  <div class="step-header">
    <div>
      <div class="step-title">Step {step.step_index}: <code>{escape(step.action)}</code></div>
      <small>{escape(step.target or "")} {value}</small>
    </div>
    <span class="status {status_class}">{escape(step.status)}</span>
  </div>
  <div class="message">{escape(step.message)}<br><small>{step.duration_ms}ms</small></div>
  {screenshot}
</article>"""

    def _render_timeline_bar(self, step: TestStepResult) -> str:
        class_name = "tick pass-bar" if step.status == "passed" else "tick"
        return f'<div class="{class_name}" title="Step {step.step_index}: {escape(step.status)}"></div>'

    @staticmethod
    def _duration_label(run: TestRun) -> str:
        if not run.started_at or not run.ended_at:
            return "n/a"
        started_at = run.started_at
        ended_at = run.ended_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if ended_at.tzinfo is None:
            ended_at = ended_at.replace(tzinfo=timezone.utc)
        seconds = max(0, int((ended_at - started_at).total_seconds()))
        return f"{seconds}s"

    @staticmethod
    def _empty_state() -> str:
        return '<div class="empty">No steps were recorded. The planner likely failed before browser execution.</div>'


report_generator = ReportGenerator()
