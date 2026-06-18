"""
GS-1.1: Unit tests for PhaseRepository.
GS-2.1 (partial): Unit tests for phase_service lifecycle.

Tests all PhaseRepository methods and the phase unlock-on-complete chain.
"""

import pytest

from app.constants.goals import PhaseStatus
from app.constants.plans import PlanTier
from app.core.exceptions.base import (
    GoalNotFoundError,
    InvalidPhaseStateError,
    PhaseLimitExceededError,
    PhaseNotFoundError,
)
from app.repositories.phase_repository import PhaseRepository
from app.services import goal_service, phase_service

USER_ID = "64f0000000000000000000aa"
USER_ID_2 = "64f0000000000000000000bb"


async def _make_active_goal(title: str = "Marathon"):
    goal = await goal_service.create_goal(
        user_id=USER_ID,
        title=title,
        description=None,
        category="HEALTH",
        horizon="MEDIUM",
        priority=2,
        target_date=None,
        plan_tier=PlanTier.PRO,
    )
    return await goal_service.activate_goal(USER_ID, str(goal.id))


# ── PhaseRepository ───────────────────────────────────────────────────────────


class TestPhaseRepository:
    @pytest.mark.asyncio
    async def test_create_and_get_by_id(self):
        goal = await _make_active_goal()
        phase = await PhaseRepository.create(
            goal_id=str(goal.id),
            user_id=USER_ID,
            title="Foundation Phase",
            description="Build the base",
            order=0,
        )
        fetched = await PhaseRepository.get_by_id(str(phase.id))
        assert fetched is not None
        assert fetched.title == "Foundation Phase"

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_for_missing(self):
        result = await PhaseRepository.get_by_id("000000000000000000000001")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_for_goal_ordered(self):
        goal = await _make_active_goal()
        await PhaseRepository.create(str(goal.id), USER_ID, "Phase A", None, 1)
        await PhaseRepository.create(str(goal.id), USER_ID, "Phase B", None, 0)
        phases = await PhaseRepository.list_for_goal(str(goal.id))
        assert len(phases) == 2
        assert phases[0].order == 0
        assert phases[1].order == 1

    @pytest.mark.asyncio
    async def test_get_active_phase(self):
        goal = await _make_active_goal()
        await PhaseRepository.create(str(goal.id), USER_ID, "Phase A", None, 0)
        await PhaseRepository.update_status(
            str((await PhaseRepository.list_for_goal(str(goal.id)))[0].id), PhaseStatus.ACTIVE
        )
        active = await PhaseRepository.get_active_phase(str(goal.id))
        assert active is not None
        assert active.status == PhaseStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_count_for_goal(self):
        goal = await _make_active_goal()
        for i in range(3):
            await PhaseRepository.create(str(goal.id), USER_ID, f"Phase {i}", None, i)
        count = await PhaseRepository.count_for_goal(str(goal.id))
        assert count == 3

    @pytest.mark.asyncio
    async def test_delete_all_for_goal(self):
        goal = await _make_active_goal()
        await PhaseRepository.create(str(goal.id), USER_ID, "Phase", None, 0)
        await PhaseRepository.delete_all_for_goal(str(goal.id))
        count = await PhaseRepository.count_for_goal(str(goal.id))
        assert count == 0


# ── phase_service ─────────────────────────────────────────────────────────────


