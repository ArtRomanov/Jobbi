from fastapi import APIRouter

from app.api.v1.applications import router as applications_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.cvs import router as cvs_router
from app.api.v1.health import router as health_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.users import router as users_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(health_router)
v1_router.include_router(auth_router)
v1_router.include_router(users_router)
v1_router.include_router(applications_router)
v1_router.include_router(cvs_router)
v1_router.include_router(chat_router)
v1_router.include_router(metrics_router)