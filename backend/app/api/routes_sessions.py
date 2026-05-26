from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.schemas.test import SessionRead
from app.services.serializers import serialize_session
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionRead])
async def list_sessions(db: AsyncSession = Depends(get_db)) -> list[dict]:
    sessions = await SessionService(db).list_sessions()
    return [serialize_session(session) for session in sessions]


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)) -> None:
    deleted = await SessionService(db).delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

