from typing import List, Union

from pydantic import AnyHttpUrl, TypeAdapter, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────
    APP_NAME: str = "LifeOps Goals Service"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8002
    SERVICE_HOST: str = "0.0.0.0"  # nosec B104

    # ── MongoDB ───────────────────────────────────────────────────────
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "lifeops_goals"

    # ── Redis ─────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Internal Service Communication ────────────────────────────────
    # Used to authenticate requests to/from Auth Service and other services
    INTERNAL_API_KEY: str = "change-this-to-a-long-random-string"

    # Auth Service — used to validate incoming JWTs
    AUTH_SERVICE_INTERNAL_URL: str = "http://auth-service:8001"

    # AI Service — used to dispatch goal decomposition tasks
    AI_SERVICE_INTERNAL_URL: str = "http://ai-service:8007"

    # ── CORS ──────────────────────────────────────────────────────────
    CORS_ALLOWED_ORIGINS: Union[str, List[AnyHttpUrl]] = [
        TypeAdapter(AnyHttpUrl).validate_python("http://localhost:3000"),
        TypeAdapter(AnyHttpUrl).validate_python("http://localhost:3002"),
    ]

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # ── Goal Defaults ─────────────────────────────────────────────────
    # How many days back to look when computing momentum score
    MOMENTUM_WINDOW_DAYS: int = 14
    # Momentum score threshold below which a goal_momentum_low event fires
    MOMENTUM_LOW_THRESHOLD: float = 40.0
    # Max phases allowed per goal (blueprint cap: 6)
    MAX_PHASES_PER_GOAL: int = 6
    # Max actions the AI decomposer may create in one shot
    MAX_ACTIONS_PER_DECOMPOSITION: int = 200

    # ── Rate Limiting ─────────────────────────────────────────────────
    GLOBAL_RATE_LIMIT_PER_MINUTE: int = 300
    # Per-user rate limits (Redis sliding window, 1-hour window)
    CREATE_GOAL_RATE_LIMIT: int = 20
    DECOMPOSE_GOAL_RATE_LIMIT: int = 5  # AI calls are expensive
    COMPLETE_ACTION_RATE_LIMIT: int = 200

    # ── Background Jobs ───────────────────────────────────────────────
    # How often (in hours) the momentum recalculation job runs
    MOMENTUM_RECALC_INTERVAL_HOURS: int = 6
    # How often (in hours) recurring action generation runs
    RECURRING_ACTION_GEN_INTERVAL_HOURS: int = 12

    # ── Logging ───────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    JSON_LOGS: bool = False

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )


settings = Settings()
