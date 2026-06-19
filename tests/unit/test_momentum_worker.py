"""
GS-3.2 / GS-3.3: Unit tests for momentum worker enrichment.

Verifies:
  - _compute_completion_streak returns the correct consecutive-day count
  - Streak silently resets on a gap (no "you broke it" assertion)
  - Enriched momentum event payload contains required fields
  - No shame language in any payload key names
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.workers.momentum_worker import _compute_completion_streak


class TestComputeCompletionStreak:
    """Pure unit tests — no database, no event publishing."""

    def _dates(self, *offsets: int) -> list[datetime]:
        """Build datetime list from day offsets relative to today (0 = today, 1 = yesterday)."""
        today = datetime.now(UTC)
        return [today - timedelta(days=d) for d in offsets]

    def test_empty_list_returns_zero(self):
        assert _compute_completion_streak([]) == 0

    def test_only_today_returns_one(self):
        result = _compute_completion_streak(self._dates(0))
        assert result == 1

    def test_consecutive_three_days(self):
        result = _compute_completion_streak(self._dates(0, 1, 2))
        assert result == 3

    def test_gap_breaks_streak(self):
        # Today and 3 days ago — gap at day 2 means streak = 1 (only today)
        result = _compute_completion_streak(self._dates(0, 3))
        assert result == 1

    def test_yesterday_and_today(self):
        result = _compute_completion_streak(self._dates(0, 1))
        assert result == 2

    def test_five_consecutive_days(self):
        result = _compute_completion_streak(self._dates(0, 1, 2, 3, 4))
        assert result == 5

    def test_gap_after_long_streak(self):
        # 5 consecutive from 6 days ago, but gap at day 0/1 breaks it
        result = _compute_completion_streak(self._dates(2, 3, 4, 5, 6))
        assert result == 0  # gap between yesterday (1) and today (0)

    def test_duplicates_on_same_day_count_as_one(self):
        # Multiple completions on the same day should not inflate the streak
        today = datetime.now(UTC)
        dates = [today, today + timedelta(hours=1), today - timedelta(days=1)]
        result = _compute_completion_streak(dates)
        assert result == 2

    def test_streak_does_not_use_shame_language(self):
        """Ensure published event payloads never contain shame-language keys.

        Checks dictionary key names only, not internal log strings (which may
        legitimately use words like 'failed' for error logging).
        """
        import inspect

        import app.workers.momentum_worker as wm

        source = inspect.getsource(wm)
        # Shame-language dictionary keys that must never appear in published payloads
        shame_keys = ("missed_days", "broken_streak", "shame_score", "failed_days")
        for key in shame_keys:
            assert f'"{key}"' not in source and f"'{key}'" not in source, (
                f"Shame payload key '{key}' found in momentum_worker — "
                "see §3 engagement philosophy in SPRINT_PLAN.md"
            )


class TestMomentumEventPayload:
    """Verify the enriched event payload shape (GS-3.3)."""

    @pytest.mark.asyncio
    async def test_momentum_low_event_includes_required_fields(self):
        """recalculate_momentum_for_all publishes payload with goal_title,
        momentum_score, and completion_streak — no shame language."""
        from unittest.mock import patch

        from beanie import PydanticObjectId

        from app.constants.goals import GoalStatus
        from app.models.goal import Goal

        user_oid = PydanticObjectId("64f0000000000000000000aa")
        goal = Goal(
            user_id=user_oid,
            title="Morning yoga",
            category="HEALTH",
            horizon="SHORT",
            priority=2,
            status=GoalStatus.ACTIVE,
            momentum_score=85.0,  # starts high, will drop to 0 (no actions)
        )
        await goal.insert()

        published_events: list[dict] = []

        async def capture_event(event_type, payload):
            published_events.append({"event_type": event_type, "payload": payload})

        with patch("app.workers.momentum_worker.publish_event", side_effect=capture_event):
            from app.workers.momentum_worker import recalculate_momentum_for_all

            await recalculate_momentum_for_all()

        # Should have fired a MOMENTUM_LOW event since score dropped from 85 → 0
        low_events = [e for e in published_events if e["event_type"] == "goal.momentum_low"]
        assert len(low_events) == 1, "Expected exactly one momentum_low event"

        payload = low_events[0]["payload"]
        assert "goal_title" in payload, "Payload must include goal_title for notification service"
        assert "momentum_score" in payload
        assert "completion_streak" in payload
        assert payload["goal_title"] == "Morning yoga"

        # Verify no shame language in payload keys
        for key in payload:
            for forbidden in ("missed", "broken", "shame", "failed", "lost"):
                assert (
                    forbidden not in key.lower()
                ), f"Shame language '{forbidden}' found in payload key '{key}'"
