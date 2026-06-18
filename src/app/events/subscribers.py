"""
Event subscriber for the Goals Service.

Listens to:
  - lifeops:events:auth   (user.deleted, user.plan_upgraded, user.plan_downgraded)
  - lifeops:events:ai     (ai.decomposition_result)
  - lifeops:events:health (health_log_saved — for energy-based auto-rescheduling, Sprint 3)

Started as a background task during app lifespan.
"""

import asyncio
import json
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

# Health Service channel — subscribed now so no events are missed later.
# The actual auto-reschedule handler is implemented in Sprint 3 when
# actions exist. The no-op handler below is intentional and tested.
HEALTH_EVENTS_CHANNEL = "lifeops:events:health"
INBOUND_HEALTH_LOG_SAVED = "health_log_saved"

_CHANNELS = [INBOUND_CHANNEL, AI_EVENTS_CHANNEL, HEALTH_EVENTS_CHANNEL]


async def _handle_user_deleted(payload: Dict[str, Any]) -> None:
    """Cascade-delete all goals for a deleted user."""
    from app.repositories.goal_repository import GoalRepository  # late import to avoid circular

    user_id = payload.get("user_id")
    if not user_id:
        return
    logger.info(f"Cascading goal deletion for user {user_id}")
    await GoalRepository.delete_all_for_user(user_id)


async def _handle_plan_change(payload: Dict[str, Any], upgraded: bool) -> None:
    """Enforce/relax plan limits when a user's plan changes."""

    user_id = payload.get("user_id")
    new_plan = payload.get("new_plan")
    if not user_id or not new_plan:
        return
    direction = "upgraded" if upgraded else "downgraded"
    logger.info(f"User {user_id} plan {direction} → {new_plan}")
    # Further enforcement logic will be added when GoalService is implemented


async def _handle_ai_decomposition_result(payload: Dict[str, Any]) -> None:
    """Apply AI-generated phases/actions to the goal."""

    goal_id = payload.get("goal_id")
    if not goal_id:
        return
    logger.info(f"Received AI decomposition result for goal {goal_id}")
    # GoalService.apply_decomposition_result will be called here


async def _handle_health_log_saved(payload: Dict[str, Any]) -> None:
    """
    Handle a health_log_saved event from the Health Service.

    Sprint 3 will implement energy-based auto-rescheduling here:
    when morning_energy <= 2, high-effort actions due today are
    rescheduled to the next day with reason 'low_energy_day'.

    For now, we log receipt so the subscription can be verified in tests.
    """
    user_id = payload.get("user_id")
    energy = payload.get("morning_energy")
    logger.debug(
        f"[health_log_saved] received for user={user_id}, morning_energy={energy} "
        f"— auto-reschedule logic pending Sprint 3"
    )


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
