"""
Action Repository — data access layer for Action documents.
"""

from __future__ import annotations

from datetime import datetime, timedelta
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
    def _next_date_for_pattern(
        pattern: str, days_of_week: List[int], current: datetime
    ) -> datetime:
        """
        Pure date arithmetic — compute the next occurrence from `current`.

        DAILY      : +1 day
        WEEKDAYS   : skip to Mon if Fri/Sat/Sun → +3/+2/+1; otherwise +1
        WEEKENDS   : skip to Sat from Mon–Fri → appropriate offset; Sun → +6
        WEEKLY     : +7 days
        BIWEEKLY   : +14 days
        MONTHLY    : +1 calendar month
        CUSTOM     : next day-of-week in `days_of_week` (weekday indices, 0=Mon)
        """
        from dateutil.relativedelta import relativedelta

        from app.constants.goals import RecurrencePattern

        if pattern == RecurrencePattern.DAILY:
            return current + timedelta(days=1)

        if pattern == RecurrencePattern.WEEKDAYS:
            # Mon=0 … Sun=6.  Fri→+3, Sat→+2, otherwise +1.
            wd = current.weekday()
            if wd == 4:  # Friday
                return current + timedelta(days=3)
            if wd == 5:  # Saturday
                return current + timedelta(days=2)
            if wd == 6:  # Sunday
                return current + timedelta(days=1)
            return current + timedelta(days=1)

        if pattern == RecurrencePattern.WEEKENDS:
            # Next Sat from Mon=+5, Tue=+4, Wed=+3, Thu=+2, Fri=+1, Sat=+7, Sun=+6
            wd = current.weekday()
            if wd == 5:  # Saturday → next Sat
                return current + timedelta(days=7)
            if wd == 6:  # Sunday → next Sat
                return current + timedelta(days=6)
            # Mon–Fri: days until Saturday = 5 - wd
            return current + timedelta(days=5 - wd)

        if pattern == RecurrencePattern.WEEKLY:
            return current + timedelta(weeks=1)

        if pattern == RecurrencePattern.BIWEEKLY:
            return current + timedelta(weeks=2)

        if pattern == RecurrencePattern.MONTHLY:
            result: datetime = current + relativedelta(months=1)  # type: ignore[assignment]
            return result

        if pattern == RecurrencePattern.CUSTOM:
            if not days_of_week:
                return current + timedelta(days=1)
            # Find the nearest future day matching one of days_of_week (0=Mon)
            for offset in range(1, 8):
                candidate = current + timedelta(days=offset)
                if candidate.weekday() in days_of_week:
                    return candidate
            # Fallback — should not happen since we checked 1–7 ahead
            return current + timedelta(days=7)

        # Unknown pattern — safe fallback
        return current + timedelta(days=1)

    @staticmethod
    async def create_next_recurrence(habit: Any, as_of: datetime) -> Optional[Any]:
        """Clone a habit action for the next recurrence window.

        Creates a new independent Action linked to the template via parent_action_id.
        Increments the template's generation_count and rolls forward next_due.

        The template action itself is *never* completed — it is the schedule anchor.
        Each generated instance is a plain PENDING Action the user can check off.
        """
        from app.constants.goals import ActionStatus
        from app.models.action import Action

        if not habit.recurrence:
            return None

        recurrence = habit.recurrence
        # Base date: last known next_due, or as_of if this is the first generation.
        base = habit.next_due if habit.next_due else as_of

        next_date = ActionRepository._next_date_for_pattern(
            pattern=recurrence.pattern,
            days_of_week=list(recurrence.days_of_week or []),
            current=base,
        )

        # Create the independent instance (no recurrence config of its own)
        new_action = Action(
            goal_id=habit.goal_id,
            phase_id=habit.phase_id,
            user_id=habit.user_id,
            parent_action_id=habit.id,
            title=habit.title,
            description=habit.description,
            action_type=habit.action_type,
            status=ActionStatus.PENDING,
            order=habit.order,
            due_date=next_date,
            next_due=None,
            recurrence=None,
            estimated_minutes=habit.estimated_minutes,
            contributes_value=habit.contributes_value,
            tags=list(habit.tags or []),
        )
        await new_action.insert()

        # Roll the template forward
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
    async def list_for_user_due_today(user_id: str, as_of: datetime) -> List[Any]:
        """Return all high-effort actions due today or overdue for a user.

        Used by the health-event auto-rescheduler (GS-3.4).
        """
        from beanie.operators import In

        from app.constants.goals import ActionStatus, GoalStatus
        from app.models.goal import Goal

        # Resolve active goal IDs for the user
        active_goals = await Goal.find(
            Goal.user_id == PydanticObjectId(user_id),
            In(Goal.status, [GoalStatus.ACTIVE, GoalStatus.RESUMED]),
        ).to_list()
        goal_ids = [g.id for g in active_goals]
        if not goal_ids:
            return []

        today_start = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = as_of.replace(hour=23, minute=59, second=59, microsecond=999999)

        return cast(
            List[Any],
            await Action.find(
                In(Action.goal_id, goal_ids),
                In(Action.status, [ActionStatus.PENDING, ActionStatus.IN_PROGRESS]),
                Action.due_date >= today_start,
                Action.due_date <= today_end,
            ).to_list(),
        )

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
    async def list_completed_for_goal_in_window(
        goal_id: str, since: datetime, until: datetime
    ) -> List[Any]:
        """Return completed actions for a goal within [since, until].

        Used by habitGrid and momentum history queries (GS-3.2, GS-3.5).
        """
        from app.constants.goals import ActionStatus

        return cast(
            List[Any],
            await Action.find(
                Action.goal_id == PydanticObjectId(goal_id),
                Action.status == ActionStatus.COMPLETED,
                Action.completed_at >= since,
                Action.completed_at <= until,
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
