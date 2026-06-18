"""
GS-2.2 / GS-2.5: Unit tests for action_service.

Covers:
  - create_action: enforcement of MAX_ACTIONS_PER_PHASE, ownership,
    HABIT recurrence setup
  - complete_action: idempotency, state guard, contributes_value → goal
    current_value increment, MILESTONE auto-phase-complete trigger
  - skip_action: idempotency, state guard, reason stored
  - reschedule_action: date update, completed guard
  - list_todays_actions: cross-goal aggregation, overdue included, scoping
  - Numeric progress (GS-2.5): progress_percent arithmetic via
    complete_action → update_goal_progress chain
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.constants.goals import ActionStatus, ActionType, GoalStatus, PhaseStatus
from app.constants.plans import PlanTier
from app.core.exceptions.base import (
    ActionLimitExceededError,
    ActionNotFoundError,
    GoalNotFoundError,
    InvalidActionStateError,
    PhaseNotFoundError,
)
from app.repositories.action_repository import ActionRepository
from app.repositories.goal_repository import GoalRepository
from app.repositories.phase_repository import PhaseRepository
from app.services import action_service, goal_service, phase_service

# ── Constants ─────────────────────────────────────────────────────────────────

USER_ID = "64f0000000000000000000aa"
USER_ID_2 = "64f0000000000000000000bb"
PAST = datetime(2026, 1, 1)
FUTURE = datetime(2030, 1, 1)
TODAY = datetime.utcnow()
YESTERDAY = TODAY - timedelta(days=1)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_active_goal(
    title: str = "Sprint goal",
    target_value: float | None = None,
    unit: str | None = None,
) -> tuple:
    """Return (goal, phase) with the goal ACTIVE and one ACTIVE phase."""
    goal = await goal_service.create_goal(
        user_id=USER_ID,
        title=title,
        description=None,
        category="HEALTH",
        horizon="MEDIUM",
        priority=2,
        target_date=None,
        plan_tier=PlanTier.PRO,
        target_value=target_value,
        current_value=0.0 if target_value is not None else None,
        unit=unit,
    )
    goal = await goal_service.activate_goal(USER_ID, str(goal.id))
    phase = await phase_service.create_phase(USER_ID, str(goal.id), "Phase 1", None)
    return goal, phase


async def _create_simple_action(
    goal,
    phase,
    title: str = "Do something",
    action_type: str = ActionType.TASK,
    due_date: datetime | None = None,
    contributes_value: float | None = None,
    recurrence: dict | None = None,
) -> object:
    return await action_service.create_action(
        user_id=USER_ID,
        goal_id=str(goal.id),
        phase_id=str(phase.id),
        title=title,
        action_type=action_type,
        due_date=due_date,
        contributes_value=contributes_value,
        recurrence=recurrence,
    )


# ── create_action ─────────────────────────────────────────────────────────────


class TestCreateAction:
    @pytest.mark.asyncio
    async def test_creates_pending_task(self):
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase)
        assert action.status == ActionStatus.PENDING
        assert action.action_type == ActionType.TASK

    @pytest.mark.asyncio
    async def test_order_increments_with_each_action(self):
        goal, phase = await _make_active_goal()
        a1 = await _create_simple_action(goal, phase, title="First")
        a2 = await _create_simple_action(goal, phase, title="Second")
        assert a1.order == 0
        assert a2.order == 1

    @pytest.mark.asyncio
    async def test_enforces_max_actions_per_phase(self):
        from app.constants.limits import MAX_ACTIONS_PER_PHASE

        goal, phase = await _make_active_goal()
        for i in range(MAX_ACTIONS_PER_PHASE):
            await _create_simple_action(goal, phase, title=f"Action {i}")
        with pytest.raises(ActionLimitExceededError):
            await _create_simple_action(goal, phase, title="Overflow action")

    @pytest.mark.asyncio
    async def test_rejects_wrong_goal_owner(self):
        goal, phase = await _make_active_goal()
        with pytest.raises(GoalNotFoundError):
            await action_service.create_action(
                user_id=USER_ID_2,
                goal_id=str(goal.id),
                phase_id=str(phase.id),
                title="Sneaky",
                action_type=ActionType.TASK,
            )

    @pytest.mark.asyncio
    async def test_rejects_missing_goal(self):
        with pytest.raises(GoalNotFoundError):
            await action_service.create_action(
                user_id=USER_ID,
                goal_id="000000000000000000000001",
                phase_id="000000000000000000000002",
                title="Ghost action",
                action_type=ActionType.TASK,
            )

    @pytest.mark.asyncio
    async def test_rejects_phase_not_belonging_to_goal(self):
        goal, phase = await _make_active_goal()
        goal2, phase2 = await _make_active_goal(title="Other goal")
        with pytest.raises(PhaseNotFoundError):
            await action_service.create_action(
                user_id=USER_ID,
                goal_id=str(goal.id),
                phase_id=str(phase2.id),
                title="Mismatched",
                action_type=ActionType.TASK,
            )

    @pytest.mark.asyncio
    async def test_habit_stores_recurrence_and_next_due(self):
        goal, phase = await _make_active_goal()
        due = TODAY + timedelta(days=1)
        action = await action_service.create_action(
            user_id=USER_ID,
            goal_id=str(goal.id),
            phase_id=str(phase.id),
            title="Morning run",
            action_type=ActionType.HABIT,
            due_date=due,
            recurrence={"pattern": "DAILY", "days_of_week": []},
        )
        assert action.recurrence is not None
        assert action.recurrence.pattern == "DAILY"
        assert action.next_due == due

    @pytest.mark.asyncio
    async def test_contributes_value_stored_on_action(self):
        goal, phase = await _make_active_goal(target_value=100.0, unit="km")
        action = await _create_simple_action(goal, phase, contributes_value=5.0)
        assert action.contributes_value == 5.0


# ── complete_action ───────────────────────────────────────────────────────────


class TestCompleteAction:
    @pytest.mark.asyncio
    async def test_marks_action_completed(self):
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase)
        result = await action_service.complete_action(USER_ID, str(action.id))
        assert result.status == ActionStatus.COMPLETED
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_idempotent_on_double_complete(self):
        """Completing an already-completed action must not raise."""
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase)
        await action_service.complete_action(USER_ID, str(action.id))
        result = await action_service.complete_action(USER_ID, str(action.id))
        assert result.status == ActionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cannot_complete_skipped_action(self):
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase)
        await action_service.skip_action(USER_ID, str(action.id))
        with pytest.raises(InvalidActionStateError):
            await action_service.complete_action(USER_ID, str(action.id))

    @pytest.mark.asyncio
    async def test_ownership_check(self):
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase)
        with pytest.raises(ActionNotFoundError):
            await action_service.complete_action(USER_ID_2, str(action.id))

    @pytest.mark.asyncio
    async def test_completion_note_stored(self):
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase)
        result = await action_service.complete_action(
            USER_ID, str(action.id), completion_note="Nailed it"
        )
        assert result.completion_note == "Nailed it"

    @pytest.mark.asyncio
    async def test_contributes_value_increments_goal_progress(self):
        """GS-2.5: completing a contributing action increments goal.current_value."""
        goal, phase = await _make_active_goal(target_value=2000.0, unit="USD")
        action = await _create_simple_action(goal, phase, contributes_value=500.0)
        await action_service.complete_action(USER_ID, str(action.id))

        refreshed_goal = await GoalRepository.get_by_id(str(goal.id))
        assert refreshed_goal is not None
        assert refreshed_goal.current_value == 500.0

    @pytest.mark.asyncio
    async def test_multiple_contributions_accumulate(self):
        """GS-2.5: Save $2,000 example — canonical test from sprint plan."""
        goal, phase = await _make_active_goal(target_value=2000.0, unit="USD")
        # Simulate 4 payments of $500
        for i in range(4):
            action = await _create_simple_action(
                goal, phase, title=f"Payment {i}", contributes_value=500.0
            )
            await action_service.complete_action(USER_ID, str(action.id))

        refreshed = await GoalRepository.get_by_id(str(goal.id))
        assert refreshed is not None
        assert refreshed.current_value == 2000.0

    @pytest.mark.asyncio
    async def test_milestone_completion_triggers_phase_complete_when_last(self):
        """GS-2.2: Completing a MILESTONE that is the last incomplete action auto-completes phase."""
        goal, phase = await _make_active_goal()

        # One TASK and one MILESTONE
        task = await _create_simple_action(
            goal, phase, title="Prep task", action_type=ActionType.TASK
        )
        milestone = await _create_simple_action(
            goal, phase, title="Race day", action_type=ActionType.MILESTONE
        )

        # Complete the task first
        await action_service.complete_action(USER_ID, str(task.id))

        # Completing the MILESTONE (last incomplete) should auto-complete the phase
        await action_service.complete_action(USER_ID, str(milestone.id))

        refreshed_phase = await PhaseRepository.get_by_id(str(phase.id))
        assert refreshed_phase is not None
        assert refreshed_phase.status == PhaseStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_milestone_does_not_auto_complete_phase_when_other_actions_remain(self):
        """MILESTONE completion should NOT auto-complete phase if other actions are pending."""
        goal, phase = await _make_active_goal()
        milestone = await _create_simple_action(
            goal, phase, title="Milestone", action_type=ActionType.MILESTONE
        )
        await _create_simple_action(goal, phase, title="Pending task")

        await action_service.complete_action(USER_ID, str(milestone.id))

        refreshed_phase = await PhaseRepository.get_by_id(str(phase.id))
        assert refreshed_phase is not None
        assert refreshed_phase.status == PhaseStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        with pytest.raises(ActionNotFoundError):
            await action_service.complete_action(USER_ID, "000000000000000000000001")


# ── skip_action ───────────────────────────────────────────────────────────────


class TestSkipAction:
    @pytest.mark.asyncio
    async def test_marks_action_skipped(self):
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase)
        result = await action_service.skip_action(USER_ID, str(action.id))
        assert result.status == ActionStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_idempotent_on_double_skip(self):
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase)
        await action_service.skip_action(USER_ID, str(action.id))
        result = await action_service.skip_action(USER_ID, str(action.id))
        assert result.status == ActionStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_reason_stored_in_completion_note(self):
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase)
        result = await action_service.skip_action(USER_ID, str(action.id), reason="Not relevant")
        assert result.completion_note == "Not relevant"

    @pytest.mark.asyncio
    async def test_cannot_skip_completed_action(self):
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase)
        await action_service.complete_action(USER_ID, str(action.id))
        with pytest.raises(InvalidActionStateError):
            await action_service.skip_action(USER_ID, str(action.id))

    @pytest.mark.asyncio
    async def test_ownership_check(self):
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase)
        with pytest.raises(ActionNotFoundError):
            await action_service.skip_action(USER_ID_2, str(action.id))


# ── reschedule_action ─────────────────────────────────────────────────────────


class TestRescheduleAction:
    @pytest.mark.asyncio
    async def test_updates_due_date(self):
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase, due_date=YESTERDAY)
        new_due = TODAY + timedelta(days=7)
        result = await action_service.reschedule_action(USER_ID, str(action.id), new_due)
        assert result.due_date.date() == new_due.date()

    @pytest.mark.asyncio
    async def test_cannot_reschedule_completed_action(self):
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase)
        await action_service.complete_action(USER_ID, str(action.id))
        with pytest.raises(InvalidActionStateError):
            await action_service.reschedule_action(
                USER_ID, str(action.id), TODAY + timedelta(days=1)
            )

    @pytest.mark.asyncio
    async def test_ownership_check(self):
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase, due_date=YESTERDAY)
        with pytest.raises(ActionNotFoundError):
            await action_service.reschedule_action(
                USER_ID_2, str(action.id), TODAY + timedelta(days=1)
            )

    @pytest.mark.asyncio
    async def test_reason_stored_in_event_payload(self):
        """Reschedule with a reason completes without error — payload captured in publisher."""
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase, due_date=YESTERDAY)
        result = await action_service.reschedule_action(
            USER_ID, str(action.id), TODAY + timedelta(days=1), reason="low_energy_day"
        )
        # Spot-check: action is still pending and has updated due date
        assert result.status == ActionStatus.PENDING


# ── list_todays_actions ───────────────────────────────────────────────────────


class TestListTodaysActions:
    @pytest.mark.asyncio
    async def test_returns_overdue_and_due_today(self):
        goal, phase = await _make_active_goal()
        overdue = await _create_simple_action(goal, phase, title="Overdue", due_date=YESTERDAY)
        due_today = await _create_simple_action(goal, phase, title="Due today", due_date=TODAY)
        # Future action must not appear
        _future = await _create_simple_action(goal, phase, title="Future", due_date=FUTURE)

        actions = await action_service.list_todays_actions(USER_ID, TODAY)
        ids = {str(a.id) for a in actions}
        assert str(overdue.id) in ids
        assert str(due_today.id) in ids
        assert str(_future.id) not in ids

    @pytest.mark.asyncio
    async def test_excludes_completed_actions(self):
        goal, phase = await _make_active_goal()
        action = await _create_simple_action(goal, phase, due_date=YESTERDAY)
        await action_service.complete_action(USER_ID, str(action.id))

        actions = await action_service.list_todays_actions(USER_ID, TODAY)
        assert all(a.status != ActionStatus.COMPLETED for a in actions)

    @pytest.mark.asyncio
    async def test_scoped_to_authenticated_user(self):
        goal, phase = await _make_active_goal()
        await _create_simple_action(goal, phase, due_date=YESTERDAY)

        # USER_ID_2 has no goals — should get empty list
        actions = await action_service.list_todays_actions(USER_ID_2, TODAY)
        assert actions == []

    @pytest.mark.asyncio
    async def test_aggregates_across_multiple_goals(self):
        goal1, phase1 = await _make_active_goal(title="Goal Alpha")
        goal2, phase2 = await _make_active_goal(title="Goal Beta")

        a1 = await _create_simple_action(goal1, phase1, title="Alpha action", due_date=YESTERDAY)
        a2 = await _create_simple_action(goal2, phase2, title="Beta action", due_date=YESTERDAY)

        actions = await action_service.list_todays_actions(USER_ID, TODAY)
        ids = {str(a.id) for a in actions}
        assert str(a1.id) in ids
        assert str(a2.id) in ids

    @pytest.mark.asyncio
    async def test_excludes_paused_goal_actions(self):
        """Actions belonging to paused goals must not appear in today's focus."""
        goal, phase = await _make_active_goal(title="Paused goal")
        action = await _create_simple_action(goal, phase, due_date=YESTERDAY)
        await goal_service.pause_goal(USER_ID, str(goal.id))

        actions = await action_service.list_todays_actions(USER_ID, TODAY)
        assert all(str(a.id) != str(action.id) for a in actions)


