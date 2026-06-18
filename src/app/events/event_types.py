"""
Event type constants for the Goals Service.

Naming convention:  <aggregate>.<past_verb>
Published via Redis Pub/Sub channel:  lifeops:events:goals
Consumed by:  AI Service, Notification Service, Analytics Service
"""


class GoalEvents:
    # Lifecycle
    CREATED = "goal.created"
    ACTIVATED = "goal.activated"
    PAUSED = "goal.paused"
    RESUMED = "goal.resumed"
    COMPLETED = "goal.completed"
    ABANDONED = "goal.abandoned"

    # AI decomposition
    DECOMPOSITION_REQUESTED = "goal.decomposition_requested"
    DECOMPOSITION_COMPLETED = "goal.decomposition_completed"
    DECOMPOSITION_FAILED = "goal.decomposition_failed"

    # Momentum (computed by background worker)
    MOMENTUM_LOW = "goal.momentum_low"
    MOMENTUM_RECOVERED = "goal.momentum_recovered"


class PhaseEvents:
    UNLOCKED = "phase.unlocked"
    COMPLETED = "phase.completed"
    SKIPPED = "phase.skipped"


class ActionEvents:
    CREATED = "action.created"
    COMPLETED = "action.completed"
    SKIPPED = "action.skipped"
    FAILED = "action.failed"
    RECURRING_GENERATED = "action.recurring_generated"


# ── Channels ──────────────────────────────────────────────────
GOALS_EVENT_CHANNEL = "lifeops:events:goals"

# ── Inbound events Goals Service listens for ──────────────────
# (published by other services we react to)
INBOUND_USER_DELETED = "user.deleted"  # from Auth Service → cascade delete goals
INBOUND_PLAN_UPGRADED = "user.plan_upgraded"  # from Auth Service → unlock features
INBOUND_PLAN_DOWNGRADED = "user.plan_downgraded"  # from Auth Service → enforce new limits
INBOUND_AI_DECOMPOSITION_RESULT = "ai.decomposition_result"  # from AI Service

INBOUND_CHANNEL = "lifeops:events:auth"
AI_EVENTS_CHANNEL = "lifeops:events:ai"
