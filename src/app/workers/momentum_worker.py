"""
Momentum Recalculation Worker.

Runs on a configurable interval (default: every 6 hours).
For every ACTIVE goal, recomputes the momentum score based on the last
MOMENTUM_WINDOW_DAYS days of action completions, then fires
goal.momentum_low or goal.momentum_recovered events as needed.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from loguru import logger

from app.config.settings import settings
from app.constants.goals import GoalStatus
from app.constants.limits import MOMENTUM_LOW_THRESHOLD, MOMENTUM_WINDOW_DAYS
from app.events.event_types import GoalEvents
from app.events.publisher import publish_event

_INTERVAL_SECONDS = settings.MOMENTUM_RECALC_INTERVAL_HOURS * 3600


async def recalculate_momentum_for_all() -> None:
    """
    Loads all ACTIVE goals and recomputes their momentum scores.
    Implemented fully once Goal and Action models are in place.
    """
    from app.repositories.goal_repository import GoalRepository
    from app.repositories.action_repository import ActionRepository

    since = datetime.now(UTC) - timedelta(days=MOMENTUM_WINDOW_DAYS)
    active_goals = await GoalRepository.list_by_status(GoalStatus.ACTIVE)

    for goal in active_goals:
        try:
            goal_id = str(goal.id)
            completions = await ActionRepository.count_completed_since(goal_id, since)
            total = await ActionRepository.count_total_in_window(goal_id, since)

            score = (completions / total * 100) if total > 0 else 0.0

            was_low = goal.momentum_score is not None and goal.momentum_score < MOMENTUM_LOW_THRESHOLD
            is_low = score < MOMENTUM_LOW_THRESHOLD

            await GoalRepository.update_momentum(goal_id, score)

            if is_low and not was_low:
                await publish_event(
                    GoalEvents.MOMENTUM_LOW,
                    {"goal_id": goal_id, "user_id": str(goal.user_id), "score": score},
                )
            elif not is_low and was_low:
                await publish_event(
                    GoalEvents.MOMENTUM_RECOVERED,
                    {"goal_id": goal_id, "user_id": str(goal.user_id), "score": score},
                )
        except Exception as exc:
            logger.error(f"Momentum recalc failed for goal {goal.id}: {exc}")


async def run_momentum_recalc() -> None:
    """Infinite loop — runs the momentum recalculation on the configured interval."""
    logger.info(
        f"Momentum worker started (interval: {settings.MOMENTUM_RECALC_INTERVAL_HOURS}h)"
    )
    while True:
        try:
            await asyncio.sleep(_INTERVAL_SECONDS)
            logger.info("Running momentum recalculation...")
            await recalculate_momentum_for_all()
            logger.info("Momentum recalculation complete.")
        except asyncio.CancelledError:
            logger.info("Momentum worker cancelled.")
            break
        except Exception as exc:
            logger.error(f"Momentum worker error: {exc}")
