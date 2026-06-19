"""
Momentum Recalculation Worker.

Runs on a configurable interval (default: every 6 hours).
For every ACTIVE goal, recomputes the momentum score based on the last
MOMENTUM_WINDOW_DAYS days of action completions, then fires
goal.momentum_low or goal.momentum_recovered events as needed.

GS-3.3: Enriched event payloads include goal_title, momentum_score, and
completion_streak so the Notification Service can write compassionate,
specific messages. No "you broke your streak" language — only
low/recovered signals. The recurring-action worker generates new instances
regardless of whether the previous one was missed (no catch-up shame).
"""

import asyncio
from datetime import UTC, datetime, timedelta

from loguru import logger

from app.config.settings import settings
from app.constants.goals import ActionStatus, GoalStatus
from app.constants.limits import MOMENTUM_LOW_THRESHOLD, MOMENTUM_WINDOW_DAYS
from app.events.event_types import GoalEvents
from app.events.publisher import publish_event

_INTERVAL_SECONDS = settings.MOMENTUM_RECALC_INTERVAL_HOURS * 3600


def _compute_completion_streak(completed_dates: list[datetime]) -> int:
    """Count how many consecutive days (ending today) had at least one completion.

    Used for the enriched momentum event payload (GS-3.3).
    This is an *opt-in positive signal* only — never surfaced as a
    "you broke your streak" counter. The streak resets silently; the
    user is not penalised for missing a day.
    """
    if not completed_dates:
        return 0

    today = datetime.now(UTC).date()
    unique_days = sorted(
        {dt.astimezone(UTC).date() if dt.tzinfo else dt.date() for dt in completed_dates},
        reverse=True,
    )

    streak = 0
    expected = today
    for day in unique_days:
        if day == expected:
            streak += 1
            expected = day - timedelta(days=1)
        elif day < expected:
            break  # gap — streak ends (silently)

    return streak


async def recalculate_momentum_for_all() -> None:
    """
    Loads all ACTIVE + RESUMED goals and recomputes their momentum scores.
    RESUMED goals are included because they behave identically to ACTIVE
    for momentum purposes (sprint plan §2.2).
    """
    from beanie.operators import In

    from app.models.action import Action
    from app.models.goal import Goal
    from app.repositories.action_repository import ActionRepository
    from app.repositories.goal_repository import GoalRepository

    since = datetime.now(UTC) - timedelta(days=MOMENTUM_WINDOW_DAYS)

    active_goals = await Goal.find(
        In(Goal.status, [GoalStatus.ACTIVE, GoalStatus.RESUMED])
    ).to_list()

    for goal in active_goals:
        try:
            goal_id = str(goal.id)
            completions = await ActionRepository.count_completed_since(goal_id, since)
            total = await ActionRepository.count_total_in_window(goal_id, since)

            score = round((completions / total * 100), 2) if total > 0 else 0.0

            was_low = (
                goal.momentum_score is not None and goal.momentum_score < MOMENTUM_LOW_THRESHOLD
            )
            is_low = score < MOMENTUM_LOW_THRESHOLD

            await GoalRepository.update_momentum(goal_id, score)

            # Build enriched payload for the Notification Service (GS-3.3)
            # Fetch recent completions to compute a compassionate streak count
            completed_actions = await Action.find(
                Action.goal_id == goal.id,
                Action.status == ActionStatus.COMPLETED,
                Action.completed_at >= since,
            ).to_list()
            completed_dates = [a.completed_at for a in completed_actions if a.completed_at]
            streak = _compute_completion_streak(completed_dates)

            enriched_payload = {
                "goal_id": goal_id,
                "user_id": str(goal.user_id),
                "goal_title": goal.title,
                "momentum_score": score,
                "completion_streak": streak,
                # No shame-language fields — §3 engagement philosophy (no missed-days, broken-streak counters)
            }

            if is_low and not was_low:
                await publish_event(GoalEvents.MOMENTUM_LOW, enriched_payload)
                logger.info(
                    f"Momentum LOW for goal '{goal.title}' (user={goal.user_id}, score={score:.1f})"
                )
            elif not is_low and was_low:
                await publish_event(GoalEvents.MOMENTUM_RECOVERED, enriched_payload)
                logger.info(
                    f"Momentum RECOVERED for goal '{goal.title}' "
                    f"(user={goal.user_id}, score={score:.1f})"
                )

        except Exception as exc:
            logger.error(f"Momentum recalc failed for goal {goal.id}: {exc}")


async def run_momentum_recalc() -> None:
    """Infinite loop — runs the momentum recalculation on the configured interval."""
    logger.info(f"Momentum worker started (interval: {settings.MOMENTUM_RECALC_INTERVAL_HOURS}h)")
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