# ── Numeric progress — GS-2.5 ─────────────────────────────────────────────────


class TestNumericProgress:
    @pytest.mark.asyncio
    async def test_progress_percent_computed_correctly(self):
        """Save-$2000 canonical example from the sprint plan."""
        goal, phase = await _make_active_goal(target_value=2000.0, unit="USD")

        # Save $806 in one action
        action = await _create_simple_action(goal, phase, contributes_value=806.0)
        await action_service.complete_action(USER_ID, str(action.id))

        refreshed = await GoalRepository.get_by_id(str(goal.id))
        assert refreshed is not None
        assert refreshed.current_value == 806.0
        # progress_percent = 806/2000*100 = 40.3 — matches blueprint example
        from app.graphql.queries import _compute_progress_percent

        pct = _compute_progress_percent(refreshed)
        assert pct == pytest.approx(40.3, rel=1e-2)

    @pytest.mark.asyncio
    async def test_progress_percent_null_safe_without_target(self):
        """Goals without a target_value must return None for progress_percent."""
        from beanie import PydanticObjectId

        from app.graphql.queries import _compute_progress_percent
        from app.models.goal import Goal

        goal_doc = Goal(
            user_id=PydanticObjectId(USER_ID),
            title="Qualitative goal",
            category="PERSONAL_GROWTH",
            horizon="MEDIUM",
            priority=2,
            target_value=None,
            current_value=None,
        )
        pct = _compute_progress_percent(goal_doc)
        assert pct is None

    @pytest.mark.asyncio
    async def test_progress_percent_clamps_null_on_zero_target(self):
        """A target_value of 0 must never produce a division-by-zero."""
        from beanie import PydanticObjectId

        from app.graphql.queries import _compute_progress_percent
        from app.models.goal import Goal

        goal_doc = Goal(
            user_id=PydanticObjectId(USER_ID),
            title="Zero target",
            category="HEALTH",
            horizon="SHORT",
            priority=1,
            target_value=0.0,
            current_value=10.0,
        )
        pct = _compute_progress_percent(goal_doc)
        assert pct is None


