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
