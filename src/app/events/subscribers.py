"""
Event subscriber for the Goals Service.

Listens to:
  - lifeops:events:auth   (user.deleted, user.plan_upgraded, user.plan_downgraded)
  - lifeops:events:ai     (ai.decomposition_result)
  - lifeops:events:health (health_log_saved — energy-based auto-rescheduling, GS-3.4)

Started as a background task during app lifespan.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Dict

import redis.asyncio as aioredis
from loguru import logger

from app.config.settings import settings
from app.events.event_types import (
    AI_EVENTS_CHANNEL,
    INBOUND_AI_DECOMPOSITION_RESULT,
    INBOUND_CHANNEL,
    INBOUND_PLAN_DOWNGRADED,
    INBOUND_PLAN_UPGRADED,
    INBOUND_USER_DELETED,
)

# Health Service channel — subscribed so no events are missed.
HEALTH_EVENTS_CHANNEL = "lifeops:events:health"
INBOUND_HEALTH_LOG_SAVED = "health_log_saved"

# Energy threshold at or below which today's high-effort actions are rescheduled.
# Matches the blueprint's worked example: energy in {1, 2} triggers a reschedule.
_LOW_ENERGY_THRESHOLD = 2

# Effort threshold in minutes — actions with estimated_minutes above this value
# are considered "high-effort" for the purposes of auto-rescheduling.
# Default 30 min is configurable via settings; the subscriber uses the value
# from settings so integration tests can override it without patching constants.
_HIGH_EFFORT_MINUTES: int = getattr(settings, "AUTO_RESCHEDULE_EFFORT_THRESHOLD_MINUTES", 30)

_CHANNELS = [INBOUND_CHANNEL, AI_EVENTS_CHANNEL, HEALTH_EVENTS_CHANNEL]


# ── Auth event handlers ───────────────────────────────────────────────────────


async def _handle_user_deleted(payload: Dict[str, Any]) -> None:
    """Cascade-delete all goals for a deleted user."""
    from app.repositories.goal_repository import GoalRepository

    user_id = payload.get("user_id")
    if not user_id:
        return
    logger.info(f"Cascading goal deletion for user {user_id}")
    await GoalRepository.delete_all_for_user(user_id)


async def _handle_plan_change(payload: Dict[str, Any], upgraded: bool) -> None:
    """Enforce/relax plan limits when a user's plan changes.

    On downgrade: goals beyond the new plan cap are moved to PAUSED (not deleted).
    On upgrade: no immediate action needed — new limits are checked at creation time.
    """
    user_id = payload.get("user_id")
    new_plan = payload.get("new_plan")
    if not user_id or not new_plan:
        return

    direction = "upgraded" if upgraded else "downgraded"
    logger.info(f"User {user_id} plan {direction} → {new_plan}")

    if not upgraded:
        # Downgrade path — implemented in Sprint 5 (GS-5.4).
        # Logged here so the event is not silently swallowed.
        logger.info(
            f"Plan downgrade enforcement for user {user_id} pending Sprint 5 implementation."
        )


# ── AI event handlers ─────────────────────────────────────────────────────────


async def _handle_ai_decomposition_result(payload: Dict[str, Any]) -> None:
    """Apply AI-generated phases/actions to the goal.

    Full implementation in Sprint 4 (GS-4.3).
    """
    goal_id = payload.get("goal_id")
    if not goal_id:
        return
    logger.info(f"Received AI decomposition result for goal {goal_id}")
    # GoalService.apply_decomposition_result will be called here in Sprint 4


# ── Health event handler — GS-3.4 ────────────────────────────────────────────


async def _handle_health_log_saved(payload: Dict[str, Any]) -> None:
    """Auto-reschedule high-effort actions when morning energy is low (GS-3.4).

    Trigger: health_log_saved event with morning_energy in {1, 2}.
    Effect:  all pending/in-progress actions due today with
             estimated_minutes > _HIGH_EFFORT_MINUTES are pushed to tomorrow.
    Reason:  'low_energy_day' — stored on the rescheduled action for transparency.

    This matches the blueprint's worked example:
      Tuesday, morning_energy=2 → "10 km run" (high effort) rescheduled to Wednesday.
      "Buy running shoes" (low effort / no estimate) — not rescheduled.

    Design note (§3 engagement philosophy):
      - No notification shaming: the event payload does not include "missed" counts.
      - No cascade: only *today's* actions are touched, not future scheduled ones.
      - No opt-out requirement: the user can always manually re-reschedule back.
    """
    user_id = payload.get("user_id")
    morning_energy = payload.get("morning_energy")

    if not user_id or morning_energy is None:
        logger.debug("[health_log_saved] missing user_id or morning_energy — ignoring")
        return

    try:
        energy_val = int(morning_energy)
    except (TypeError, ValueError):
        logger.debug(f"[health_log_saved] non-numeric morning_energy={morning_energy!r} — ignoring")
        return

    if energy_val > _LOW_ENERGY_THRESHOLD:
        logger.debug(
            f"[health_log_saved] user={user_id}, morning_energy={energy_val} — no reschedule needed"
        )
        return

    logger.info(
        f"[health_log_saved] LOW ENERGY (energy={energy_val}) for user={user_id} "
        f"— auto-rescheduling high-effort actions (>{_HIGH_EFFORT_MINUTES} min)"
    )

    try:
        from app.repositories.action_repository import ActionRepository
        from app.services.action_service import reschedule_action

        now = datetime.now(UTC).replace(tzinfo=None)  # naive UTC — consistent with stored dates
        tomorrow = now + timedelta(days=1)
        # Normalise to start-of-day so the reschedule reads clearly in the UI
        tomorrow_noon = tomorrow.replace(hour=12, minute=0, second=0, microsecond=0)

        todays_actions = await ActionRepository.list_for_user_due_today(user_id, now)

        rescheduled_count = 0
        for action in todays_actions:
            # Only reschedule explicitly high-effort actions (those with an estimate set)
            if action.estimated_minutes and action.estimated_minutes > _HIGH_EFFORT_MINUTES:
                try:
                    await reschedule_action(
                        user_id=user_id,
                        action_id=str(action.id),
                        new_due_date=tomorrow_noon,
                        reason="low_energy_day",
                    )
                    rescheduled_count += 1
                    logger.info(
                        f"  ↳ Rescheduled '{action.title}' "
                        f"({action.estimated_minutes} min) to tomorrow"
                    )
                except Exception as action_err:
                    logger.warning(f"  ↳ Could not reschedule action {action.id}: {action_err}")

        logger.info(
            f"[health_log_saved] auto-reschedule complete: "
            f"{rescheduled_count} action(s) moved for user={user_id}"
        )

    except Exception as exc:
        logger.error(f"[health_log_saved] auto-reschedule error for user={user_id}: {exc}")


# ── Dispatcher ────────────────────────────────────────────────────────────────


async def _dispatch(event_type: str, payload: Dict[str, Any]) -> None:
    handlers = {
        INBOUND_USER_DELETED: _handle_user_deleted,
        INBOUND_PLAN_UPGRADED: lambda p: _handle_plan_change(p, upgraded=True),
        INBOUND_PLAN_DOWNGRADED: lambda p: _handle_plan_change(p, upgraded=False),
        INBOUND_AI_DECOMPOSITION_RESULT: _handle_ai_decomposition_result,
        INBOUND_HEALTH_LOG_SAVED: _handle_health_log_saved,
    }
    handler = handlers.get(event_type)
    if handler:
        try:
            await handler(payload)
        except Exception as exc:
            logger.error(f"Error handling event '{event_type}': {exc}")
    else:
        logger.debug(f"No handler for inbound event: {event_type}")


async def start_subscriber() -> None:
    """
    Long-running coroutine — subscribes to Redis channels and dispatches events.
    Reconnects automatically on connection loss.
    """
    while True:
        try:
            sub_client = aioredis.from_url(
                settings.REDIS_URL, encoding="utf-8", decode_responses=True
            )
            pubsub = sub_client.pubsub()
            await pubsub.subscribe(*_CHANNELS)
            logger.info(f"Goals Service subscribed to channels: {_CHANNELS}")

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    event_type = data.pop("event", None)
                    if event_type:
                        await _dispatch(event_type, data)
                except json.JSONDecodeError:
                    logger.warning(f"Non-JSON message on channel {message['channel']}")
        except asyncio.CancelledError:
            logger.info("Event subscriber shutting down.")
            break
        except Exception as exc:
            logger.error(f"Subscriber error — reconnecting in 5s: {exc}")
            await asyncio.sleep(5)