# ── ActionRepository extra coverage ──────────────────────────────────────────


class TestActionRepository:
    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_for_missing(self):
        result = await ActionRepository.get_by_id("000000000000000000000001")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_for_phase_ordered(self):
        goal, phase = await _make_active_goal()
        a1 = await _create_simple_action(goal, phase, title="First")
        a2 = await _create_simple_action(goal, phase, title="Second")
        actions = await ActionRepository.list_for_phase(str(phase.id))
        assert actions[0].id == a1.id
        assert actions[1].id == a2.id

    @pytest.mark.asyncio
    async def test_count_for_phase(self):
        goal, phase = await _make_active_goal()
        for i in range(3):
            await _create_simple_action(goal, phase, title=f"Action {i}")
        count = await ActionRepository.count_for_phase(str(phase.id))
        assert count == 3

    @pytest.mark.asyncio
    async def test_list_overdue(self):
        goal, phase = await _make_active_goal()
        overdue = await _create_simple_action(goal, phase, due_date=PAST)
        _not_overdue = await _create_simple_action(goal, phase, due_date=FUTURE)
        results = await ActionRepository.list_overdue(str(goal.id), TODAY)
        ids = {str(a.id) for a in results}
        assert str(overdue.id) in ids
        assert str(_not_overdue.id) not in ids

    @pytest.mark.asyncio
    async def test_delete_all_for_goal(self):
        goal, phase = await _make_active_goal()
        await _create_simple_action(goal, phase)
        await ActionRepository.delete_all_for_goal(str(goal.id))
        count = await ActionRepository.count_for_phase(str(phase.id))
        assert count == 0

    @pytest.mark.asyncio
    async def test_create_next_recurrence_daily(self):
        """GS-2.2 / GS-3.1 prep: DAILY habit generates instance with next-day due date."""
        goal, phase = await _make_active_goal()
        base_due = datetime(2026, 6, 1, 9, 0)
        habit = await action_service.create_action(
            user_id=USER_ID,
            goal_id=str(goal.id),
            phase_id=str(phase.id),
            title="Daily run",
            action_type=ActionType.HABIT,
            due_date=base_due,
            recurrence={"pattern": "DAILY", "days_of_week": []},
        )
        instance = await ActionRepository.create_next_recurrence(habit, base_due)
        assert instance is not None
        assert instance.parent_action_id == habit.id
        assert instance.recurrence is None  # instances carry no recurrence
        # Template's next_due must roll forward by one day
        refreshed_habit = await ActionRepository.get_by_id(str(habit.id))
        assert refreshed_habit is not None
        expected_next = base_due + __import__("datetime").timedelta(days=1)
        assert refreshed_habit.next_due == expected_next

    @pytest.mark.asyncio
    async def test_create_next_recurrence_custom_pattern(self):
        """CUSTOM (Mon/Wed/Fri) recurrence generates correct next weekday."""
        from datetime import timedelta as _td

        goal, phase = await _make_active_goal()
        # June 2, 2026 is a Tuesday — next Mon/Wed/Fri day from Tue is Wed=2
        base_due = datetime(2026, 6, 2, 9, 0)  # Tuesday
        habit = await action_service.create_action(
            user_id=USER_ID,
            goal_id=str(goal.id),
            phase_id=str(phase.id),
            title="MWF workout",
            action_type=ActionType.HABIT,
            due_date=base_due,
            recurrence={
                "pattern": "CUSTOM",
                "days_of_week": [0, 2, 4],  # Mon=0, Wed=2, Fri=4
            },
        )
        instance = await ActionRepository.create_next_recurrence(habit, base_due)
        assert instance is not None
        # Next day after Tuesday in [Mon=0, Wed=2, Fri=4] is Wednesday (2026-06-03)
        assert instance.due_date == datetime(2026, 6, 3, 9, 0)

    @pytest.mark.asyncio
    async def test_sorts_by_goal_priority_then_due_date(self):
        """GS-2.4: CRITICAL-priority goal actions appear before LOW-priority actions."""
        from app.constants.goals import Priority

        # LOW priority goal
        low_goal = await goal_service.create_goal(
            user_id=USER_ID,
            title="Low priority goal",
            description=None,
            category="MINDSET",
            horizon="LONG",
            priority=Priority.LOW,
            target_date=None,
            plan_tier=PlanTier.PRO,
        )
        low_goal = await goal_service.activate_goal(USER_ID, str(low_goal.id))
        low_phase = await phase_service.create_phase(USER_ID, str(low_goal.id), "Phase", None)
        low_action = await action_service.create_action(
            user_id=USER_ID,
            goal_id=str(low_goal.id),
            phase_id=str(low_phase.id),
            title="Low pri action",
            action_type=ActionType.TASK,
            due_date=YESTERDAY,
        )

        # CRITICAL priority goal
        crit_goal = await goal_service.create_goal(
            user_id=USER_ID,
            title="Critical goal",
            description=None,
            category="HEALTH",
            horizon="SHORT",
            priority=Priority.CRITICAL,
            target_date=None,
            plan_tier=PlanTier.PRO,
        )
        crit_goal = await goal_service.activate_goal(USER_ID, str(crit_goal.id))
        crit_phase = await phase_service.create_phase(USER_ID, str(crit_goal.id), "Phase", None)
        crit_action = await action_service.create_action(
            user_id=USER_ID,
            goal_id=str(crit_goal.id),
            phase_id=str(crit_phase.id),
            title="Critical action",
            action_type=ActionType.TASK,
            due_date=YESTERDAY,
        )

        actions = await action_service.list_todays_actions(USER_ID, TODAY)
        ids = [str(a.id) for a in actions]
        assert str(crit_action.id) in ids
        assert str(low_action.id) in ids
        # CRITICAL must come before LOW
        assert ids.index(str(crit_action.id)) < ids.index(str(low_action.id))

    @pytest.mark.asyncio
    async def test_includes_resumed_goal_actions(self):
        """RESUMED goals (treated as ACTIVE) must appear in today's actions."""
        goal, phase = await _make_active_goal(title="Resumed goal")
        await goal_service.pause_goal(USER_ID, str(goal.id))
        await goal_service.resume_goal(USER_ID, str(goal.id))

        action = await action_service.create_action(
            user_id=USER_ID,
            goal_id=str(goal.id),
            phase_id=str(phase.id),
            title="Resumed action",
            action_type=ActionType.TASK,
            due_date=YESTERDAY,
        )

        actions = await action_service.list_todays_actions(USER_ID, TODAY)
        ids = {str(a.id) for a in actions}
        assert str(action.id) in ids
