from pathlib import Path

from app.core.config import settings


def ensure_storage_dirs() -> None:
    """Create runtime folders used by screenshots, reports, sessions, and SQLite."""

    for path in [
        Path("./data"),
        settings.STORAGE_DIR,
        settings.REPORTS_DIR,
        settings.SCREENSHOTS_DIR,
        settings.SESSIONS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def secure_join(base: Path, filename: str) -> Path:
    """Join a filename to a base directory and prevent path traversal."""

    candidate = (base / filename).resolve()
    root = base.resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError("Unsafe file path requested")
    return candidate

