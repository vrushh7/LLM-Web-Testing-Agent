from fastapi import APIRouter

from app.api.routes_reports import router as reports_router
from app.api.routes_sessions import router as sessions_router
from app.api.routes_tests import router as tests_router

api_router = APIRouter()
api_router.include_router(tests_router)
api_router.include_router(sessions_router)
api_router.include_router(reports_router)

