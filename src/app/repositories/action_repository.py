"""
Action Repository — data access layer for Action documents.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional


class ActionRepository:

    @staticmethod
    async def count_completed_since(goal_id: str, since: datetime) -> int:
        from app.models.action import Action
        from app.constants.goals import ActionStatus
        from beanie import PydanticObjectId

        return await Action.find(
            Action.goal_id == PydanticObjectId(goal_id),
            Action.status == ActionStatus.COMPLETED,
            Action.completed_at >= since,
        ).count()

    @staticmethod
    async def count_total_in_window(goal_id: str, since: datetime) -> int:
        from app.models.action import Action
        from beanie import PydanticObjectId

        return await Action.find(
            Action.goal_id == PydanticObjectId(goal_id),
            Action.created_at >= since,
        ).count()

    @staticmethod
    async def list_overdue_habits(goal_id: str, as_of: datetime) -> List[Any]:
        from app.models.action import Action
        from app.constants.goals import ActionType, ActionStatus
        from beanie import PydanticObjectId

        return await Action.find(
            Action.goal_id == PydanticObjectId(goal_id),
            Action.action_type == ActionType.HABIT,
            Action.status == ActionStatus.PENDING,
            Action.next_due <= as_of,
        ).to_list()

    @staticmethod
    async def create_next_recurrence(habit: Any, as_of: datetime) -> Optional[Any]:
        """Clone a habit action for the next recurrence window."""
        # Full implementation added when Action model is finalised
        return None
