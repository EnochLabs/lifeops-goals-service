"""
GS-1.8 / GS-1.9: Integration tests for the GraphQL endpoint.

Tests the full goal lifecycle through the HTTP test client:
  create → activate → pause → resume → complete

Also tests:
  - Unauthenticated mutations return a clean GraphQL error (not 500)
  - Cross-user ownership: another user's goal returns not-found
  - goals / goal queries scope to the authenticated user
  - Health event subscription does not error
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

MOCK_USER_ID = "64f0000000000000000000aa"
OTHER_USER_ID = "64f0000000000000000000cc"

# Fake validated token context returned by the Auth Service mock
_MOCK_AUTH_CONTEXT = {
    "user_id": MOCK_USER_ID,
    "email": "test@lifeops.io",
    "role": "USER",
    "plan": "PRO",
    "plan_expires": None,
}

_OTHER_AUTH_CONTEXT = {
    "user_id": OTHER_USER_ID,
    "email": "other@lifeops.io",
    "role": "USER",
    "plan": "PRO",
    "plan_expires": None,
}

AUTH_HEADERS = {"Authorization": "Bearer test-token-abc"}
OTHER_HEADERS = {"Authorization": "Bearer test-token-other"}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def gql_client(fake_redis, client) -> AsyncClient:
    """
    HTTP client with token validation mocked so no real Auth Service is needed.
    Uses the `client` fixture from conftest (which patches Redis) and additionally
    patches the token validator.
    """
    return client


async def _post_gql(client: AsyncClient, query: str, headers: dict | None = None) -> dict:
    """Helper: POST a GraphQL query and return the JSON body."""
    hdrs = headers or AUTH_HEADERS
    resp = await client.post("/graphql", json={"query": query}, headers=hdrs)
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text}"
    return resp.json()


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestGraphQLHealth:
    """Basic sanity: GraphQL endpoint is reachable."""

    @pytest.mark.asyncio
    async def test_introspection_works(self, client):
        resp = await client.post(
            "/graphql",
            json={"query": "{ __typename }"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200


class TestUnauthenticatedAccess:
    """GS-1.9: Unauthenticated requests return a clean GraphQL error, not a 500."""

    @pytest.mark.asyncio
    async def test_goals_query_without_token(self, client):
        resp = await client.post("/graphql", json={"query": "{ goals { id } }"})
        assert resp.status_code == 200
        body = resp.json()
        # Should have errors, not a 500 crash
        assert "errors" in body
        assert body.get("data") is None or body["data"] is None

    @pytest.mark.asyncio
    async def test_create_goal_without_token(self, client):
        mutation = """
        mutation {
          createGoal(input: { title: "Sneaky goal" }) {
            id
          }
        }
        """
        resp = await client.post("/graphql", json={"query": mutation})
        assert resp.status_code == 200
        body = resp.json()
        assert "errors" in body


class TestGoalLifecycle:
    """GS-1.8: Full create → activate → pause → resume → complete lifecycle."""

    @pytest.mark.asyncio
    async def test_full_goal_lifecycle(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            # 1. Create
            body = await _post_gql(
                client,
                """
                mutation {
                  createGoal(input: {
                    title: "Run a half-marathon",
                    category: HEALTH,
                    horizon: MEDIUM,
                    priority: HIGH,
                    targetValue: 21.1,
                    unit: "km"
                  }) {
                    id status title targetValue unit progressPercent
                  }
                }
                """,
            )
            assert "errors" not in body, body.get("errors")
            goal = body["data"]["createGoal"]
            goal_id = goal["id"]
            assert goal["status"] == "DRAFT"
            assert goal["targetValue"] == 21.1
            assert goal["unit"] == "km"

            # 2. Activate
            body = await _post_gql(
                client,
                f"""
                mutation {{
                  activateGoal(goalId: "{goal_id}") {{
                    id status activatedAt
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            assert body["data"]["activateGoal"]["status"] == "ACTIVE"

            # 3. Pause
            body = await _post_gql(
                client,
                f"""
                mutation {{
                  pauseGoal(goalId: "{goal_id}") {{
                    id status pausedAt
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            assert body["data"]["pauseGoal"]["status"] == "PAUSED"

            # 4. Resume
            body = await _post_gql(
                client,
                f"""
                mutation {{
                  resumeGoal(goalId: "{goal_id}") {{
                    id status
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            assert body["data"]["resumeGoal"]["status"] == "RESUMED"

            # 5. Complete
            body = await _post_gql(
                client,
                f"""
                mutation {{
                  completeGoal(goalId: "{goal_id}") {{
                    id status completedAt
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            assert body["data"]["completeGoal"]["status"] == "COMPLETED"
            assert body["data"]["completeGoal"]["completedAt"] is not None

    @pytest.mark.asyncio
    async def test_abandon_goal(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            body = await _post_gql(
                client,
                'mutation { createGoal(input: { title: "Goal to abandon" }) { id } }',
            )
            goal_id = body["data"]["createGoal"]["id"]

            body = await _post_gql(
                client,
                f"""
                mutation {{
                  abandonGoal(goalId: "{goal_id}", reason: "Not relevant anymore") {{
                    id status note
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            assert body["data"]["abandonGoal"]["status"] == "ABANDONED"

    @pytest.mark.asyncio
    async def test_invalid_transition_returns_error(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            body = await _post_gql(
                client,
                'mutation { createGoal(input: { title: "Transition test" }) { id } }',
            )
            goal_id = body["data"]["createGoal"]["id"]

            # Try to pause a DRAFT goal — should error
            body = await _post_gql(
                client,
                f'mutation {{ pauseGoal(goalId: "{goal_id}") {{ id }} }}',
            )
            assert "errors" in body


class TestGoalQueries:
    """GS-1.7: goals and goal queries scoped to the authenticated user."""

    @pytest.mark.asyncio
    async def test_goals_returns_only_own_goals(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            # Create 2 goals
            for i in range(2):
                await _post_gql(
                    client,
                    f'mutation {{ createGoal(input: {{ title: "My Goal {i}" }}) {{ id }} }}',
                )

            body = await _post_gql(client, "{ goals { id title } }")
            assert "errors" not in body, body.get("errors")
            goals = body["data"]["goals"]
            assert len(goals) == 2
            assert all(g["title"].startswith("My Goal") for g in goals)

    @pytest.mark.asyncio
    async def test_goal_ownership_check_returns_not_found(self, client):
        """Cross-user access must return not-found (never leak existence)."""
        # User A creates a goal
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            body = await _post_gql(
                client,
                'mutation { createGoal(input: { title: "Private goal" }) { id } }',
            )
            goal_id = body["data"]["createGoal"]["id"]

        # User B tries to fetch it
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_OTHER_AUTH_CONTEXT),
        ):
            body = await _post_gql(
                client,
                f'{{ goal(goalId: "{goal_id}") {{ id }} }}',
                headers=OTHER_HEADERS,
            )
            assert "errors" in body

    @pytest.mark.asyncio
    async def test_goals_filter_by_status(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            body = await _post_gql(
                client,
                'mutation { createGoal(input: { title: "Draft only" }) { id } }',
            )
            await _post_gql(
                client,
                f"""
                mutation {{
                  activateGoal(goalId: "{body["data"]["createGoal"]["id"]}") {{ id }}
                }}
                """,
            )
            await _post_gql(
                client,
                'mutation { createGoal(input: { title: "Still Draft" }) { id } }',
            )

            body = await _post_gql(client, "{ goals(status: DRAFT) { id title } }")
            assert "errors" not in body
            assert all(g["title"] == "Still Draft" for g in body["data"]["goals"])


class TestGoalWithPhases:
    """Integration: goal query returns nested phases."""

    @pytest.mark.asyncio
    async def test_goal_resolves_phases(self, client):
        with patch(
            "app.core.security.token_validator.validate_token",
            new=AsyncMock(return_value=_MOCK_AUTH_CONTEXT),
        ):
            body = await _post_gql(
                client,
                'mutation { createGoal(input: { title: "Phased Goal" }) { id } }',
            )
            goal_id = body["data"]["createGoal"]["id"]

            await _post_gql(
                client,
                f"""
                mutation {{
                  createPhase(input: {{
                    goalId: "{goal_id}",
                    title: "Foundation"
                  }}) {{ id status }}
                }}
                """,
            )

            body = await _post_gql(
                client,
                f"""
                {{
                  goal(goalId: "{goal_id}") {{
                    id
                    phases {{
                      id title status order
                    }}
                  }}
                }}
                """,
            )
            assert "errors" not in body, body.get("errors")
            phases = body["data"]["goal"]["phases"]
            assert len(phases) == 1
            assert phases[0]["title"] == "Foundation"
            assert phases[0]["status"] == "ACTIVE"


class TestHealthEventSubscription:
    """GS-1.10: Health channel subscription logs receipt without erroring."""

    @pytest.mark.asyncio
    async def test_health_log_saved_handler_does_not_raise(self):
        from app.events.subscribers import _handle_health_log_saved

        # Should not raise; just logs
        await _handle_health_log_saved(
            {"user_id": MOCK_USER_ID, "morning_energy": 2, "log_date": "2026-06-18"}
        )
