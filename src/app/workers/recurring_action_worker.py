"""
Recurring Action Generation Worker.

Runs on a configurable interval (default: every 12 hours).
For every ACTIVE goal, finds HABIT actions whose next_due date has passed
and generates new action instances for the upcoming window.
"""

import asyncio
from datetime import UTC, datetime

from loguru import logger

from app.config.settings import settings
from app.constants.goals import ActionStatus, ActionType, GoalStatus
from app.events.event_types import ActionEvents
from app.events.publisher import publish_event

_INTERVAL_SECONDS = settings.RECURRING_ACTION_GEN_INTERVAL_HOURS * 3600


async def generate_recurring_actions() -> None:
    """
    Find overdue recurring (HABIT) actions and generate new instances.
    Fully implemented once Action and Goal models are in place.
    """
    from app.repositories.action_repository import ActionRepository
    from app.repositories.goal_repository import GoalRepository

    now = datetime.now(UTC)
    active_goals = await GoalRepository.list_by_status(GoalStatus.ACTIVE)

    for goal in active_goals:
        try:
            due_habits = await ActionRepository.list_overdue_habits(str(goal.id), now)
            for habit in due_habits:
                new_action = await ActionRepository.create_next_recurrence(habit, now)
                if new_action:
                    await publish_event(
                        ActionEvents.RECURRING_GENERATED,
                        {
                            "goal_id": str(goal.id),
                            "user_id": str(goal.user_id),
                            "action_id": str(new_action.id),
                            "parent_action_id": str(habit.id),
                        },
                    )
        except Exception as exc:
            logger.error(f"Recurring action gen failed for goal {goal.id}: {exc}")


async def run_recurring_action_gen() -> None:
    """Infinite loop — generates recurring actions on the configured interval."""
    logger.info(
        f"Recurring action worker started (interval: {settings.RECURRING_ACTION_GEN_INTERVAL_HOURS}h)"
    )
    while True:
        try:
            await asyncio.sleep(_INTERVAL_SECONDS)
            logger.info("Generating recurring actions...")
            await generate_recurring_actions()
            logger.info("Recurring action generation complete.")
        except asyncio.CancelledError:
            logger.info("Recurring action worker cancelled.")
            break
        except Exception as exc:
            logger.error(f"Recurring action worker error: {exc}")
