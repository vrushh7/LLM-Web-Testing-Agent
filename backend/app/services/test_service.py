import asyncio
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.ai.orchestrator import AIOrchestrator
from app.automation.engine import EngineOptions, PlaywrightEngine, StepRunResult
from app.core.config import settings
from app.core.security import make_run_id
from app.database.models import TestRun, TestStepResult
from app.database.session import async_session_maker
from app.reports.generator import report_generator
from app.schemas.test import TestRunCreate
from app.services.serializers import screenshot_url
from app.services.session_service import SessionService
from app.services.websocket_manager import websocket_manager


class TestService:
    """Coordinates planning, execution, persistence, reports, and live status."""

    async def create_run(self, payload: TestRunCreate) -> TestRun:
        run = TestRun(
            id=make_run_id(),
            prompt=payload.prompt,
            base_url=payload.base_url,
            status="queued",
            browser=payload.browser.value,
            session_id=payload.session_id,
            save_session_name=payload.save_session_name,
        )
        async with async_session_maker() as db:
            db.add(run)
            await db.commit()
            await db.refresh(run)

        asyncio.create_task(self.execute_run(run.id, payload))
        return run

    async def execute_run(self, run_id: str, payload: TestRunCreate) -> None:
        async with async_session_maker() as db:
            run = await db.get(TestRun, run_id)
            if run is None:
                return

            try:
                run.status = "planning"
                run.started_at = datetime.now(timezone.utc)
                await db.commit()
                await websocket_manager.publish(run_id, "status", "Planning test steps", status="planning")

                workflow_context = await self._recent_workflow_context(db)
                orchestrator = AIOrchestrator(db)
                steps, plan_meta = await orchestrator.plan_steps(payload.prompt, payload.base_url, workflow_context)
                run.total_steps = len(steps)
                run.status = "executing"
                await db.commit()
                await websocket_manager.publish(
                    run_id,
                    "status",
                    f"Executing {len(steps)} planned steps",
                    status="executing",
                    payload=plan_meta,
                )

                session_service = SessionService(db)
                session_state_path = await session_service.get_session_state_path(payload.session_id)
                save_session_id, save_session_path = await session_service.prepare_save_path(
                    payload.save_session_name,
                    payload.browser.value,
                )

                async def on_log(message: str, data: dict | None) -> None:
                    if data and "step" in data:
                        await websocket_manager.publish(
                            run_id,
                            "step_started",
                            message,
                            status=run.status,
                            step_index=data.get("step_index"),
                            payload=data,
                        )
                    await websocket_manager.publish(run_id, "log", message, status=run.status, payload=data or {})

                async def on_step(result: StepRunResult) -> None:
                    await self._persist_step(db, run_id, result)
                    await websocket_manager.publish(
                        run_id,
                        "step_finished",
                        result.message,
                        status=result.status,
                        step_index=result.step_index,
                        payload={
                            "action": result.action,
                            "target": result.target,
                            "duration_ms": result.duration_ms,
                            "screenshot_url": screenshot_url(result.screenshot_path),
                        },
                    )

                engine = PlaywrightEngine(on_log=on_log, on_step=on_step)
                passed, failed = await engine.execute(
                    steps,
                    EngineOptions(
                        run_id=run_id,
                        browser=payload.browser.value,
                        headless=payload.headless,
                        session_state_path=session_state_path,
                        save_session_path=save_session_path,
                        max_retries=payload.max_retries
                        if payload.max_retries is not None
                        else settings.ACTION_RETRIES,
                    ),
                )

                run.passed_steps = passed
                run.failed_steps = failed
                run.status = "passed" if failed == 0 and passed == len(steps) else "failed"
                run.ended_at = datetime.now(timezone.utc)

                if save_session_id and save_session_path and Path(save_session_path).exists():
                    await session_service.upsert_session(
                        save_session_id,
                        payload.save_session_name or save_session_id,
                        payload.browser.value,
                        save_session_path,
                    )

                report_path = await self._generate_report(db, run)
                run.report_path = report_path
                await db.commit()
                await websocket_manager.publish(
                    run_id,
                    "report",
                    "Report generated",
                    status=run.status,
                    payload={"report_url": f"/api/reports/{run_id}"},
                )
                await websocket_manager.publish(run_id, "status", f"Run {run.status}", status=run.status)
            except Exception as exc:
                await db.rollback()
                await self._mark_failed(run_id, str(exc))

    async def _persist_step(self, db, run_id: str, result: StepRunResult) -> None:
        db.add(
            TestStepResult(
                run_id=run_id,
                step_index=result.step_index,
                action=result.action,
                target=result.target,
                value=result.value,
                status=result.status,
                message=result.message,
                screenshot_path=result.screenshot_path,
                duration_ms=result.duration_ms,
                started_at=result.started_at,
                ended_at=result.ended_at,
            )
        )
        await db.commit()

    async def _generate_report(self, db, run: TestRun) -> str:
        result = await db.execute(
            select(TestStepResult)
            .where(TestStepResult.run_id == run.id)
            .order_by(TestStepResult.step_index.asc())
        )
        steps = list(result.scalars().all())
        return report_generator.generate(run, steps)

    async def _recent_workflow_context(self, db) -> str | None:
        result = await db.execute(
            select(TestRun)
            .options(selectinload(TestRun.steps))
            .where(TestRun.status == "passed")
            .order_by(TestRun.ended_at.desc())
            .limit(1)
        )
        run = result.scalar_one_or_none()
        if not run:
            return None

        values = []
        for step in run.steps:
            if step.action in {"open_url", "search", "sort_results", "filter_results", "click"}:
                values.append(f"{step.action}:{step.target or ''}:{step.value or ''}")
        return f"Previous prompt: {run.prompt}. Previous steps: {'; '.join(values[:8])}"

    async def _mark_failed(self, run_id: str, message: str) -> None:
        async with async_session_maker() as db:
            run = await db.get(TestRun, run_id)
            if run:
                run.status = "failed"
                run.error_message = message
                run.ended_at = datetime.now(timezone.utc)
                report_path = await self._generate_report(db, run)
                run.report_path = report_path
                await db.commit()
        await websocket_manager.publish(run_id, "status", message, status="failed")

    async def get_run(self, run_id: str) -> TestRun | None:
        async with async_session_maker() as db:
            result = await db.execute(
                select(TestRun).options(selectinload(TestRun.steps)).where(TestRun.id == run_id)
            )
            return result.scalar_one_or_none()

    async def list_runs(self, limit: int = 30) -> list[TestRun]:
        async with async_session_maker() as db:
            result = await db.execute(
                select(TestRun)
                .options(selectinload(TestRun.steps))
                .order_by(TestRun.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().unique().all())


test_service = TestService()