class TestCreatePhase:
    @pytest.mark.asyncio
    async def test_first_phase_is_active(self):
        goal = await _make_active_goal()
        phase = await phase_service.create_phase(USER_ID, str(goal.id), "Foundation", None)
        assert phase.status == PhaseStatus.ACTIVE
        assert phase.unlocked_at is not None

    @pytest.mark.asyncio
    async def test_second_phase_is_locked(self):
        goal = await _make_active_goal()
        await phase_service.create_phase(USER_ID, str(goal.id), "Phase 1", None)
        p2 = await phase_service.create_phase(USER_ID, str(goal.id), "Phase 2", None)
        assert p2.status == PhaseStatus.LOCKED

    @pytest.mark.asyncio
    async def test_enforces_max_phases(self):
        goal = await _make_active_goal()
        for i in range(6):
            await phase_service.create_phase(USER_ID, str(goal.id), f"Phase {i}", None)
        with pytest.raises(PhaseLimitExceededError):
            await phase_service.create_phase(USER_ID, str(goal.id), "Phase overflow", None)

    @pytest.mark.asyncio
    async def test_ownership_check(self):
        goal = await _make_active_goal()
        with pytest.raises(GoalNotFoundError):
            await phase_service.create_phase(USER_ID_2, str(goal.id), "Phase", None)


class TestCompletePhase:
    @pytest.mark.asyncio
    async def test_complete_unlocks_next_phase(self):
        goal = await _make_active_goal()
        p1 = await phase_service.create_phase(USER_ID, str(goal.id), "Phase 1", None)
        p2 = await phase_service.create_phase(USER_ID, str(goal.id), "Phase 2", None)

        await phase_service.complete_phase(USER_ID, str(p1.id))

        next_phase = await PhaseRepository.get_by_id(str(p2.id))
        assert next_phase is not None
        assert next_phase.status == PhaseStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_complete_last_phase_no_error(self):
        goal = await _make_active_goal()
        p1 = await phase_service.create_phase(USER_ID, str(goal.id), "Only Phase", None)
        # Should not raise when there is no next phase to unlock
        result = await phase_service.complete_phase(USER_ID, str(p1.id))
        assert result.status == PhaseStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cannot_complete_already_completed_phase(self):
        goal = await _make_active_goal()
        p1 = await phase_service.create_phase(USER_ID, str(goal.id), "Phase", None)
        await phase_service.complete_phase(USER_ID, str(p1.id))
        with pytest.raises(InvalidPhaseStateError):
            await phase_service.complete_phase(USER_ID, str(p1.id))

    @pytest.mark.asyncio
    async def test_ownership_check_on_complete(self):
        goal = await _make_active_goal()
        p1 = await phase_service.create_phase(USER_ID, str(goal.id), "Phase", None)
        with pytest.raises(PhaseNotFoundError):
            await phase_service.complete_phase(USER_ID_2, str(p1.id))


class TestSkipPhase:
    @pytest.mark.asyncio
    async def test_skip_active_unlocks_next(self):
        goal = await _make_active_goal()
        p1 = await phase_service.create_phase(USER_ID, str(goal.id), "Phase 1", None)
        p2 = await phase_service.create_phase(USER_ID, str(goal.id), "Phase 2", None)

        await phase_service.skip_phase(USER_ID, str(p1.id), reason="Not relevant")

        p2_refreshed = await PhaseRepository.get_by_id(str(p2.id))
        assert p2_refreshed is not None
        assert p2_refreshed.status == PhaseStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_skip_records_reason(self):
        goal = await _make_active_goal()
        p1 = await phase_service.create_phase(USER_ID, str(goal.id), "Phase", None)
        result = await phase_service.skip_phase(USER_ID, str(p1.id), reason="Out of scope")
        assert "Out of scope" in (result.note or "")


class TestReorderPhases:
    @pytest.mark.asyncio
    async def test_reorder_updates_order_field(self):
        goal = await _make_active_goal()
        p1 = await phase_service.create_phase(USER_ID, str(goal.id), "Phase A", None)
        p2 = await phase_service.create_phase(USER_ID, str(goal.id), "Phase B", None)
        p3 = await phase_service.create_phase(USER_ID, str(goal.id), "Phase C", None)

        # Reverse order: C, A, B
        reordered = await phase_service.reorder_phases(
            USER_ID, str(goal.id), [str(p3.id), str(p1.id), str(p2.id)]
        )
        assert reordered[0].title == "Phase C"
        assert reordered[0].order == 0
        assert reordered[1].title == "Phase A"
        assert reordered[1].order == 1
