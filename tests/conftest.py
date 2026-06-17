"""
Shared pytest fixtures for the Goals Service test suite.

Uses:
  - mongomock-motor  → in-memory MongoDB (no real connection needed)
  - fakeredis        → in-memory Redis
  - httpx.AsyncClient → async test client for FastAPI
"""

import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import beanie
import fakeredis.aioredis
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.models.action import Action
from app.models.goal import Goal
from app.models.phase import Phase


# ── Fake Redis ────────────────────────────────────────────────
@pytest.fixture(scope="session")
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


# ── In-memory MongoDB via Beanie ──────────────────────────────
@pytest_asyncio.fixture(autouse=True)
async def init_test_db():
    client = AsyncMongoMockClient()
    await beanie.init_beanie(
        database=client["test_lifeops_goals"],
        document_models=[Goal, Phase, Action],
    )
    yield
    # Collections reset between tests automatically by mongomock


# ── FastAPI test client ───────────────────────────────────────
@pytest_asyncio.fixture
async def client(fake_redis) -> AsyncGenerator[AsyncClient, None]:
    from app.main import app

    with (
        patch("app.config.redis.redis_client", fake_redis),
        patch("app.core.security.token_validator.redis_client", fake_redis),
        patch("app.middleware.rate_limit_middleware.redis_client", fake_redis),
        patch("app.core.dependencies.rate_limit.redis_client", fake_redis),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            yield c


# ── Helpers ───────────────────────────────────────────────────
@pytest.fixture
def mock_current_user():
    """Returns a mock validated user context (as returned by Auth Service)."""
    return {
        "user_id": "64f0000000000000000000aa",
        "email": "test@lifeops.io",
        "role": "USER",
        "plan": "PRO",
        "plan_expires": None,
    }


@pytest.fixture
def auth_headers(mock_current_user):
    """Bearer token header — token validation is mocked in test_client."""
    return {"Authorization": "Bearer test-token-lifeops"}
