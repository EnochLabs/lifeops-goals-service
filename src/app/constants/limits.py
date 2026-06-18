# ── Per-user rate limits (sliding window / 1 hour) ───────────
CREATE_GOAL_RATE_LIMIT = 20
UPDATE_GOAL_RATE_LIMIT = 60
DELETE_GOAL_RATE_LIMIT = 10
COMPLETE_ACTION_RATE_LIMIT = 200
DECOMPOSE_GOAL_RATE_LIMIT = 5  # AI calls are expensive
REORDER_PHASES_RATE_LIMIT = 30

# ── Global IP-level rate limit (per minute) ───────────────────
GLOBAL_RATE_LIMIT_PER_MINUTE = 300

# ── Structural limits ─────────────────────────────────────────
MAX_PHASES_PER_GOAL = 6
MAX_ACTIONS_PER_PHASE = 50
MAX_ACTIONS_PER_DECOMPOSITION = 200  # AI service cap
MAX_GOAL_TITLE_LENGTH = 120
MAX_GOAL_DESCRIPTION_LENGTH = 2000
MAX_ACTION_TITLE_LENGTH = 200
MAX_PHASE_TITLE_LENGTH = 120
MAX_NOTE_LENGTH = 5000

# ── Momentum ──────────────────────────────────────────────────
MOMENTUM_WINDOW_DAYS = 14
MOMENTUM_LOW_THRESHOLD = 40.0  # below this → fire event

# ── Recalculation schedules ───────────────────────────────────
MOMENTUM_RECALC_INTERVAL_HOURS = 6
RECURRING_ACTION_GEN_INTERVAL_HOURS = 12
