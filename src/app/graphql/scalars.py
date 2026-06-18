"""DateTime scalar — mirrors the auth-service scalar for platform consistency."""

from datetime import datetime

import strawberry


def _serialize_datetime(value: datetime) -> str:
    return value.isoformat()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


DateTime = strawberry.scalar(
    datetime,
    name="DateTime",
    description="ISO-8601 datetime string",
    serialize=_serialize_datetime,
    parse_value=_parse_datetime,
)
