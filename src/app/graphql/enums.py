"""
Strawberry GraphQL enums for the Goals Service.

Each enum mirrors its constants-module counterpart exactly.
A test (test_enums.py) asserts that the values stay in sync
so they can never silently drift apart.
"""

from enum import Enum

import strawberry


@strawberry.enum
class GoalStatusEnum(Enum):
    """Lifecycle state of a Goal."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RESUMED = "RESUMED"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"


@strawberry.enum
class GoalCategoryEnum(Enum):
    """Life domain that a goal belongs to."""

    HEALTH = "HEALTH"
    FINANCE = "FINANCE"
    RELATIONSHIPS = "RELATIONSHIPS"
    CAREER = "CAREER"
    PERSONAL_GROWTH = "PERSONAL_GROWTH"
    MINDSET = "MINDSET"
    CREATIVITY = "CREATIVITY"
    SPIRITUALITY = "SPIRITUALITY"
    CUSTOM = "CUSTOM"


@strawberry.enum
class GoalHorizonEnum(Enum):
    """Time-frame intent for a goal."""

    SPRINT = "SPRINT"
    SHORT = "SHORT"
    MEDIUM = "MEDIUM"
    LONG = "LONG"
    LIFETIME = "LIFETIME"


@strawberry.enum
class PriorityEnum(Enum):
    """Numeric priority mapped to named levels (1=LOW … 4=CRITICAL)."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@strawberry.enum
class DecompositionStateEnum(Enum):
    """State of the AI decomposition pipeline for a goal."""

    NONE = "NONE"
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@strawberry.enum
class PhaseStatusEnum(Enum):
    """Lifecycle status of a Phase within a Goal."""

    LOCKED = "LOCKED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"


@strawberry.enum
class ActionStatusEnum(Enum):
    """Completion status of an Action."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


@strawberry.enum
class ActionTypeEnum(Enum):
    """Semantic type of an Action (one-off task vs. recurring habit, etc.)."""

    TASK = "TASK"
    HABIT = "HABIT"
    MILESTONE = "MILESTONE"
    REFLECTION = "REFLECTION"
    LEARNING = "LEARNING"
    CHALLENGE = "CHALLENGE"


@strawberry.enum
class RecurrencePatternEnum(Enum):
    """Recurrence frequency for HABIT-type actions."""

    DAILY = "DAILY"
    WEEKDAYS = "WEEKDAYS"
    WEEKENDS = "WEEKENDS"
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    MONTHLY = "MONTHLY"
    CUSTOM = "CUSTOM"
