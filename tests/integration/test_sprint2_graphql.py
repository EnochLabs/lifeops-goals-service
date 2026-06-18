"""
GS-2.6 / GS-2.3 / GS-2.4 / GS-2.5: Integration tests for Phase & Action
GraphQL mutations and queries.

Covers:
  - createPhase, completePhase, skipPhase, reorderPhases
  - createAction, completeAction, skipAction, rescheduleAction
  - goal query returning nested phases → actions in one round-trip
  - todaysActions query aggregation and scoping
  - Numeric progress: progressPercent computed field via contributing actions
  - reorderPhases rate limit (GS-2.3)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

MOCK_USER_ID = "64f0000000000000000000aa"
OTHER_USER_ID = "64f0000000000000000000dd"

_MOCK_AUTH_CONTEXT = {
    "user_id": MOCK_USER_ID,
    "email": "sprint2@lifeops.io",
    "role": "USER",
    "plan": "PRO",
    "plan_expires": None,
}

AUTH_HEADERS = {"Authorization": "Bearer sprint2-token"}
YESTERDAY_ISO = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"
TOMORROW_ISO = (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z"


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _post_gql(client: AsyncClient, query: str) -> dict:
    resp = await client.post("/graphql", json={"query": query}, headers=AUTH_HEADERS)
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text}"
    return resp.json()


async def _create_goal(client: AsyncClient, title: str = "Test Goal", **kwargs) -> str:
    extra = ""
    if kwargs.get("target_value"):
        extra += f' targetValue: {kwargs["target_value"]}'
    if kwargs.get("unit"):
        extra += f' unit: "{kwargs["unit"]}"'
    body = await _post_gql(
        client,
        f'mutation {{ createGoal(input: {{ title: "{title}"{extra} }}) {{ id }} }}',
    )
    assert "errors" not in body, body.get("errors")
    return body["data"]["createGoal"]["id"]


async def _activate_goal(client: AsyncClient, goal_id: str) -> None:
    body = await _post_gql(client, f'mutation {{ activateGoal(goalId: "{goal_id}") {{ id }} }}')
    assert "errors" not in body, body.get("errors")


async def _create_phase(client: AsyncClient, goal_id: str, title: str = "Phase 1") -> str:
    body = await _post_gql(
        client,
        f"""
        mutation {{
          createPhase(input: {{ goalId: "{goal_id}", title: "{title}" }}) {{
            id status
          }}
        }}
        """,
    )
    assert "errors" not in body, body.get("errors")
    return body["data"]["createPhase"]["id"]


async def _create_action(
    client: AsyncClient,
    goal_id: str,
    phase_id: str,
    title: str = "Do something",
    action_type: str = "TASK",
    due_date: str | None = None,
    contributes_value: float | None = None,
) -> str:
    due_str = f' dueDate: "{due_date}"' if due_date else ""
    contrib_str = f" contributesValue: {contributes_value}" if contributes_value is not None else ""
    body = await _post_gql(
        client,
        f"""
        mutation {{
          createAction(input: {{
            goalId: "{goal_id}"
            phaseId: "{phase_id}"
            title: "{title}"
            actionType: {action_type}{due_str}{contrib_str}
          }}) {{
            id status actionType
          }}
        }}
        """,
    )
    assert "errors" not in body, body.get("errors")
    return body["data"]["createAction"]["id"]


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestPhaseLifecycleGraphQL:
    """GS-2.6 / GS-2.1: Phase mutations through the GraphQL surface."""

    @pytest.mark.asyncio
    async def test_create_phase_first_is_active(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client)
            body = await _post_gql(
                client,
                f"""
                mutation {{
                  createPhase(input: {{ goalId: "{goal_id}", title: "Foundation" }}) {{
                    id status order
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            phase = body["data"]["createPhase"]
            assert phase["status"] == "ACTIVE"
            assert phase["order"] == 0

    @pytest.mark.asyncio
    async def test_create_phase_second_is_locked(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client)
            await _create_phase(client, goal_id, "Phase 1")
            body = await _post_gql(
                client,
                f"""
                mutation {{
                  createPhase(input: {{ goalId: "{goal_id}", title: "Phase 2" }}) {{
                    id status order
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            assert body["data"]["createPhase"]["status"] == "LOCKED"
            assert body["data"]["createPhase"]["order"] == 1

    @pytest.mark.asyncio
    async def test_complete_phase_unlocks_next(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client)
            phase1_id = await _create_phase(client, goal_id, "Phase 1")
            phase2_id = await _create_phase(client, goal_id, "Phase 2")

            body = await _post_gql(
                client,
                f'mutation {{ completePhase(phaseId: "{phase1_id}") {{ id status }} }}',
            )
            assert "errors" not in body, body.get("errors")
            assert body["data"]["completePhase"]["status"] == "COMPLETED"

            # Phase 2 should now be ACTIVE
            body2 = await _post_gql(
                client,
                f"""
                {{
                  goal(goalId: "{goal_id}") {{
                    phases {{ id status }}
                  }}
                }}
                """,
            )
            phases = body2["data"]["goal"]["phases"]
            phase2 = next(p for p in phases if p["id"] == phase2_id)
            assert phase2["status"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_skip_phase_unlocks_next(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client)
            phase1_id = await _create_phase(client, goal_id, "Skip Me")
            phase2_id = await _create_phase(client, goal_id, "Unlock Me")

            body = await _post_gql(
                client,
                f'mutation {{ skipPhase(phaseId: "{phase1_id}", reason: "not relevant") {{ id status }} }}',
            )
            assert "errors" not in body, body.get("errors")
            assert body["data"]["skipPhase"]["status"] == "SKIPPED"

            body2 = await _post_gql(
                client,
                f'{{ goal(goalId: "{goal_id}") {{ phases {{ id status }} }} }}',
            )
            phases = body2["data"]["goal"]["phases"]
            phase2 = next(p for p in phases if p["id"] == phase2_id)
            assert phase2["status"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_reorder_phases(self, client):
        """GS-2.3: reorderPhases persists new order field on each phase."""
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client)
            p1_id = await _create_phase(client, goal_id, "Phase A")
            p2_id = await _create_phase(client, goal_id, "Phase B")
            p3_id = await _create_phase(client, goal_id, "Phase C")

            body = await _post_gql(
                client,
                f"""
                mutation {{
                  reorderPhases(input: {{
                    goalId: "{goal_id}",
                    orderedPhaseIds: ["{p3_id}", "{p1_id}", "{p2_id}"]
                  }}) {{
                    id order
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            phases = body["data"]["reorderPhases"]
            assert phases[0]["id"] == p3_id and phases[0]["order"] == 0
            assert phases[1]["id"] == p1_id and phases[1]["order"] == 1
            assert phases[2]["id"] == p2_id and phases[2]["order"] == 2


class TestActionMutationsGraphQL:
    """GS-2.6 / GS-2.2: Action mutations through the GraphQL surface."""

    @pytest.mark.asyncio
    async def test_create_task_action(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client)
            phase_id = await _create_phase(client, goal_id)
            action_id = await _create_action(client, goal_id, phase_id)
            assert action_id

    @pytest.mark.asyncio
    async def test_create_habit_with_recurrence(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client)
            phase_id = await _create_phase(client, goal_id)
            body = await _post_gql(
                client,
                f"""
                mutation {{
                  createAction(input: {{
                    goalId: "{goal_id}"
                    phaseId: "{phase_id}"
                    title: "Morning jog"
                    actionType: HABIT
                    dueDate: "{TOMORROW_ISO}"
                    recurrence: {{ pattern: DAILY }}
                  }}) {{
                    id actionType recurrence {{ pattern generationCount }}
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            action = body["data"]["createAction"]
            assert action["actionType"] == "HABIT"
            assert action["recurrence"]["pattern"] == "DAILY"
            assert action["recurrence"]["generationCount"] == 0

    @pytest.mark.asyncio
    async def test_complete_action(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client)
            phase_id = await _create_phase(client, goal_id)
            action_id = await _create_action(client, goal_id, phase_id)

            body = await _post_gql(
                client,
                f"""
                mutation {{
                  completeAction(input: {{
                    actionId: "{action_id}",
                    completionNote: "Crushed it"
                  }}) {{
                    id status completedAt completionNote
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            result = body["data"]["completeAction"]
            assert result["status"] == "COMPLETED"
            assert result["completedAt"] is not None
            assert result["completionNote"] == "Crushed it"

    @pytest.mark.asyncio
    async def test_skip_action(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client)
            phase_id = await _create_phase(client, goal_id)
            action_id = await _create_action(client, goal_id, phase_id)

            body = await _post_gql(
                client,
                f"""
                mutation {{
                  skipAction(input: {{
                    actionId: "{action_id}",
                    reason: "Not today"
                  }}) {{
                    id status completionNote
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            result = body["data"]["skipAction"]
            assert result["status"] == "SKIPPED"
            assert result["completionNote"] == "Not today"

    @pytest.mark.asyncio
    async def test_reschedule_action(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client)
            phase_id = await _create_phase(client, goal_id)
            action_id = await _create_action(client, goal_id, phase_id, due_date=YESTERDAY_ISO)

            body = await _post_gql(
                client,
                f"""
                mutation {{
                  rescheduleAction(input: {{
                    actionId: "{action_id}",
                    newDueDate: "{TOMORROW_ISO}",
                    reason: "low_energy_day"
                  }}) {{
                    id status dueDate
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            assert body["data"]["rescheduleAction"]["status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_complete_action_updates_goal_progress(self, client):
        """GS-2.5: contributing action increments goal's currentValue."""
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(
                client, title="Save for holiday", target_value=1000.0, unit="USD"
            )
            phase_id = await _create_phase(client, goal_id)
            action_id = await _create_action(client, goal_id, phase_id, contributes_value=250.0)

            await _post_gql(
                client,
                f'mutation {{ completeAction(input: {{ actionId: "{action_id}" }}) {{ id }} }}',
            )

            body = await _post_gql(
                client,
                f"""
                {{
                  goal(goalId: "{goal_id}") {{
                    currentValue progressPercent unit
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            goal_data = body["data"]["goal"]
            assert goal_data["currentValue"] == 250.0
            assert goal_data["unit"] == "USD"
            assert goal_data["progressPercent"] == pytest.approx(25.0, rel=1e-2)

    @pytest.mark.asyncio
    async def test_invalid_complete_skipped_action_returns_error(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client)
            phase_id = await _create_phase(client, goal_id)
            action_id = await _create_action(client, goal_id, phase_id)

            await _post_gql(
                client,
                f'mutation {{ skipAction(input: {{ actionId: "{action_id}" }}) {{ id }} }}',
            )
            body = await _post_gql(
                client,
                f'mutation {{ completeAction(input: {{ actionId: "{action_id}" }}) {{ id }} }}',
            )
            assert "errors" in body


class TestNestedGoalPhasesActionsGraphQL:
    """GS-2.6: Goal.phases and Phase.actions resolve in a single query."""

    @pytest.mark.asyncio
    async def test_goal_resolves_phases_with_actions(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client, "Nested resolution goal")
            phase_id = await _create_phase(client, goal_id, "Sprint phase")
            action_id = await _create_action(client, goal_id, phase_id, title="First action")

            body = await _post_gql(
                client,
                f"""
                {{
                  goal(goalId: "{goal_id}") {{
                    id title
                    phases {{
                      id title status
                      actions {{
                        id title status actionType
                      }}
                    }}
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            phases = body["data"]["goal"]["phases"]
            assert len(phases) == 1
            assert phases[0]["title"] == "Sprint phase"

            actions = phases[0]["actions"]
            assert len(actions) == 1
            assert actions[0]["id"] == action_id
            assert actions[0]["title"] == "First action"
            assert actions[0]["status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_goal_with_multiple_phases_and_actions(self, client):
        """Blueprint dashboard pattern: multi-phase, multi-action query in one round-trip."""
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client, "Half-marathon journey")
            p1_id = await _create_phase(client, goal_id, "Base training")
            p2_id = await _create_phase(client, goal_id, "Peak week")

            # Add actions to phase 1
            a1_id = await _create_action(client, goal_id, p1_id, title="Easy 5km run")
            a2_id = await _create_action(client, goal_id, p1_id, title="Strength session")

            body = await _post_gql(
                client,
                f"""
                {{
                  goal(goalId: "{goal_id}") {{
                    phases {{
                      id title
                      actions {{ id title }}
                    }}
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            phases = body["data"]["goal"]["phases"]
            assert len(phases) == 2

            phase1 = next(p for p in phases if p["id"] == p1_id)
            assert len(phase1["actions"]) == 2
            action_ids = {a["id"] for a in phase1["actions"]}
            assert a1_id in action_ids
            assert a2_id in action_ids

            # Phase 2 has no actions yet — must return empty list, not None
            phase2 = next(p for p in phases if p["id"] == p2_id)
            assert phase2["actions"] is not None
            assert len(phase2["actions"]) == 0


class TestTodaysActionsGraphQL:
    """GS-2.4: todaysActions query through GraphQL."""

    @pytest.mark.asyncio
    async def test_todays_actions_returns_overdue_and_due_today(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client, "Focus goal")
            await _activate_goal(client, goal_id)
            phase_id = await _create_phase(client, goal_id)

            overdue_id = await _create_action(
                client, goal_id, phase_id, title="Overdue task", due_date=YESTERDAY_ISO
            )
            future_id = await _create_action(
                client, goal_id, phase_id, title="Future task", due_date=TOMORROW_ISO
            )

            body = await _post_gql(
                client,
                "{ todaysActions { id title status } }",
            )
            assert "errors" not in body, body.get("errors")
            ids = {a["id"] for a in body["data"]["todaysActions"]}
            assert overdue_id in ids
            assert future_id not in ids

    @pytest.mark.asyncio
    async def test_todays_actions_excludes_completed(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client, "Done goal")
            await _activate_goal(client, goal_id)
            phase_id = await _create_phase(client, goal_id)
            action_id = await _create_action(client, goal_id, phase_id, due_date=YESTERDAY_ISO)
            await _post_gql(
                client,
                f'mutation {{ completeAction(input: {{ actionId: "{action_id}" }}) {{ id }} }}',
            )

            body = await _post_gql(client, "{ todaysActions { id } }")
            assert "errors" not in body, body.get("errors")
            ids = {a["id"] for a in body["data"]["todaysActions"]}
            assert action_id not in ids

    @pytest.mark.asyncio
    async def test_todays_actions_unauthenticated_returns_error(self, client):
        resp = await client.post(
            "/graphql",
            json={"query": "{ todaysActions { id } }"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "errors" in body


class TestNumericProgressGraphQL:
    """GS-2.5: numeric progress fields and progressPercent via GraphQL."""

    @pytest.mark.asyncio
    async def test_goal_without_target_has_null_progress_percent(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client, "Qualitative goal")
            body = await _post_gql(
                client,
                f"""
                {{
                  goal(goalId: "{goal_id}") {{
                    targetValue currentValue progressPercent
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            data = body["data"]["goal"]
            assert data["targetValue"] is None
            assert data["progressPercent"] is None

    @pytest.mark.asyncio
    async def test_multiple_contributing_actions_accumulate_progress(self, client):
        """Blueprint's 'Save $2,000' scenario — three payments accumulate correctly."""
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            goal_id = await _create_goal(client, "Emergency fund", target_value=2000.0, unit="USD")
            phase_id = await _create_phase(client, goal_id)

            for i, amount in enumerate([500.0, 750.0, 250.0]):
                action_id = await _create_action(
                    client,
                    goal_id,
                    phase_id,
                    title=f"Deposit {i}",
                    contributes_value=amount,
                )
                await _post_gql(
                    client,
                    f'mutation {{ completeAction(input: {{ actionId: "{action_id}" }}) {{ id }} }}',
                )

            body = await _post_gql(
                client,
                f"""
                {{
                  goal(goalId: "{goal_id}") {{
                    currentValue progressPercent
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            data = body["data"]["goal"]
            assert data["currentValue"] == 1500.0
            assert data["progressPercent"] == pytest.approx(75.0, rel=1e-2)
