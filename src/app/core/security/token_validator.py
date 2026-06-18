"""
JWT validation for the Goals Service.

The Goals Service does NOT issue or sign tokens — it delegates all token
validation to the Auth Service via the internal /internal/validate-token
endpoint.  Responses are cached in Redis for 60 s per JTI.
"""

import json
from typing import Any, Dict, Optional, cast

import httpx
from loguru import logger

from app.config.redis import redis_client
from app.config.settings import settings
from app.core.exceptions import AuthServiceUnavailableError, InvalidTokenError

_VALIDATE_URL = f"{settings.AUTH_SERVICE_INTERNAL_URL}/internal/validate-token"
_HEADERS = {"X-Internal-Key": settings.INTERNAL_API_KEY}

# Cache TTL must not exceed access-token lifetime (15 min in auth service)
_CACHE_TTL_SECONDS = 60


async def validate_token(bearer_token: str) -> Dict[str, Any]:
    """
    Validate a Bearer token against the Auth Service.

    Returns the user context dict:
        {user_id, email, role, plan, plan_expires}

    Raises:
        InvalidTokenError        — token rejected by Auth Service
        AuthServiceUnavailableError — auth service unreachable
    """
    # ── Try Redis cache first (fail-open on Redis outage) ─────────
    cached = await _get_cached(bearer_token)
    if cached:
        return cached

    # ── Call Auth Service ─────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                _VALIDATE_URL,
                headers={**_HEADERS, "Authorization": f"Bearer {bearer_token}"},
            )
    except httpx.RequestError as exc:
        logger.error(f"Auth service unreachable: {exc}")
        raise AuthServiceUnavailableError()

    if resp.status_code == 401:
        raise InvalidTokenError()

    if resp.status_code != 200:
        logger.error(f"Auth service returned unexpected status {resp.status_code}")
        raise AuthServiceUnavailableError()

    data: Dict[str, Any] = resp.json()

    # ── Cache the result (best-effort) ────────────────────────────
    await _set_cached(bearer_token, data)

    return data


async def _cache_key(token: str) -> str:
    # Use last 32 chars of token as a short discriminator (avoids storing full token)
    return f"goals:token_cache:{token[-32:]}"


async def _get_cached(token: str) -> Optional[Dict[str, Any]]:
    try:
        raw = await redis_client.get(await _cache_key(token))
        if raw:
            return cast(Dict[str, Any], json.loads(raw))
    except Exception:
        pass
    return None


async def _set_cached(token: str, data: Dict[str, Any]) -> None:
    try:
        await redis_client.setex(await _cache_key(token), _CACHE_TTL_SECONDS, json.dumps(data))
    except Exception:
        pass
