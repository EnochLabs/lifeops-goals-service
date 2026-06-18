"""
LifeOps Goals Service — FastAPI application entry point.
"""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from app.api.health import router as health_router
from app.api.internal.check_access import router as internal_router
from app.config.settings import settings
from app.graphql.schema import schema
from app.lifespan import lifespan
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.rate_limit_middleware import GlobalRateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware


async def get_graphql_context(request: Request, response: Response):  # type: ignore[return]
    """
    Build the Strawberry context for every GraphQL request.

    Resolves the current user from the Authorization header using the
    same token validator the REST layer uses — but lazily, so queries
    that don't require auth (future: goalTemplates) don't pay the
    network round-trip cost.
    """
    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ")

    user = None
    if token:
        try:
            from app.core.dependencies.auth import CurrentUser
            from app.core.security.token_validator import validate_token

            ctx = await validate_token(token)
            from app.constants.plans import PlanTier

            user = CurrentUser(
                user_id=ctx["user_id"],
                email=ctx.get("email", ""),
                role=ctx.get("role", "USER"),
                plan=ctx.get("plan", PlanTier.FREE),
                plan_expires=ctx.get("plan_expires"),
            )
        except Exception:
            # Unauthenticated — mutations will raise 401 when they need a user
            pass

    return {"request": request, "response": response, "user": user}


def _build_cors_origins() -> list:  # type: ignore[type-arg]
    raw = settings.CORS_ALLOWED_ORIGINS
    origins = raw if isinstance(raw, list) else [raw]
    return [str(o).rstrip("/") for o in origins]


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
    allow_origins=_build_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Internal-Key"],
)

# ── GraphQL ────────────────────────────────────────────────────
graphql_router = GraphQLRouter(
    schema,
    context_getter=get_graphql_context,
    graphql_ide="graphiql" if settings.DEBUG else None,
)
app.include_router(graphql_router, prefix="/graphql")

# ── REST Routers ───────────────────────────────────────────────
app.include_router(health_router)
app.include_router(internal_router)
