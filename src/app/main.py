"""
LifeOps Goals Service — FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.internal.check_access import router as internal_router
from app.config.settings import settings
from app.lifespan import lifespan
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.rate_limit_middleware import GlobalRateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ── Middleware (order matters — outermost is applied last on response) ──
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(GlobalRateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(o) for o in settings.CORS_ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Internal-Key"],
)

# ── Routers ────────────────────────────────────────────────────
app.include_router(health_router)
app.include_router(internal_router)

# Feature routers will be registered here as they are built:
# from app.api.v1.goals import router as goals_router
# from app.api.v1.phases import router as phases_router
# from app.api.v1.actions import router as actions_router
# app.include_router(goals_router, prefix="/api/v1")
# app.include_router(phases_router, prefix="/api/v1")
# app.include_router(actions_router, prefix="/api/v1")
