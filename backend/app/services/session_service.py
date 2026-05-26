from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import safe_session_name
from app.database.models import BrowserSession


class SessionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_sessions(self) -> list[BrowserSession]:
        result = await self.db.execute(select(BrowserSession).order_by(BrowserSession.created_at.desc()))
        return list(result.scalars().all())

    async def get_session_state_path(self, session_id: str | None) -> str | None:
        if not session_id:
            return None
        session = await self.db.get(BrowserSession, session_id)
        if not session:
            raise ValueError(f"Browser session {session_id} was not found")
        session.last_used_at = datetime.now(timezone.utc)
        await self.db.commit()
        return session.storage_state_path

    async def prepare_save_path(self, session_name: str | None, browser: str) -> tuple[str | None, str | None]:
        if not session_name:
            return None, None
        safe_name = safe_session_name(session_name)
        session_id = f"{browser}-{safe_name}"
        path = settings.SESSIONS_DIR / f"{session_id}.json"
        return session_id, str(path)

    async def upsert_session(self, session_id: str, name: str, browser: str, storage_state_path: str) -> BrowserSession:
        existing = await self.db.get(BrowserSession, session_id)
        now = datetime.now(timezone.utc)
        if existing:
            existing.name = name
            existing.browser = browser
            existing.storage_state_path = storage_state_path
            existing.last_used_at = now
            await self.db.commit()
            return existing

        session = BrowserSession(
            id=session_id,
            name=name,
            browser=browser,
            storage_state_path=storage_state_path,
            last_used_at=now,
        )
        self.db.add(session)
        await self.db.commit()
        return session

    async def delete_session(self, session_id: str) -> bool:
        session = await self.db.get(BrowserSession, session_id)
        if not session:
            return False
        path = Path(session.storage_state_path)
        await self.db.delete(session)
        await self.db.commit()
        if path.exists():
            path.unlink()
        return True

