from pathlib import Path

from app.database.models import BrowserSession, TestRun, TestStepResult


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def screenshot_url(path: str | None) -> str | None:
    if not path:
        return None
    return f"/static/screenshots/{Path(path).name}"


def report_url(path: str | None, run_id: str) -> str | None:
    return f"/api/reports/{run_id}" if path else None


def serialize_step(step: TestStepResult) -> dict:
    return {
        "id": step.id,
        "step_index": step.step_index,
        "action": step.action,
        "target": step.target,
        "value": step.value,
        "status": step.status,
        "message": step.message,
        "screenshot_url": screenshot_url(step.screenshot_path),
        "duration_ms": step.duration_ms,
        "started_at": step.started_at.isoformat(),
        "ended_at": step.ended_at.isoformat(),
    }


def serialize_run(run: TestRun, include_steps: bool = True) -> dict:
    return {
        "id": run.id,
        "prompt": run.prompt,
        "base_url": run.base_url,
        "status": run.status,
        "browser": run.browser,
        "session_id": run.session_id,
        "total_steps": run.total_steps,
        "passed_steps": run.passed_steps,
        "failed_steps": run.failed_steps,
        "report_url": report_url(run.report_path, run.id),
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat(),
        "started_at": _iso(run.started_at),
        "ended_at": _iso(run.ended_at),
        "steps": [serialize_step(step) for step in run.steps] if include_steps else [],
    }


def serialize_session(session: BrowserSession) -> dict:
    return {
        "id": session.id,
        "name": session.name,
        "browser": session.browser,
        "created_at": session.created_at.isoformat(),
        "last_used_at": _iso(session.last_used_at),
    }

