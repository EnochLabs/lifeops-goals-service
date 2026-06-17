"""
FastAPI dependencies for authentication and authorisation.

Usage:
    @router.post("/goals")
    async def create_goal(user: CurrentUser = Depends(get_current_user)):
        ...

    @router.post("/goals/{id}/decompose")
    async def decompose(user: CurrentUser = Depends(require_plan("BASIC"))):
        ...
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict

from fastapi import Depends, Header
from loguru import logger

from app.config.settings import settings
from app.constants.plans import PlanTier
from app.core.exceptions import ForbiddenError, PlanFeatureLockedError, UnauthenticatedError
from app.core.security.token_validator import validate_token

PLAN_RANK: Dict[str, int] = {
    PlanTier.FREE: 0,
    PlanTier.BASIC: 1,
    PlanTier.PRO: 2,
    PlanTier.MAX: 3,
}


@dataclass
class CurrentUser:
    """Lightweight user context extracted from the validated JWT."""

    user_id: str
    email: str
    role: str
    plan: str
    plan_expires: str | None


async def get_current_user(authorization: str = Header(...)) -> CurrentUser:
    """
    Extract and validate Bearer token from Authorization header.
    Delegates validation to Auth Service (with Redis caching).
    """
    if not authorization.startswith("Bearer "):
        raise UnauthenticatedError()

    token = authorization.removeprefix("Bearer ")

    ctx: Dict[str, Any] = await validate_token(token)

    return CurrentUser(
        user_id=ctx["user_id"],
        email=ctx.get("email", ""),
        role=ctx.get("role", "USER"),
        plan=ctx.get("plan", PlanTier.FREE),
        plan_expires=ctx.get("plan_expires"),
    )


def require_plan(minimum_plan: str) -> Callable:
    """
    Dependency factory — gates a route behind a minimum subscription plan.

    Usage:
        Depends(require_plan("BASIC"))
    """

    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        user_rank = PLAN_RANK.get(user.plan, 0)
        required_rank = PLAN_RANK.get(minimum_plan, 1)
        if user_rank < required_rank:
            raise PlanFeatureLockedError("this feature", minimum_plan)
        return user

    return _check


async def get_internal_caller(x_internal_key: str = Header(...)) -> None:
    """
    Validates that an inbound request is from a trusted internal service.
    Used on /internal/* routes.
    """
    if x_internal_key != settings.INTERNAL_API_KEY:
        raise ForbiddenError("Invalid internal API key.")
