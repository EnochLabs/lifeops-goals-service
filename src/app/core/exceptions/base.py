"""
Domain exception hierarchy for the Goals Service.

All HTTP-mapped exceptions inherit from GoalsServiceError so callers can
catch them at any granularity they need.
"""

from fastapi import HTTPException


class GoalsServiceError(HTTPException):
    """Base for all Goals Service exceptions."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(status_code=status_code, detail=detail)


# ── 400 Bad Request ───────────────────────────────────────────
class ValidationError(GoalsServiceError):
    def __init__(self, detail: str = "Invalid input.") -> None:
        super().__init__(400, detail)


class GoalLimitExceededError(GoalsServiceError):
    def __init__(self, limit: int, plan: str) -> None:
        super().__init__(
            400,
            f"Goal limit ({limit}) reached for your {plan} plan. Upgrade to create more.",
        )


class PhaseLimitExceededError(GoalsServiceError):
    def __init__(self) -> None:
        super().__init__(400, "Maximum phases per goal reached.")


class ActionLimitExceededError(GoalsServiceError):
    def __init__(self) -> None:
        super().__init__(400, "Maximum actions per phase reached.")


class InvalidGoalStateError(GoalsServiceError):
    def __init__(self, detail: str) -> None:
        super().__init__(400, detail)


class InvalidPhaseStateError(GoalsServiceError):
    def __init__(self, detail: str) -> None:
        super().__init__(400, detail)


class InvalidActionStateError(GoalsServiceError):
    def __init__(self, detail: str) -> None:
        super().__init__(400, detail)


# ── 401 Unauthorized ──────────────────────────────────────────
class UnauthenticatedError(GoalsServiceError):
    def __init__(self) -> None:
        super().__init__(401, "Authentication required.")


class InvalidTokenError(GoalsServiceError):
    def __init__(self) -> None:
        super().__init__(401, "Invalid or expired token.")


# ── 403 Forbidden ─────────────────────────────────────────────
class ForbiddenError(GoalsServiceError):
    def __init__(self, detail: str = "You do not have permission to perform this action.") -> None:
        super().__init__(403, detail)


class PlanFeatureLockedError(GoalsServiceError):
    """Raised when a feature requires a higher subscription tier."""

    def __init__(self, feature: str, required_plan: str) -> None:
        super().__init__(
            403,
            f"'{feature}' requires the {required_plan} plan or above. Upgrade to unlock.",
        )


class AIDecompositionLockedError(GoalsServiceError):
    def __init__(self, required_plan: str = "BASIC") -> None:
        super().__init__(
            403,
            f"AI goal decomposition requires the {required_plan} plan or above.",
        )


# ── 404 Not Found ─────────────────────────────────────────────
class GoalNotFoundError(GoalsServiceError):
    def __init__(self, goal_id: str = "") -> None:
        detail = f"Goal '{goal_id}' not found." if goal_id else "Goal not found."
        super().__init__(404, detail)


class PhaseNotFoundError(GoalsServiceError):
    def __init__(self, phase_id: str = "") -> None:
        detail = f"Phase '{phase_id}' not found." if phase_id else "Phase not found."
        super().__init__(404, detail)


class ActionNotFoundError(GoalsServiceError):
    def __init__(self, action_id: str = "") -> None:
        detail = f"Action '{action_id}' not found." if action_id else "Action not found."
        super().__init__(404, detail)


# ── 409 Conflict ──────────────────────────────────────────────
class DuplicateGoalError(GoalsServiceError):
    def __init__(self) -> None:
        super().__init__(409, "A goal with this title already exists.")


# ── 422 Unprocessable ─────────────────────────────────────────
class DecompositionError(GoalsServiceError):
    def __init__(self, detail: str = "AI decomposition failed.") -> None:
        super().__init__(422, detail)


# ── 429 Too Many Requests ─────────────────────────────────────
class RateLimitExceededError(GoalsServiceError):
    def __init__(self, detail: str = "Rate limit exceeded. Please slow down.") -> None:
        super().__init__(429, detail)


# ── 503 Service Unavailable ───────────────────────────────────
class AIServiceUnavailableError(GoalsServiceError):
    def __init__(self) -> None:
        super().__init__(503, "AI service is temporarily unavailable. Please try again later.")


class AuthServiceUnavailableError(GoalsServiceError):
    def __init__(self) -> None:
        super().__init__(503, "Auth service is temporarily unavailable.")
