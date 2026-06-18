"""
GS-1.2: Unit tests for goal_service lifecycle functions.

Covers: create_goal, activate_goal, pause_goal, resume_goal,
complete_goal, abandon_goal — plus all invalid-state transitions.
"""

import pytest

from app.constants.goals import GoalStatus
from app.constants.plans import PlanTier
from app.core.exceptions.base import (
    DuplicateGoalError,
    GoalLimitExceededError,
    GoalNotFoundError,
    InvalidGoalStateError,
)
from app.models.goal import Goal
from app.services import goal_service

# ── helpers ──────────────────────────────────────────────────────────────────

USER_ID = "64f0000000000000000000aa"
USER_ID_2 = "64f0000000000000000000bb"


async def _make_goal(
    title: str = "Test goal",
    plan: str = PlanTier.PRO,
    status: str = GoalStatus.DRAFT,
) -> Goal:
    goal = await goal_service.create_goal(
        user_id=USER_ID,
        title=title,
        description=None,
        category="HEALTH",
        horizon="MEDIUM",
        priority=2,
        target_date=None,
        plan_tier=plan,
    )
    if status == GoalStatus.ACTIVE:
        goal = await goal_service.activate_goal(USER_ID, str(goal.id))
    return goal


# ── create_goal ───────────────────────────────────────────────────────────────


class TestCreateGoal:
    @pytest.mark.asyncio
    async def test_creates_goal_in_draft(self):
        goal = await _make_goal()
        assert goal.status == GoalStatus.DRAFT
        assert goal.title == "Test goal"

    @pytest.mark.asyncio
    async def test_enforces_goal_limit_for_plan(self):
        # FREE plan max = 3 active goals
        for i in range(3):
            g = await _make_goal(title=f"Goal {i}", plan=PlanTier.FREE)
            await goal_service.activate_goal(USER_ID, str(g.id))

        with pytest.raises(GoalLimitExceededError):
            await _make_goal(title="Goal overflow", plan=PlanTier.FREE)

    @pytest.mark.asyncio
    async def test_rejects_duplicate_title(self):
        await _make_goal(title="My unique goal")
        with pytest.raises(DuplicateGoalError):
            await _make_goal(title="My unique goal")

    @pytest.mark.asyncio
    async def test_creates_with_numeric_progress(self):
        goal = await goal_service.create_goal(
            user_id=USER_ID,
            title="Save for trip",
            description=None,
            category="FINANCE",
            horizon="SHORT",
            priority=2,
            target_date=None,
            plan_tier=PlanTier.PRO,
            target_value=2000.0,
            current_value=0.0,
            unit="USD",
        )
        assert goal.target_value == 2000.0
        assert goal.unit == "USD"


# ── activate_goal ────────────────────────────────────────────────────────────


class TestActivateGoal:
    @pytest.mark.asyncio
    async def test_draft_to_active(self):
        goal = await _make_goal()
        result = await goal_service.activate_goal(USER_ID, str(goal.id))
        assert result.status == GoalStatus.ACTIVE
        assert result.activated_at is not None

    @pytest.mark.asyncio
    async def test_cannot_activate_already_active(self):
        goal = await _make_goal(status=GoalStatus.ACTIVE)
        with pytest.raises(InvalidGoalStateError):
            await goal_service.activate_goal(USER_ID, str(goal.id))

    @pytest.mark.asyncio
    async def test_ownership_check(self):
        goal = await _make_goal()
        with pytest.raises(GoalNotFoundError):
            await goal_service.activate_goal(USER_ID_2, str(goal.id))

    @pytest.mark.asyncio
    async def test_not_found(self):
        with pytest.raises(GoalNotFoundError):
            await goal_service.activate_goal(USER_ID, "000000000000000000000001")


# ── pause_goal ───────────────────────────────────────────────────────────────


