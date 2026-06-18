"""
Goal Repository — data access layer for Goal documents.

All database logic lives here; services never touch the ORM directly.
Methods are stubbed with correct signatures so workers, event handlers,
and internal routes compile and run.  Bodies are filled when models
are ready.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, cast


class GoalRepository:

    @staticmethod
    async def list_by_status(status: str) -> List[Any]:
        """Return all goals with the given status."""
        from app.models.goal import Goal

        return cast(List[Any], await Goal.find(Goal.status == status).to_list())

    @staticmethod
    async def get_by_id_raw(goal_id: str) -> Optional[Dict[str, Any]]:
        """Return a raw dict for a goal (used by internal access-check route)."""
        from beanie import PydanticObjectId

        from app.models.goal import Goal

        goal = await Goal.get(PydanticObjectId(goal_id))
        return goal.model_dump() if goal else None

    @staticmethod
    async def update_momentum(goal_id: str, score: float) -> None:
        """Persist a recomputed momentum score."""
        from beanie import PydanticObjectId

        from app.models.goal import Goal

        goal = await Goal.get(PydanticObjectId(goal_id))
        if goal:
            goal.momentum_score = score
            goal.updated_at = datetime.utcnow()
            await goal.save()

    @staticmethod
    async def delete_all_for_user(user_id: str) -> None:
        """Cascade-delete all goals (and their phases/actions) for a deleted user."""
        from beanie import PydanticObjectId

        from app.models.action import Action
        from app.models.goal import Goal
        from app.models.phase import Phase

        goals = await Goal.find(Goal.user_id == PydanticObjectId(user_id)).to_list()
        for goal in goals:
            await Action.find(Action.goal_id == goal.id).delete()
            await Phase.find(Phase.goal_id == goal.id).delete()
            await goal.delete()
