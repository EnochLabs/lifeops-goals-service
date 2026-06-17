"""
Health check endpoints.

GET /health        → basic liveness (always 200 if process is up)
GET /health/live   → same as above
GET /health/ready  → deep readiness: checks MongoDB + Redis
"""

from fastapi import APIRouter
from loguru import logger

from app.config.database import client as mongo_client
from app.config.redis import redis_client
from app.config.settings import settings

router = APIRouter(tags=["Health"])


@router.get("/health", include_in_schema=False)
@router.get("/health/live", include_in_schema=False)
async def liveness():
    return {"status": "ok", "service": settings.APP_NAME}


@router.get("/health/ready", include_in_schema=False)
async def readiness():
    checks = {}
    ok = True

    # MongoDB
    try:
        await mongo_client.admin.command("ping")
        checks["mongodb"] = "ok"
    except Exception as exc:
        logger.error(f"MongoDB health check failed: {exc}")
        checks["mongodb"] = "error"
        ok = False

    # Redis
    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.error(f"Redis health check failed: {exc}")
        checks["redis"] = "error"
        ok = False

    return {
        "status": "ready" if ok else "degraded",
        "service": settings.APP_NAME,
        "checks": checks,
    }