class TestPauseGoal:
    @pytest.mark.asyncio
    async def test_active_to_paused(self):
        goal = await _make_goal(status=GoalStatus.ACTIVE)
        result = await goal_service.pause_goal(USER_ID, str(goal.id))
        assert result.status == GoalStatus.PAUSED
        assert result.paused_at is not None

    @pytest.mark.asyncio
    async def test_cannot_pause_draft(self):
        goal = await _make_goal()
        with pytest.raises(InvalidGoalStateError):
            await goal_service.pause_goal(USER_ID, str(goal.id))

    @pytest.mark.asyncio
    async def test_cannot_pause_completed(self):
        goal = await _make_goal(status=GoalStatus.ACTIVE)
        await goal_service.complete_goal(USER_ID, str(goal.id))
        with pytest.raises(InvalidGoalStateError):
            await goal_service.pause_goal(USER_ID, str(goal.id))


# ── resume_goal ───────────────────────────────────────────────────────────────


class TestResumeGoal:
    @pytest.mark.asyncio
    async def test_paused_to_resumed(self):
        goal = await _make_goal(status=GoalStatus.ACTIVE)
        await goal_service.pause_goal(USER_ID, str(goal.id))
        result = await goal_service.resume_goal(USER_ID, str(goal.id))
        assert result.status == GoalStatus.RESUMED

    @pytest.mark.asyncio
    async def test_cannot_resume_draft(self):
        goal = await _make_goal()
        with pytest.raises(InvalidGoalStateError):
            await goal_service.resume_goal(USER_ID, str(goal.id))

    @pytest.mark.asyncio
    async def test_resumed_goal_can_be_paused_again(self):
        goal = await _make_goal(status=GoalStatus.ACTIVE)
        await goal_service.pause_goal(USER_ID, str(goal.id))
        await goal_service.resume_goal(USER_ID, str(goal.id))
        result = await goal_service.pause_goal(USER_ID, str(goal.id))
        assert result.status == GoalStatus.PAUSED


# ── complete_goal ─────────────────────────────────────────────────────────────


class TestCompleteGoal:
    @pytest.mark.asyncio
    async def test_active_to_completed(self):
        goal = await _make_goal(status=GoalStatus.ACTIVE)
        result = await goal_service.complete_goal(USER_ID, str(goal.id))
        assert result.status == GoalStatus.COMPLETED
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_paused_can_be_completed(self):
        goal = await _make_goal(status=GoalStatus.ACTIVE)
        await goal_service.pause_goal(USER_ID, str(goal.id))
        result = await goal_service.complete_goal(USER_ID, str(goal.id))
        assert result.status == GoalStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cannot_complete_draft(self):
        goal = await _make_goal()
        with pytest.raises(InvalidGoalStateError):
            await goal_service.complete_goal(USER_ID, str(goal.id))

    @pytest.mark.asyncio
    async def test_cannot_complete_abandoned(self):
        goal = await _make_goal(status=GoalStatus.ACTIVE)
        await goal_service.abandon_goal(USER_ID, str(goal.id))
        with pytest.raises(InvalidGoalStateError):
            await goal_service.complete_goal(USER_ID, str(goal.id))


# ── abandon_goal ──────────────────────────────────────────────────────────────


class TestAbandonGoal:
    @pytest.mark.asyncio
    async def test_active_to_abandoned(self):
        goal = await _make_goal(status=GoalStatus.ACTIVE)
        result = await goal_service.abandon_goal(USER_ID, str(goal.id), reason="Changed mind")
        assert result.status == GoalStatus.ABANDONED
        assert "Changed mind" in (result.note or "")

    @pytest.mark.asyncio
    async def test_draft_can_be_abandoned(self):
        goal = await _make_goal()
        result = await goal_service.abandon_goal(USER_ID, str(goal.id))
        assert result.status == GoalStatus.ABANDONED

    @pytest.mark.asyncio
    async def test_ownership_check_on_abandon(self):
        goal = await _make_goal(status=GoalStatus.ACTIVE)
        with pytest.raises(GoalNotFoundError):
            await goal_service.abandon_goal(USER_ID_2, str(goal.id))
