"""
Internal endpoint consumed by other LifeOps micro-services to check
whether a user has access to a specific goal (ownership + plan gating).

POST /internal/check-access
Headers: X-Internal-Key: <INTERNAL_API_KEY>
Body:    { "user_id": "...", "goal_id": "..." }
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.dependencies.auth import get_internal_caller

router = APIRouter(prefix="/internal", tags=["Internal"])


class AccessCheckRequest(BaseModel):
    user_id: str
    goal_id: str


class AccessCheckResponse(BaseModel):
    allowed: bool
    reason: str | None = None


@router.post(
    "/check-access",
    response_model=AccessCheckResponse,
    dependencies=[Depends(get_internal_caller)],
)
async def check_access(body: AccessCheckRequest) -> AccessCheckResponse:
    """
    Returns whether `user_id` owns `goal_id`.
    Populated once GoalRepository is implemented.
    """
    from app.repositories.goal_repository import GoalRepository  # late import

    goal = await GoalRepository.get_by_id_raw(body.goal_id)
    if not goal:
        return AccessCheckResponse(allowed=False, reason="goal_not_found")
    if str(goal.get("user_id")) != body.user_id:
        return AccessCheckResponse(allowed=False, reason="not_owner")
    return AccessCheckResponse(allowed=True)
