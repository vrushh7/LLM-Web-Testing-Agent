from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from app.core.config import settings
from app.core.paths import secure_join
from app.services.test_service import test_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{run_id}", response_class=HTMLResponse)
async def view_report(run_id: str) -> HTMLResponse:
    run = await test_service.get_run(run_id)
    if not run or not run.report_path:
        raise HTTPException(status_code=404, detail="Report not found")
    path = Path(run.report_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report file missing")
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.get("/{run_id}/download")
async def download_report(run_id: str) -> FileResponse:
    run = await test_service.get_run(run_id)
    if not run or not run.report_path:
        raise HTTPException(status_code=404, detail="Report not found")
    path = secure_join(settings.REPORTS_DIR, Path(run.report_path).name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report file missing")
    return FileResponse(path, media_type="text/html", filename=f"{run_id}-report.html")

