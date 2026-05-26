from fastapi import APIRouter, HTTPException, Request

from app.schemas.test import RunQueuedResponse, TestRunCreate, TestRunRead
from app.services.serializers import serialize_run
from app.services.test_service import test_service

router = APIRouter(prefix="/tests", tags=["tests"])


@router.post("/run", response_model=RunQueuedResponse, status_code=202)
async def run_test(payload: TestRunCreate, request: Request) -> dict:
    run = await test_service.create_run(payload)
    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    websocket_url = f"{ws_scheme}://{request.url.netloc}/ws/runs/{run.id}"
    return {"run_id": run.id, "status": run.status, "websocket_url": websocket_url}


@router.get("", response_model=list[TestRunRead])
async def list_runs(limit: int = 30) -> list[dict]:
    runs = await test_service.list_runs(limit=max(1, min(limit, 100)))
    return [serialize_run(run, include_steps=False) for run in runs]


@router.get("/{run_id}", response_model=TestRunRead)
async def get_run(run_id: str) -> dict:
    run = await test_service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return serialize_run(run)

