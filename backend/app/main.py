import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.api.websocket import router as websocket_router
from app.automation.browser_pool import browser_pool
from app.core.config import settings
from app.core.paths import ensure_storage_dirs
from app.core.rate_limit import InMemoryRateLimitMiddleware
from app.database.session import init_db


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_storage_dirs()
    await init_db()
    yield
    await browser_pool.close()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(InMemoryRateLimitMiddleware, requests_per_minute=settings.RATE_LIMIT_PER_MINUTE)

app.include_router(api_router, prefix=settings.API_PREFIX)
app.include_router(websocket_router)
app.mount("/static/screenshots", StaticFiles(directory=settings.SCREENSHOTS_DIR, check_dir=False), name="screenshots")
app.mount("/static/reports", StaticFiles(directory=settings.REPORTS_DIR, check_dir=False), name="reports")


@app.get("/")
async def root() -> dict:
    return {
        "name": settings.APP_NAME,
        "status": "ready",
        "docs": "/docs",
        "api": settings.API_PREFIX,
    }


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
