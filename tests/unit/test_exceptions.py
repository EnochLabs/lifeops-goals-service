import pytest

from app.core.exceptions import (
    GoalNotFoundError,
    PlanFeatureLockedError,
    RateLimitExceededError,
    UnauthenticatedError,
)


def test_goal_not_found_includes_id():
    exc = GoalNotFoundError("abc123")
    assert "abc123" in exc.detail
    assert exc.status_code == 404


def test_plan_feature_locked_includes_plan():
    exc = PlanFeatureLockedError("AI decomposition", "BASIC")
    assert "BASIC" in exc.detail
    assert exc.status_code == 403


def test_rate_limit_is_429():
    exc = RateLimitExceededError()
    assert exc.status_code == 429


def test_unauthenticated_is_401():
    exc = UnauthenticatedError()
    assert exc.status_code == 401
