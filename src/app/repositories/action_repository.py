"""
Action Repository — data access layer for Action documents.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional, cast

from beanie import PydanticObjectId

from app.models.action import Action


class ActionRepository:

    @staticmethod
    async def count_completed_since(goal_id: str, since: datetime) -> int:
        from beanie import PydanticObjectId

        from app.constants.goals import ActionStatus
        from app.models.action import Action

        return cast(
            int,
            await Action.find(
                Action.goal_id == PydanticObjectId(goal_id),
                Action.status == ActionStatus.COMPLETED,
                Action.completed_at >= since,
            ).count(),
        )

    @staticmethod
    async def count_total_in_window(goal_id: str, since: datetime) -> int:
        from beanie import PydanticObjectId

        from app.models.action import Action

        return cast(
            int,
            await Action.find(
                Action.goal_id == PydanticObjectId(goal_id),
                Action.created_at >= since,
            ).count(),
        )

    @staticmethod
    async def list_overdue_habits(goal_id: str, as_of: datetime) -> List[Any]:
        from beanie import PydanticObjectId

        from app.constants.goals import ActionStatus, ActionType
        from app.models.action import Action

        return cast(
            List[Any],
            await Action.find(
                Action.goal_id == PydanticObjectId(goal_id),
                Action.action_type == ActionType.HABIT,
                Action.status == ActionStatus.PENDING,
                Action.next_due <= as_of,
            ).to_list(),
        )

    @staticmethod
    async def create_next_recurrence(habit: Any, as_of: datetime) -> Optional[Any]:
        """Clone a habit action for the next recurrence window.
        
        Creates a new independent Action linked to the template via parent_action_id.
        Increments the template's generation_count and rolls forward next_due.
        """
        from datetime import timedelta
        from dateutil.relativedelta import relativedelta
        
        from app.constants.goals import ActionStatus, RecurrencePattern
        from app.models.action import Action, Recurrence

        if not habit.recurrence:
            return None

        recurrence = habit.recurrence
        next_date = habit.next_due

        # Calculate the next due date based on recurrence pattern
        if recurrence.pattern == RecurrencePattern.DAILY:
            next_date = next_date + timedelta(days=1) if next_date else as_of + timedelta(days=1)
        elif recurrence.pattern == RecurrencePattern.WEEKLY:
            next_date = next_date + timedelta(weeks=1) if next_date else as_of + timedelta(weeks=1)
        elif recurrence.pattern == RecurrencePattern.BIWEEKLY:
            next_date = next_date + timedelta(weeks=2) if next_date else as_of + timedelta(weeks=2)
        elif recurrence.pattern == RecurrencePattern.MONTHLY:
            next_date = next_date + relativedelta(months=1) if next_date else as_of + relativedelta(months=1)
        elif recurrence.pattern == RecurrencePattern.CUSTOM:
            # For CUSTOM pattern, find the next matching day of week
            if recurrence.days_of_week:
                current_date = next_date if next_date else as_of
                days_ahead = 0
                while days_ahead < 7:
                    check_date = current_date + timedelta(days=days_ahead)
                    if check_date.weekday() in recurrence.days_of_week:
                        next_date = check_date
                        break
                    days_ahead += 1
                else:
                    # No matching day found in next week, wrap around
                    next_date = current_date + timedelta(days=7)

        # Create the new action instance
        new_action = Action(
            goal_id=habit.goal_id,
            phase_id=habit.phase_id,
            user_id=habit.user_id,
            parent_action_id=habit.id,  # Link back to template
            title=habit.title,
            description=habit.description,
            action_type=habit.action_type,
            status=ActionStatus.PENDING,
            order=habit.order,
            due_date=next_date,
            next_due=None,  # Instances don't have next_due
            recurrence=None,  # Only the template has recurrence
            estimated_minutes=habit.estimated_minutes,
            contributes_value=habit.contributes_value,
            tags=habit.tags,
        )
        await new_action.insert()

        # Update the template's next_due and generation count
        habit.next_due = next_date
        habit.recurrence.generation_count += 1
        habit.updated_at = datetime.utcnow()
        await habit.save()

        return new_action

    @staticmethod
    async def get_by_id(action_id: str) -> Optional[Any]:
        """Retrieve an action by ID."""
        return await Action.get(PydanticObjectId(action_id))

    @staticmethod
    async def list_for_phase(phase_id: str) -> List[Any]:
        """Return all actions for a phase, ordered."""
        return cast(
            List[Any],
            await Action.find(Action.phase_id == PydanticObjectId(phase_id))
            .sort([(Action.order, 1)])
            .to_list(),
        )

    @staticmethod
    async def list_for_goal(goal_id: str, status: Optional[str] = None) -> List[Any]:
        """Return all actions for a goal, optionally filtered by status."""
        query = Action.find(Action.goal_id == PydanticObjectId(goal_id))
        if status:
            query = query.find(Action.status == status)
        return cast(List[Any], await query.sort([(Action.due_date, 1)]).to_list())

    @staticmethod
    async def list_overdue(goal_id: str, as_of: datetime) -> List[Any]:
        """Return all non-completed actions due before as_of date."""
        from app.constants.goals import ActionStatus

        return cast(
            List[Any],
            await Action.find(
                Action.goal_id == PydanticObjectId(goal_id),
                Action.status != ActionStatus.COMPLETED,
                Action.due_date < as_of,
            ).to_list(),
        )

    @staticmethod
    async def update_status(action_id: str, new_status: str) -> Optional[Any]:
        """Update an action's status."""
        action = await Action.get(PydanticObjectId(action_id))
        if not action:
            return None

        action.status = new_status
        action.updated_at = datetime.utcnow()

        from app.constants.goals import ActionStatus

        if new_status == ActionStatus.COMPLETED:
            action.completed_at = action.completed_at or datetime.utcnow()

        await action.save()
        return action

    @staticmethod
    async def update_due_date(action_id: str, new_due_date: datetime) -> Optional[Any]:
        """Reschedule an action to a new due date."""
        action = await Action.get(PydanticObjectId(action_id))
        if not action:
            return None

        action.due_date = new_due_date
        action.updated_at = datetime.utcnow()
        await action.save()
        return action

    @staticmethod
    async def count_for_phase(phase_id: str) -> int:
        """Count total actions in a phase."""
        return cast(
            int,
            await Action.find(Action.phase_id == PydanticObjectId(phase_id)).count(),
        )

    @staticmethod
    async def delete_all_for_goal(goal_id: str) -> None:
        """Delete all actions for a goal (cascade)."""
        await Action.find(Action.goal_id == PydanticObjectId(goal_id)).delete()

