"""
GS-3.1: Unit tests for ActionRepository.create_next_recurrence.

Verifies that every recurrence pattern generates the correct next date,
including across month and year boundaries, and that the CUSTOM
(Mon/Wed/Fri) pattern is correctly computed.

Design note: tests verify date arithmetic only — no shaming of missed
recurrences, no "catch-up" logic, no "you missed N habits" assertions.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.repositories.action_repository import ActionRepository

# ── Pure date arithmetic tests (no database) ────────────────────────────────


class TestNextDateForPattern:
    """Unit tests for _next_date_for_pattern — pure function, no I/O."""

    def _next(self, pattern: str, days_of_week: list = None, current: datetime = None) -> datetime:
        if current is None:
            current = datetime(2026, 6, 15, 9, 0)  # Monday
        return ActionRepository._next_date_for_pattern(
            pattern=pattern,
            days_of_week=days_of_week or [],
            current=current,
        )

    # ── DAILY ────────────────────────────────────────────────────────────────

    def test_daily_increments_by_one_day(self):
        base = datetime(2026, 6, 15)
        result = self._next("DAILY", current=base)
        assert result == datetime(2026, 6, 16)

    def test_daily_crosses_month_boundary(self):
        base = datetime(2026, 6, 30)
        result = self._next("DAILY", current=base)
        assert result == datetime(2026, 7, 1)

    def test_daily_crosses_year_boundary(self):
        base = datetime(2025, 12, 31)
        result = self._next("DAILY", current=base)
        assert result == datetime(2026, 1, 1)

    # ── WEEKDAYS ─────────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "day_offset,expected_offset",
        [
            (0, 1),  # Mon → Tue (+1)
            (1, 1),  # Tue → Wed (+1)
            (2, 1),  # Wed → Thu (+1)
            (3, 1),  # Thu → Fri (+1)
            (4, 3),  # Fri → Mon (+3)
            (5, 2),  # Sat → Mon (+2)
            (6, 1),  # Sun → Mon (+1)
        ],
    )
    def test_weekdays_skip_weekend(self, day_offset, expected_offset):
        # Start from a known Monday (2026-06-15)
        monday = datetime(2026, 6, 15)
        base = monday + timedelta(days=day_offset)
        result = self._next("WEEKDAYS", current=base)
        expected = base + timedelta(days=expected_offset)
        assert result == expected, f"From {base.strftime('%A')} expected +{expected_offset} days"

    # ── WEEKENDS ─────────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "day_offset,expected_offset",
        [
            (0, 5),  # Mon → Sat (+5)
            (1, 4),  # Tue → Sat (+4)
            (2, 3),  # Wed → Sat (+3)
            (3, 2),  # Thu → Sat (+2)
            (4, 1),  # Fri → Sat (+1)
            (5, 7),  # Sat → next Sat (+7)
            (6, 6),  # Sun → next Sat (+6)
        ],
    )
    def test_weekends_lands_on_saturday(self, day_offset, expected_offset):
        monday = datetime(2026, 6, 15)
        base = monday + timedelta(days=day_offset)
        result = self._next("WEEKENDS", current=base)
        expected = base + timedelta(days=expected_offset)
        assert result == expected
        assert result.weekday() == 5, "Next weekend occurrence must be a Saturday"

    # ── WEEKLY ───────────────────────────────────────────────────────────────

    def test_weekly_adds_seven_days(self):
        base = datetime(2026, 6, 15)  # Monday
        result = self._next("WEEKLY", current=base)
        assert result == datetime(2026, 6, 22)
        assert result.weekday() == 0  # still a Monday

    # ── BIWEEKLY ─────────────────────────────────────────────────────────────

    def test_biweekly_adds_fourteen_days(self):
        base = datetime(2026, 6, 15)
        result = self._next("BIWEEKLY", current=base)
        assert result == datetime(2026, 6, 29)

    # ── MONTHLY ──────────────────────────────────────────────────────────────

    def test_monthly_same_day_next_month(self):
        base = datetime(2026, 6, 15)
        result = self._next("MONTHLY", current=base)
        assert result == datetime(2026, 7, 15)

    def test_monthly_crosses_year(self):
        base = datetime(2025, 12, 10)
        result = self._next("MONTHLY", current=base)
        assert result == datetime(2026, 1, 10)

    # ── CUSTOM ───────────────────────────────────────────────────────────────

    def test_custom_mon_wed_fri_from_monday(self):
        # [0, 2, 4] = Mon, Wed, Fri.  From Monday → next is Wednesday (+2).
        monday = datetime(2026, 6, 15)
        result = self._next("CUSTOM", days_of_week=[0, 2, 4], current=monday)
        assert result.weekday() == 2, "From Monday, next Mon/Wed/Fri is Wednesday"

    def test_custom_mon_wed_fri_from_friday(self):
        # From Friday → next Mon (+3 days)
        friday = datetime(2026, 6, 19)
        result = self._next("CUSTOM", days_of_week=[0, 2, 4], current=friday)
        assert result.weekday() == 0, "From Friday, next Mon/Wed/Fri is Monday"

    def test_custom_mon_wed_fri_from_wednesday(self):
        # From Wednesday → next Friday (+2)
        wednesday = datetime(2026, 6, 17)
        result = self._next("CUSTOM", days_of_week=[0, 2, 4], current=wednesday)
        assert result.weekday() == 4, "From Wednesday, next Mon/Wed/Fri is Friday"

    def test_custom_empty_days_falls_back(self):
        # No days_of_week configured — should not raise, falls back to +1 day
        base = datetime(2026, 6, 15)
        result = self._next("CUSTOM", days_of_week=[], current=base)
        assert result == base + timedelta(days=1)

    def test_custom_single_day_weekly_equivalent(self):
        # Only Tuesdays [1]: from Mon → Tue (+1), from Tue → next Tue (+7)
        monday = datetime(2026, 6, 15)
        result = self._next("CUSTOM", days_of_week=[1], current=monday)
        assert result.weekday() == 1
        # From that Tuesday:
        result2 = self._next("CUSTOM", days_of_week=[1], current=result)
        assert result2 == result + timedelta(days=7)


# ── Integration tests: full create_next_recurrence flow ─────────────────────


class TestCreateNextRecurrence:
    """Tests the full create_next_recurrence path including DB writes."""

    @pytest.mark.asyncio
    async def test_daily_habit_generates_correct_next_instance(self):
        from datetime import datetime

        from beanie import PydanticObjectId

        from app.constants.goals import ActionStatus, ActionType, RecurrencePattern
        from app.models.action import Action, Recurrence
        from app.models.goal import Goal
        from app.models.phase import Phase

        user_oid = PydanticObjectId("64f0000000000000000000aa")
        goal = Goal(
            user_id=user_oid,
            title="Daily run",
            category="HEALTH",
            horizon="SHORT",
            priority=2,
            status="ACTIVE",
        )
        await goal.insert()

        phase = Phase(goal_id=goal.id, user_id=user_oid, title="Phase 1", order=0, status="ACTIVE")
        await phase.insert()

        base_date = datetime(2026, 6, 15, 7, 0)
        habit = Action(
            goal_id=goal.id,
            phase_id=phase.id,
            user_id=user_oid,
            title="Run 5km",
            action_type=ActionType.HABIT,
            status=ActionStatus.PENDING,
            order=0,
            next_due=base_date,
            recurrence=Recurrence(pattern=RecurrencePattern.DAILY),
        )
        await habit.insert()

        as_of = datetime(2026, 6, 15, 8, 0)
        new_action = await ActionRepository.create_next_recurrence(habit, as_of)

        assert new_action is not None
        assert new_action.due_date == datetime(2026, 6, 16, 7, 0)
        assert new_action.parent_action_id == habit.id
        assert new_action.recurrence is None  # instances don't carry recurrence
        assert new_action.status == ActionStatus.PENDING

        # Template should be rolled forward
        await habit.sync()
        assert habit.next_due == datetime(2026, 6, 16, 7, 0)
        assert habit.recurrence.generation_count == 1

    @pytest.mark.asyncio
    async def test_custom_mon_wed_fri_generates_correct_sequence(self):
        """A CUSTOM habit generates exactly the right dates across a week."""
        from datetime import datetime

        from beanie import PydanticObjectId

        from app.constants.goals import ActionStatus, ActionType, RecurrencePattern
        from app.models.action import Action, Recurrence
        from app.models.goal import Goal
        from app.models.phase import Phase

        user_oid = PydanticObjectId("64f0000000000000000000ab")
        goal = Goal(
            user_id=user_oid,
            title="Weight training",
            category="HEALTH",
            horizon="MEDIUM",
            priority=3,
            status="ACTIVE",
        )
        await goal.insert()

        phase = Phase(goal_id=goal.id, user_id=user_oid, title="P1", order=0, status="ACTIVE")
        await phase.insert()

        monday = datetime(2026, 6, 15, 8, 0)
        habit = Action(
            goal_id=goal.id,
            phase_id=phase.id,
            user_id=user_oid,
            title="Lift weights",
            action_type=ActionType.HABIT,
            status=ActionStatus.PENDING,
            order=0,
            next_due=monday,
            recurrence=Recurrence(
                pattern=RecurrencePattern.CUSTOM,
                days_of_week=[0, 2, 4],  # Mon, Wed, Fri
            ),
        )
        await habit.insert()

        as_of = monday
        # Monday → next is Wednesday
        instance1 = await ActionRepository.create_next_recurrence(habit, as_of)
        assert instance1 is not None
        assert instance1.due_date.weekday() == 2, "Instance 1 should be Wednesday"

        # Wednesday → next is Friday
        await habit.sync()
        instance2 = await ActionRepository.create_next_recurrence(habit, as_of)
        assert instance2 is not None
        assert instance2.due_date.weekday() == 4, "Instance 2 should be Friday"

        # Friday → next is Monday
        await habit.sync()
        instance3 = await ActionRepository.create_next_recurrence(habit, as_of)
        assert instance3 is not None
        assert instance3.due_date.weekday() == 0, "Instance 3 should be Monday"
        assert habit.recurrence.generation_count == 3

    @pytest.mark.asyncio
    async def test_no_recurrence_returns_none(self):
        """Actions without recurrence config return None gracefully."""
        from datetime import datetime

        from beanie import PydanticObjectId

        from app.constants.goals import ActionStatus, ActionType
        from app.models.action import Action
        from app.models.goal import Goal
        from app.models.phase import Phase

        user_oid = PydanticObjectId("64f0000000000000000000ac")
        goal = Goal(
            user_id=user_oid,
            title="Task goal",
            category="CAREER",
            horizon="SHORT",
            priority=2,
            status="ACTIVE",
        )
        await goal.insert()

        phase = Phase(goal_id=goal.id, user_id=user_oid, title="P1", order=0, status="ACTIVE")
        await phase.insert()

        task = Action(
            goal_id=goal.id,
            phase_id=phase.id,
            user_id=user_oid,
            title="One-off task",
            action_type=ActionType.TASK,
            status=ActionStatus.PENDING,
            order=0,
            recurrence=None,
        )
        await task.insert()

        result = await ActionRepository.create_next_recurrence(task, datetime.utcnow())
        assert result is None
