"""
GS-1.4: Unit tests that assert every Strawberry GraphQL enum value
exactly matches its constants-module counterpart.

If a constant is added/renamed but the GQL enum is not updated,
this test will catch the divergence before it silently breaks clients.
"""

from app.constants.goals import (
    ActionStatus,
    ActionType,
    DecompositionState,
    GoalCategory,
    GoalHorizon,
    GoalStatus,
    PhaseStatus,
    Priority,
    RecurrencePattern,
)
from app.graphql.enums import (
    ActionStatusEnum,
    ActionTypeEnum,
    DecompositionStateEnum,
    GoalCategoryEnum,
    GoalHorizonEnum,
    GoalStatusEnum,
    PhaseStatusEnum,
    PriorityEnum,
    RecurrencePatternEnum,
)


def _constant_values(cls: type) -> set:
    """Extract string/int values from a plain class used as an enum namespace."""
    return {v for k, v in cls.__dict__.items() if not k.startswith("_")}


def _gql_values(enum_cls) -> set:
    return {member.value for member in enum_cls}


class TestGoalStatusEnumSync:
    def test_all_goal_statuses_present_in_gql(self):
        constants = _constant_values(GoalStatus)
        gql = _gql_values(GoalStatusEnum)
        assert constants == gql, (
            f"GoalStatus constants not in GQL: {constants - gql} | "
            f"GQL values not in constants: {gql - constants}"
        )


class TestGoalCategoryEnumSync:
    def test_all_categories_present_in_gql(self):
        constants = _constant_values(GoalCategory)
        gql = _gql_values(GoalCategoryEnum)
        assert constants == gql


class TestGoalHorizonEnumSync:
    def test_all_horizons_present_in_gql(self):
        constants = _constant_values(GoalHorizon)
        gql = _gql_values(GoalHorizonEnum)
        assert constants == gql


class TestPriorityEnumSync:
    def test_all_priorities_present_in_gql(self):
        constants = _constant_values(Priority)
        gql = _gql_values(PriorityEnum)
        assert constants == gql


class TestDecompositionStateEnumSync:
    def test_all_decomposition_states_present_in_gql(self):
        constants = _constant_values(DecompositionState)
        gql = _gql_values(DecompositionStateEnum)
        assert constants == gql


class TestPhaseStatusEnumSync:
    def test_all_phase_statuses_present_in_gql(self):
        constants = _constant_values(PhaseStatus)
        gql = _gql_values(PhaseStatusEnum)
        assert constants == gql


class TestActionStatusEnumSync:
    def test_all_action_statuses_present_in_gql(self):
        constants = _constant_values(ActionStatus)
        gql = _gql_values(ActionStatusEnum)
        assert constants == gql


class TestActionTypeEnumSync:
    def test_all_action_types_present_in_gql(self):
        constants = _constant_values(ActionType)
        gql = _gql_values(ActionTypeEnum)
        assert constants == gql


class TestRecurrencePatternEnumSync:
    def test_all_recurrence_patterns_present_in_gql(self):
        constants = _constant_values(RecurrencePattern)
        gql = _gql_values(RecurrencePatternEnum)
        assert constants == gql
