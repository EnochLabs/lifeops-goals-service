# ─────────────────────────────────────────────────────────────
# GOAL CATEGORIES  (blueprint §3 — Life Dimensions)
# ─────────────────────────────────────────────────────────────
class GoalCategory:
    HEALTH = "HEALTH"
    FINANCE = "FINANCE"
    RELATIONSHIPS = "RELATIONSHIPS"
    CAREER = "CAREER"
    PERSONAL_GROWTH = "PERSONAL_GROWTH"
    MINDSET = "MINDSET"
    CREATIVITY = "CREATIVITY"
    SPIRITUALITY = "SPIRITUALITY"
    CUSTOM = "CUSTOM"


ALL_CATEGORIES = [v for k, v in GoalCategory.__dict__.items() if not k.startswith("_")]


# ─────────────────────────────────────────────────────────────
# GOAL STATUS
# ─────────────────────────────────────────────────────────────
class GoalStatus:
    DRAFT = "DRAFT"  # created but not yet activated
    ACTIVE = "ACTIVE"  # in progress
    PAUSED = "PAUSED"  # user paused (momentum frozen)
    RESUMED = "RESUMED"  # resumed after pause (treated as ACTIVE for momentum)
    COMPLETED = "COMPLETED"  # all phases done
    ABANDONED = "ABANDONED"  # user gave up / archived


# ─────────────────────────────────────────────────────────────
# PHASE STATUS
# ─────────────────────────────────────────────────────────────
class PhaseStatus:
    LOCKED = "LOCKED"  # future phase, not yet unlocked
    ACTIVE = "ACTIVE"  # current phase being worked on
    COMPLETED = "COMPLETED"  # all actions in phase done
    SKIPPED = "SKIPPED"  # user explicitly skipped


# ─────────────────────────────────────────────────────────────
# ACTION STATUS
# ─────────────────────────────────────────────────────────────
class ActionStatus:
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


# ─────────────────────────────────────────────────────────────
# ACTION TYPES
# ─────────────────────────────────────────────────────────────
class ActionType:
    TASK = "TASK"  # one-off task
    HABIT = "HABIT"  # recurring habit
    MILESTONE = "MILESTONE"  # significant checkpoint
    REFLECTION = "REFLECTION"  # journaling / review prompt
    LEARNING = "LEARNING"  # consume content / study
    CHALLENGE = "CHALLENGE"  # short burst challenge


# ─────────────────────────────────────────────────────────────
# RECURRENCE PATTERNS  (for HABIT actions)
# ─────────────────────────────────────────────────────────────
class RecurrencePattern:
    DAILY = "DAILY"
    WEEKDAYS = "WEEKDAYS"  # Mon–Fri
    WEEKENDS = "WEEKENDS"
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"  # Every two weeks
    MONTHLY = "MONTHLY"  # Once a month
    CUSTOM = "CUSTOM"  # specific days of week


# ─────────────────────────────────────────────────────────────
# GOAL HORIZON  (time-frame intent)
# ─────────────────────────────────────────────────────────────
class GoalHorizon:
    SPRINT = "SPRINT"  # < 2 weeks
    SHORT = "SHORT"  # 2 weeks – 3 months
    MEDIUM = "MEDIUM"  # 3 – 12 months
    LONG = "LONG"  # > 12 months
    LIFETIME = "LIFETIME"  # no end date


# ─────────────────────────────────────────────────────────────
# PRIORITY LEVELS
# ─────────────────────────────────────────────────────────────
class Priority:
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


# ─────────────────────────────────────────────────────────────
# DECOMPOSITION STATE  (AI decomposition lifecycle)
# ─────────────────────────────────────────────────────────────
class DecompositionState:
    NONE = "NONE"  # never decomposed
    PENDING = "PENDING"  # queued to AI service
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
