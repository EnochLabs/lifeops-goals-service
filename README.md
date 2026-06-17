# LifeOps Goals Service

The **Goals Service** owns the complete goal lifecycle for the LifeOps platform — from creation and AI decomposition through phase progression, action tracking, and momentum scoring.

---

## Service Overview

| Detail | Value |
|---|---|
| Port | `8002` |
| Framework | FastAPI + Beanie (MongoDB ODM) |
| Database | MongoDB |
| Cache / Pub-Sub | Redis |
| Auth | Delegates to Auth Service via internal `/internal/validate-token` |
| Internal key header | `X-Internal-Key` |

---

## Quick Start

```bash
# 1. Clone and enter the repo
git clone https://github.com/EnochLabs/lifeops-goals-service.git
cd lifeops-goals-service

# 2. Create and activate a virtual environment
python3.11 -m venv lifeopsvenv
source lifeopsvenv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment file and fill in values
cp .env.example .env

# 5. Generate a secure internal API key
python scripts/generate_keys.py

# 6. Run the service
PYTHONPATH=src uvicorn app.main:app --reload --port 8002
```

Or with Docker Compose:
```bash
docker compose up --build
```

---

## Project Structure

```
lifeops-goals-service/
├── src/app/
│   ├── api/
│   │   ├── health.py              # /health, /health/live, /health/ready
│   │   ├── internal/              # service-to-service routes
│   │   └── v1/                    # public REST routes (added per feature)
│   ├── config/
│   │   ├── settings.py            # pydantic-settings config
│   │   ├── database.py            # Motor/MongoDB client
│   │   └── redis.py               # Redis async client
│   ├── constants/
│   │   ├── goals.py               # GoalStatus, ActionType, PhaseStatus ...
│   │   ├── plans.py               # PlanTier, MAX_GOALS_BY_PLAN ...
│   │   └── limits.py              # rate limits, structural caps
│   ├── core/
│   │   ├── dependencies/
│   │   │   ├── auth.py            # get_current_user, require_plan()
│   │   │   └── rate_limit.py      # per-user sliding-window rate limiter
│   │   ├── exceptions/            # full domain exception hierarchy
│   │   ├── logging.py             # loguru setup
│   │   └── security/
│   │       └── token_validator.py # calls Auth Service + Redis cache
│   ├── events/
│   │   ├── event_types.py         # all event name constants + channels
│   │   ├── publisher.py           # publish_event() helper
│   │   └── subscribers.py        # listens to auth + AI event channels
│   ├── middleware/
│   │   ├── security_headers.py
│   │   ├── logging_middleware.py
│   │   └── rate_limit_middleware.py
│   ├── models/                    # Beanie ODM documents
│   │   ├── goal.py
│   │   ├── phase.py
│   │   └── action.py
│   ├── repositories/              # all DB access (no ORM in services)
│   │   ├── goal_repository.py
│   │   └── action_repository.py
│   ├── services/                  # business logic (added per feature)
│   ├── schemas/                   # Pydantic request/response schemas
│   ├── workers/
│   │   ├── momentum_worker.py     # recalculates momentum scores (6h)
│   │   └── recurring_action_worker.py
│   ├── graphql/                   # Strawberry GraphQL (optional layer)
│   ├── main.py                    # FastAPI app factory
│   └── lifespan.py                # startup / shutdown lifecycle
├── tests/
│   ├── unit/
│   └── integration/
├── docker/
│   ├── entrypoint.sh
│   └── nginx.conf
├── scripts/
│   └── generate_keys.py
├── .github/workflows/
│   ├── ci.yml
│   ├── auto-pr.yml
│   ├── commit-check.yml
│   └── codeql.yml
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── pytest.ini
├── requirements.txt
├── .env.example
├── .flake8
├── .pre-commit-config.yaml
└── commitlint-config.js
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Commit Convention

Follows [Conventional Commits](https://www.conventionalcommits.org/).

```
feat(goals): add goal activation endpoint
fix(momentum): handle zero-action window correctly
chore(deps): upgrade beanie to 1.29.0
```

Valid scopes: `goals`, `phases`, `actions`, `momentum`, `workers`, `events`, `auth`, `middleware`, `config`, `models`, `schemas`, `repos`, `services`, `graphql`, `ci`, `deps`, `docker`

---

## Inter-Service Communication

| Direction | Protocol | Purpose |
|---|---|---|
| Goals <- Auth | HTTP (internal) | Token validation |
| Goals -> AI | HTTP (internal) | Request decomposition |
| Goals -> All | Redis Pub/Sub | Domain events |
| Goals <- Auth | Redis Pub/Sub | user.deleted, plan changes |
| Goals <- AI | Redis Pub/Sub | decomposition results |
