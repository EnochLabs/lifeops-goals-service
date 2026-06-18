"""
Event publisher for the Goals Service.

Publishes JSON-encoded domain events to the Redis pub/sub channel
`lifeops:events:goals`.  All other services subscribe to this channel.

Usage:
    await publish_event(GoalEvents.COMPLETED, {"goal_id": str(goal.id), "user_id": user_id})
"""

import json
from datetime import UTC, datetime
from typing import Any, Dict

from loguru import logger

from app.config.redis import redis_client
from app.events.event_types import GOALS_EVENT_CHANNEL


async def publish_event(event_type: str, payload: Dict[str, Any]) -> None:
    """
    Publish a domain event to Redis.

    Silently swallows errors — event publishing should never crash the
    primary request path.
    """
    message = json.dumps(
        {
            "event": event_type,
            "service": "goals",
            "timestamp": datetime.now(UTC).isoformat(),
            **payload,
        }
    )
    try:
        await redis_client.publish(GOALS_EVENT_CHANNEL, message)
        logger.debug(f"Published event: {event_type}")
    except Exception as exc:
        logger.error(f"Failed to publish event '{event_type}': {exc}")


# Convenience wrappers for each aggregate type
async def publish_goal_event(
    event_type: str,
    goal_id: str,
    user_id: str,
    payload: Dict[str, Any],
) -> None:
    """Publish a goal event."""
    enriched_payload = {
        "goal_id": goal_id,
        "user_id": user_id,
        **payload,
    }
    await publish_event(event_type, enriched_payload)


async def publish_phase_event(
    event_type: str,
    phase_id: str,
    goal_id: str,
    user_id: str,
    payload: Dict[str, Any],
) -> None:
    """Publish a phase event."""
    enriched_payload = {
        "phase_id": phase_id,
        "goal_id": goal_id,
        "user_id": user_id,
        **payload,
    }
    await publish_event(event_type, enriched_payload)


async def publish_action_event(
    event_type: str,
    action_id: str,
    goal_id: str,
    phase_id: str,
    user_id: str,
    payload: Dict[str, Any],
) -> None:
    """Publish an action event."""
    enriched_payload = {
        "action_id": action_id,
        "goal_id": goal_id,
        "phase_id": phase_id,
        "user_id": user_id,
        **payload,
    }
    await publish_event(event_type, enriched_payload)
