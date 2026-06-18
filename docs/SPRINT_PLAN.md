# LifeOps Goals Service — Sprint Plan

**Status:** Draft for review
**Version:** 1.0
**Date:** 2026-06-17
**Scope:** Backend only — `lifeops-goals-service` (port 8002, MongoDB `lifeops_goals`). MFE-Goals, the AI Service internals, and the Notification Service are out of scope except where this service must hand them a stable contract.
**Inputs used to build this plan:** a full line-by-line audit of this repository's current code, `docs/LifeOps_Blueprint.docx` (platform-wide v3.0 blueprint), `docs/LifeOps_AuthService_Blueprint.docx` and `docs/LifeOps_ProxyService_Blueprint_v1.docx` for cross-service context, the already-implemented `lifeops-auth-service` repo as the platform's reference implementation pattern, and external research on goal-decomposition systems, habit-formation science, and ethical engagement design (sources listed in Section 11).

---

## 0. How to Read This Document

This is not a from-scratch plan — a meaningful amount of scaffolding already exists in this repo (models, auth delegation, event taxonomy, workers, CI, test harness). Section 1 inventories exactly what's already done so nothing gets re-planned by accident. Section 2 surfaces a handful of decisions that need to be made *before* Sprint 1 starts, because they change what gets built. Section 3 is the philosophy behind how this service should drive engagement — written because of the "make it addictive" brief, and worth reading once. Sections 4 onward are the actual plan: working agreements, epics, six two-week sprints, cross-service dependencies, success metrics, and a risk register.

---

## 1. Current State Audit

A full read of `src/app/` shows the service is further along in some places than the v3.0 blueprint describes, and further behind in others. Treat this table as ground truth over both the blueprint and the README's structure diagram, which is aspirational in places.

| Layer | Status | Notes |
|---|---|---|
| **Domain models** (`models/goal.py`, `phase.py`, `action.py`) | Built, richer than blueprint | `Goal` carries `category` (8 life-domain values + `CUSTOM`), `horizon`, `priority`, `decomposition_state` — none of which exist in the v3.0 blueprint's `Goal` type. `Action` carries six `action_type` values (`TASK`, `HABIT`, `MILESTONE`, `REFLECTION`, `LEARNING`, `CHALLENGE`) where the blueprint only has a goal-level `OUTCOME/PROCESS/LEARNING` split. This is a genuine improvement — see §2.2. |
| **Constants & limits** (`constants/`) | Complete | Plan tiers (`FREE/BASIC/PRO/MAX`), per-plan goal caps, per-plan AI-decomposition quotas, structural caps (6 phases/goal, 50 actions/phase), and rate limits are all already defined as the single source of truth. The sprints below consume these, not redefine them. |
| **Repositories** (`repositories/`) | Partially built | `GoalRepository` has 4 of the methods it needs. `ActionRepository` has 4 of 5 — `create_next_recurrence` is a stub that returns `None`. **There is no `PhaseRepository` file at all.** |
| **Auth delegation** (`core/security/token_validator.py`, `core/dependencies/auth.py`) | Complete and solid | Calls the Auth Service's `/internal/validate-token`, Redis-caches the result for 60s, exposes `get_current_user`, `require_plan(tier)`, and `get_internal_caller`. Nothing to build here. |
| **Internal API** (`api/internal/check_access.py`) | Complete | Used by other services to check goal ownership. |
| **Rate limiting** | Complete | Global IP-level (middleware) and per-user per-action (dependency factory) both exist and are wired into `main.py`. |
| **Security headers, request logging** | Complete | Mirrors the auth-service implementation. |
| **Events** (`events/`) | Skeleton, partially wired | The full event taxonomy is defined (`event_types.py`). The publisher is complete. The subscriber listens to the Auth channel and the AI channel, but two of its three handlers are placeholder comments (`_handle_plan_change`, `_handle_ai_decomposition_result`). **It does not yet subscribe to the Health Service's channel**, which the blueprint requires for energy-based auto-rescheduling. |
| **Background workers** (`workers/`) | Skeleton, partially functional | `momentum_worker.py` is fully implemented end-to-end and will work as soon as `Action` data exists. `recurring_action_worker.py` runs on schedule but does nothing useful, because `ActionRepository.create_next_recurrence` is unimplemented. |
| **Business logic / services layer** (`services/`) | **Empty** | Only `__init__.py`. This is the largest gap — almost nothing in the system can actually happen yet (no way to create a goal, complete an action, or decompose anything). |
| **Request/response schemas** (`schemas/`) | **Empty** | No Pydantic DTOs exist yet. |
| **GraphQL layer** (`graphql/`) | **Empty** | No `schema.py`, `types.py`, `queries.py`, `mutations.py`, `enums.py`, or `inputs.py`. Compare to `lifeops-auth-service`, which has all six files fully built — that repo is the reference pattern for this work (see §2.1). |
| **AI decomposition trigger** | Not started | `AI_SERVICE_INTERNAL_URL` is already defined in `settings.py`, mirroring the Auth Service's URL setting, but no client code calls it yet. |
| **Tests** | Harness ready, coverage thin | `conftest.py` already gives every future test a working in-memory Mongo (`mongomock-motor`), fake Redis, an async test client, and a mock authenticated user. Only `test_exceptions.py`, `test_settings.py`, and one health-check integration test currently exist. |
| **CI/CD** | Complete | `ci.yml` runs Black, isort, Flake8, mypy, Bandit, pytest with coverage, then a Docker build + smoke test. This is the gate every sprint below has to pass through. |

**Bottom line:** the foundation (auth, infra, events skeleton, models, CI, test harness) is genuinely solid and doesn't need re-work. But the part that makes the service *do* anything — services, schemas, and the entire GraphQL surface — hasn't been started. That's most of what this plan covers.

---

## 2. Decisions Needed Before Sprint 1

### 2.1 REST vs. GraphQL — resolved by evidence, needs your sign-off

This repo's README structure diagram lists `api/v1/` as "public REST routes (added per feature)" and calls `graphql/` an "optional layer." That reads as if REST is the primary surface. But `lifeops-auth-service` — the most mature, most complete service in the platform, and the one other services already call — has zero REST routes beyond `/internal/*` and `/health`. Its entire public surface is a Strawberry GraphQL schema at `/graphql`, plus a `/.well-known/jwks.json` endpoint for the future Apollo Router. The platform blueprint's gateway is also explicitly an Apollo Router federating GraphQL subgraphs, not a REST aggregator.

**This plan proceeds on the assumption that GraphQL is the real public surface for the Goals Service, matching the Auth Service, and that the `api/v1/` folder in the README is leftover template boilerplate.** If that's wrong — if there's a reason this service specifically needs REST — flag it before Sprint 1, because it changes the shape of almost every sprint below.

### 2.2 Keep the Action-level typing, don't reintroduce Goal-level OUTCOME/PROCESS/LEARNING

The blueprint types a whole *Goal* as `OUTCOME`, `PROCESS`, or `LEARNING`. The actual code instead types individual *Actions* as `TASK`, `HABIT`, `MILESTONE`, `REFLECTION`, `LEARNING`, or `CHALLENGE`, and lets a single goal mix them freely — a half-marathon goal can have recurring `HABIT` training runs, a one-off `MILESTONE` for race day, and a `TASK` for buying shoes, all under one goal. This is strictly more expressive than the blueprint's model and should be kept as-is. The sprints below build on the Action-level typing, not the blueprint's Goal-level typing.

### 2.3 Numeric progress tracking is currently missing — needs a decision

This is the one real regression found in the audit. The blueprint's worked examples depend on a goal having a quantifiable target — "Save $2,000," a progress bar at "40.3%," "$0 remaining in this envelope." The current `Goal` model has no `target_value`, `current_value`, or `unit` field at all. As built today, the *only* progress signal for any goal is `momentum_score`, which measures action-completion rate over a rolling 14-day window — useful for habit consistency, useless for "how much of my $2,000 have I saved."

**Recommendation:** add `target_value`, `current_value`, and `unit` back to `Goal` as fully optional fields (not tied to a goal "type," since that axis no longer exists per §2.2) — a user toggles "does this goal have a measurable target?" during creation, independent of category or horizon. Pair this with an optional `contributes_value: float` field on `Action`, so completing "Run 5km" can auto-increment the parent goal's `current_value` by 5. This is scoped into Sprint 2 below. If you'd rather goals stay purely momentum-driven and never show a dollar or kilometer figure, say so now — it removes a chunk of Sprint 2 and changes what the Goal Detail screen in the MFE can show.

### 2.4 Service-layer code style: mirror the Auth Service, not this repo's repository style

`GoalRepository`/`ActionRepository` in this repo use static-method classes. `lifeops-auth-service`'s `services/` layer uses plain module-level functions (`login_user()`, `register_user()`, `change_password()`) imported directly into `graphql/mutations.py`. This plan keeps the existing repository class style untouched, but builds the new `services/` layer as plain functions per service module (`services/goal_service.py` exposing `create_goal()`, `activate_goal()`, etc.) to match the Auth Service convention, since GraphQL resolvers will be calling into both repos eventually and consistency there matters more than consistency with this repo's own repository layer.

### 2.5 Naming collision to design around

`app.constants.goals.ActionType` already exists (the `TASK/HABIT/MILESTONE/...` enum). The GraphQL *object type* representing an `Action` entity can't also be called `ActionType` without a Python import collision. Mirroring the Auth Service's own precedent (`SubscriptionGQLType` alongside the `Subscription` model), this plan names the GraphQL entity types `GoalGQLType`, `PhaseGQLType`, and `ActionGQLType`, while the Strawberry enums keep the exact names of their constants counterparts (`GoalStatus`, `ActionType`, `ActionStatus`, `RecurrencePattern`, `GoalCategory`, `GoalHorizon`, `Priority`, `DecompositionState`, `PhaseStatus`).

### 2.6 AI Service contract — assumed, not verified

`lifeops-ai-service` wasn't cloned or reviewed for this plan. Sprint 4 below assumes the AI Service exposes an internal endpoint such as `POST /internal/decompose` that accepts a goal payload and either returns synchronously or, more likely given the event taxonomy already defined here, replies asynchronously by publishing `ai.decomposition_result` on its own channel for this service to consume. If the actual AI Service contract differs, Sprint 4's estimates and acceptance criteria will need a quick revision once that repo is reviewed — flagged here so it isn't a silent assumption.

---

## 3. Engagement Philosophy: Irresistibly Useful, Not Manufactured-Addictive

You said you want this platform to leave people speechless and make them feel like they can't put it down. That's the right ambition, and it's worth being precise about how to get there, because the cheap version of "addictive" and the durable version of "indispensable" are built with almost opposite techniques — and your own blueprint has already chosen the durable version. The Notification Service section explicitly bans streak-shame notifications and caps push volume at three a day; the momentum scoring already fires a *compassionate* re-engagement event rather than a guilt one. The sprints below just need to carry that same discipline into the Goals Service's own logic, not water it down with whatever gets the highest short-term engagement number.

A few things from the research worth keeping in mind while building this:

**Streak design is the single biggest place habit apps get this wrong.** Hard, all-or-nothing streaks reliably produce a "catastrophic failure mode" — the longer the streak, the more anxiety it produces, and when it inevitably breaks (life happens), a large fraction of users never restart at all. Apps that instead use grace periods, quiet resets, and "options to pause without losing momentum" measure *higher* long-run engagement, not lower, because the metric stops being a source of dread. The current `momentum_score` design (a rolling 14-day completion ratio, not a brittle daily streak) already avoids the worst version of this — the sprints below should keep it that way rather than bolting a classic "don't break the chain" counter on top.

**BJ Fogg's own behavior model — the thing every habit app cites — comes with his explicit warning that the same mechanics produce both healthy tiny-habit formation and exploitative dark-pattern onboarding, and that the difference is whether the design assists a behavior the user would endorse on reflection or overrides their judgment in the moment.** Fear-based prompting (urgency, shame, loss-aversion notifications) gets a short-term spike and burns trust; hope-based prompting (visible progress, achievable next steps, identity reinforcement — "I am someone who shows up") is slower but is what survives past week three. Self-Determination Theory's three needs — autonomy, competence, relatedness — are a useful checklist for any new feature in this service: does it give the user a real choice (autonomy), does it make their progress legible and earned (competence), and — since this service alone can't supply relatedness, that's the Relationships Service's job — does it at least not actively undermine the other two in pursuit of a metric.

**The market data backs this up as a growth strategy, not just an ethics position.** Industry retention research from this year is blunt about it: the apps with the best 2026 retention numbers are not the ones optimized for compulsive return visits — they're the ones that remove friction, welcome users back after a lapse without penalty, and make the value so immediate that staying away feels like the loss, not staying in. That is a fair description of what "Today's Focus," a clean momentum sparkline, and a phase-completion celebration are supposed to do here. Build for that, and the speechless reaction comes from genuine usefulness compounding over weeks — which is also the only version of "addictive" that doesn't generate App Store reviews about anxiety and guilt twelve months from now.

Concretely, this shapes a few backlog items below: momentum recalculation should never produce a punitive "you broke your streak" event, only the existing low/recovered momentum signals; the recurring-action engine should generate the next instance regardless of whether the previous one was missed (no catch-up shame, no "missed 4 habits" badge); and the phase/goal completion celebration (Sprint 5) is designed to make the *user's own effort* visible and shareable, not to gate a reward behind a manufactured streak.

---

## 4. Working Agreements & Definition of Done

### 4.1 Cadence

Two-week sprints, six sprints, 12 weeks total. Each sprint targets roughly 7–8 effective focused days out of the 10 working days available, leaving room for context-switching against the other repos in the LifeOps ecosystem you're running in parallel — this is a solo-developer plan, not a team plan, and pretends otherwise would just produce a schedule that slips in week one. Effort is sized S (≈0.5 day) / M (≈1–2 days) / L (≈3–5 days) rather than story points — planning-poker-style point estimation assumes a team calibrating against each other's velocity, which doesn't apply here, and flow-based S/M/L sizing is also where the industry has been trending for small teams through 2025–2026.

### 4.2 Definition of Done (applies to every backlog item below, no exceptions)

A backlog item is done when: it passes `black`, `isort`, `flake8`, and `mypy` clean; `bandit -r src/ -ll` reports nothing new; there's at least one unit test for the service-layer logic and, for anything reachable via GraphQL, one integration test through the test client in `conftest.py`; the relevant domain event(s) are published with the correct payload shape; the GraphQL schema change is exercised manually once in GraiQL/GraphiQL; the conventional-commit message uses one of the scopes already listed in this repo's README; and `docker build` + the CI smoke test still pass. This is just the existing `ci.yml` pipeline restated as a checklist — nothing new is being asked of the code, just made explicit per item.

### 4.3 Ceremonies, adapted for one developer

No daily standup or planning poker. At the start of each sprint: re-read this sprint's backlog table, confirm nothing upstream changed (especially the AI Service contract assumption in §2.6), and write one sentence in the commit log or a `NOTES.md` stating the sprint goal. At the end: a short retro note (what shipped, what slipped, what was learned) appended to the bottom of this file under a "Sprint Log" section, so the plan stays a living document rather than a one-time artifact.

---

## 5. Epics

| ID | Epic | Sprints |
|---|---|---|
| E1 | Goal Lifecycle & Core Services | 1, 2 |
| E2 | Phases & Actions Execution Layer | 2 |
| E3 | GraphQL API Surface | 1 – 6 (cross-cutting, built incrementally) |
| E4 | Habit & Recurrence Engine | 3 |
| E5 | Momentum, Streaks & Compassionate Engagement | 3, 5 |
| E6 | AI Decomposition Integration | 4 |
| E7 | Plan Tiers, Quotas & Goal Templates | 4, 5 |
| E8 | Apollo Federation & Production Hardening | 6 |

---

## 6. Sprint 1 — Goal Lifecycle & GraphQL Bootstrap

**Sprint goal:** a user can authenticate, create a goal, move it through its full lifecycle (draft → active → paused/resumed → completed/abandoned), and query it back — entirely through a working GraphQL endpoint.

| ID | Item | Description | Acceptance Criteria | Effort |
|---|---|---|---|---|
| GS-1.1 | Build `PhaseRepository` | Currently missing entirely. Mirror the static-method pattern of `GoalRepository`: `get_by_id`, `list_for_goal`, `get_active_phase`, `create`, `update_status`. | All methods covered by unit tests against the in-memory Mongo fixture. | M |
| GS-1.2 | `services/goal_service.py` — lifecycle functions | `create_goal()` (enforces `MAX_GOALS_BY_PLAN`, checks for duplicate title per user, sets `status=DRAFT`), `activate_goal()`, `pause_goal()`, `resume_goal()`, `complete_goal()`, `abandon_goal()`. Each publishes its matching event from `GoalEvents` (`CREATED`, `ACTIVATED`, `PAUSED`, `RESUMED`, `COMPLETED`, `ABANDONED`). | Illegal transitions raise `InvalidGoalStateError` (e.g., can't activate an already-completed goal). Goal limit breach raises `GoalLimitExceededError` with the correct plan name. Every transition is unit-tested. | L |
| GS-1.3 | Pydantic DTOs in `schemas/goal.py` | Internal validation schemas used by the service layer (`GoalCreateData`, `GoalUpdateData`) — kept separate from Strawberry input types so service-layer validation doesn't depend on the GraphQL library. | Title length, description length, and category/horizon enum values are validated using the existing `constants/limits.py` values, not new magic numbers. | S |
| GS-1.4 | `graphql/enums.py` | Strawberry-wrap every constants class needed by Sprint 1: `GoalStatus`, `GoalCategory`, `GoalHorizon`, `Priority`, `DecompositionState`. | Each enum's values match its constants-module counterpart exactly (test asserts on this so the two can't silently drift). | S |
| GS-1.5 | `graphql/types.py` — `GoalGQLType` | Per the naming decision in §2.5. Includes the (not yet populated) `target_value`/`current_value`/`unit`/`progress_percent` fields stubbed as `Optional` ahead of Sprint 2 if §2.3 is approved. | Renders correctly in GraphiQL introspection. | S |
| GS-1.6 | `graphql/inputs.py` — `CreateGoalInput`, `UpdateGoalInput` | Strawberry input types wrapping the Pydantic DTOs from GS-1.3. | Invalid input produces a GraphQL error with the same message as the underlying `ValidationError`. | S |
| GS-1.7 | `graphql/queries.py` — `goals`, `goal` | `goals(status: Optional[GoalStatus])` scoped to the authenticated user; `goal(id: ID!)` with an ownership check (404 via `GoalNotFoundError` if not owned, not a 403 — don't leak existence). Include the `_goal_to_type()` converter helper for reuse by mutations. | Returns only the calling user's goals; cross-user access attempt is covered by a test. | M |
| GS-1.8 | `graphql/mutations.py` — `createGoal`, `updateGoal`, `pauseGoal`, `resumeGoal`, `completeGoal`, `abandonGoal` | Thin resolvers calling into `goal_service`. | Full lifecycle exercised end-to-end in one integration test (create → activate → pause → resume → complete). | M |
| GS-1.9 | `graphql/schema.py` + wire into `main.py` | Plain `strawberry.Schema` (federation comes in Sprint 6, see §2.6/Sprint 6). Auth handled via a `get_context()` function that reads the `Authorization` header directly and calls the existing `validate_token()` — **not** a new global `AuthMiddleware`, since some future queries (e.g., `goalTemplates`, Sprint 5) should be servable without auth, and a blanket middleware fights that. | `/graphql` reachable in `DEBUG`, GraphiQL loads, an unauthenticated mutation attempt returns a clean GraphQL error rather than a 500. | M |
| GS-1.10 | Subscribe to the Health Service event channel | `events/subscribers.py` currently only listens to the Auth and AI channels. Add `lifeops:events:health` to `_CHANNELS` with a no-op handler for now — the actual auto-reschedule logic depends on Actions existing, so it's implemented in Sprint 3, but the subscription itself belongs here so nothing is missed later. | Subscriber logs receipt of a test `health_log_saved` event without erroring. | S |

**Definition of Done for this sprint, beyond §4.2:** every mutation above is runnable by hand from GraphiQL against a local Docker Compose stack, in the exact sequence a new user would hit them.

---

## 7. Sprint 2 — Phases, Actions & Measurable Progress

**Sprint goal:** a goal can be broken into ordered phases that unlock sequentially, each phase can hold actions, actions can be completed/skipped/rescheduled, and — pending the §2.3 decision — a goal can carry a real numeric target.

| ID | Item | Description | Acceptance Criteria | Effort |
|---|---|---|---|---|
| GS-2.1 | `services/phase_service.py` | `create_phase()` (enforces `MAX_PHASES_PER_GOAL`), `complete_phase()` (auto-unlocks the next `LOCKED` phase to `ACTIVE` — sequential unlock per the model's own docstring), `skip_phase()`. Publishes `PhaseEvents.UNLOCKED/COMPLETED/SKIPPED`. | Completing the last phase of a goal does *not* error when there's no next phase to unlock; it's a no-op plus the completion event. Covered by unit tests including the boundary case. | M |
| GS-2.2 | `services/action_service.py` | `create_action()` (enforces `MAX_ACTIONS_PER_PHASE`), `complete_action()`, `skip_action()` (reason stored in `completion_note`), `reschedule_action()` (updates `due_date`). Publishes `ActionEvents.CREATED/COMPLETED/SKIPPED`. | Completing a `MILESTONE`-type action that is the last incomplete action in its phase auto-triggers `phase_service.complete_phase()`. Tested explicitly. | L |
| GS-2.3 | Reorder mutation | `REORDER_PHASES_RATE_LIMIT` already exists in `constants/limits.py` with nothing consuming it — implement `reorderPhases(goalId, orderedPhaseIds)` so the Kanban-style UI described in the blueprint has something to call. | Reordering persists the new `order` field on each `Phase`; rate limit is enforced via the existing `rate_limit()` dependency factory. | M |
| GS-2.4 | `todaysActions` query | `todaysActions(userId logic via context, not param — see GS-1.9)` returns all `PENDING`/`IN_PROGRESS` actions due today or overdue, across all the user's active goals, sorted by goal priority then due date. | Matches the blueprint's dashboard worked example shape closely enough for the MFE team to consume without renegotiation. | M |
| GS-2.5 | Numeric progress fields *(pending §2.3 approval)* | Add `target_value: Optional[float]`, `current_value: Optional[float]`, `unit: Optional[str]` to `Goal`; add `contributes_value: Optional[float]` to `Action`. `complete_action()` from GS-2.2 increments the parent goal's `current_value` when `contributes_value` is set. Expose `progress_percent` as a computed GraphQL field (`current_value / target_value * 100`, null-safe). | A "Save $2,000" style goal can be created, have a contributing action completed, and show the correct `progress_percent` — tested as the canonical example. | M |
| GS-2.6 | GraphQL surface for Phase & Action | `PhaseGQLType`, `ActionGQLType` (per §2.5), corresponding queries/mutations/inputs, wired the same way as Sprint 1's Goal surface. | `Goal.phases` and `Phase.actions` resolve as nested fields in a single query, matching the blueprint's "single network round-trip" dashboard pattern. | L |

---

## 8. Sprint 3 — Habit Engine, Momentum & Cross-Domain Rescheduling

**Sprint goal:** recurring habits actually generate their next occurrence on schedule, momentum scores are visible and trustworthy, and a low-energy health log measurably reschedules the right actions — without ever shaming the user for missing one.

| ID | Item | Description | Acceptance Criteria | Effort |
|---|---|---|---|---|
| GS-3.1 | Implement `ActionRepository.create_next_recurrence` | The HABIT action stays a template (its `next_due` rolls forward, `recurrence.generation_count` increments); each generation creates a new, independently completable instance linked via `parent_action_id`. Worker-driven generation (already scheduled, not completion-triggered) is intentionally kept — it's more robust than the blueprint's "regenerate on completion" idea, since it doesn't depend on the user ever opening the app. | A `DAILY` habit and a `CUSTOM` (e.g., Mon/Wed/Fri) habit both generate exactly the right next date across a simulated week in a unit test, including across a month boundary. | L |
| GS-3.2 | Momentum exposure in GraphQL | Expose `momentumScore`, `lastMomentumCalc`, and a 30-day momentum history (new lightweight read model, doesn't need its own collection — derive from existing `Action.completed_at` timestamps) as queryable fields on `GoalGQLType`. | Sparkline-shaped data matches what the blueprint's Goal Detail view expects (a simple list of `{date, score}` points). | M |
| GS-3.3 | `goal.momentum_low` / `goal.momentum_recovered` payload enrichment | The momentum worker already fires these correctly; enrich the payload with the goal title and current streak-of-completions count so the Notification Service can write a specific, compassionate message rather than a generic one. | Payload includes `goal_title`, `momentum_score`, and `completion_streak` — no "you broke your streak" language anywhere in this service's code or events, per §3. | S |
| GS-3.4 | Health-event-driven auto-reschedule | Complete the no-op subscriber from GS-1.10: on `health_log_saved` with `morning_energy` in {1, 2}, find that user's high-effort (`estimated_minutes` above a configurable threshold) actions due today and reschedule them to the next day, publishing a reschedule event with reason `low_energy_day`. | Exactly matches the blueprint's worked example (Tue, energy=2 → "10km run" rescheduled). Covered by an integration test that publishes a synthetic `health_log_saved` event and asserts the reschedule happened. | M |
| GS-3.5 | Habit-grid query | A GitHub-contribution-graph-shaped data query for `PROCESS`/habit-style goals — `habitGrid(goalId, days)` returning per-day completion booleans. | Matches the blueprint's "habit grid" UI description; returns gaps as `false`, never as an error or a flagged "miss." | M |

---

## 9. Sprint 4 — AI Decomposition Integration

**Sprint goal:** a user can ask AI to plan a goal, the request reaches the AI Service, and the result comes back as real phases and actions — gated correctly by plan tier and monthly quota. (Estimates here carry the most uncertainty in the whole plan — see §2.6.)

| ID | Item | Description | Acceptance Criteria | Effort |
|---|---|---|---|---|
| GS-4.1 | `core/security/ai_client.py` | Outbound HTTP client to `AI_SERVICE_INTERNAL_URL`, structured exactly like the existing `token_validator.py` (timeout, `X-Internal-Key` header, clean failure → `AIServiceUnavailableError`). | Unreachable AI Service degrades gracefully — the goal's `decomposition_state` reverts to `NONE` rather than getting stuck in `PENDING` forever. | M |
| GS-4.2 | `decomposeGoal` mutation + `services/decomposition_service.py` | Gated by `require_plan` against `AI_DECOMPOSITION_PLANS` (raises `AIDecompositionLockedError` below `BASIC`) and by a monthly quota check (new Redis key `goals:ai_quota:{user_id}:{YYYY-MM}`, TTL ~35 days, checked against `AI_DECOMPOSITIONS_PER_MONTH[plan]`). Sets `decomposition_state=PENDING`, calls `ai_client`, publishes `GoalEvents.DECOMPOSITION_REQUESTED`. | Quota enforcement is plan-aware and tested for all four tiers, including `FREE` (quota of 0, immediate `AIDecompositionLockedError` before even checking Redis). | L |
| GS-4.3 | Complete `_handle_ai_decomposition_result` | Currently a stub comment. On receiving `ai.decomposition_result`, write the returned phases and actions via `PhaseRepository`/`ActionRepository`, set `decomposition_state=COMPLETED`, publish `GoalEvents.DECOMPOSITION_COMPLETED`. | A synthetic decomposition payload (shaped like the blueprint's half-marathon worked example) produces the correct phases/actions in the database, end-to-end tested without a real AI Service running. | L |
| GS-4.4 | Handle decomposition failure | On a malformed or failed AI response, set `decomposition_state=FAILED`, store `decomposition_error`, publish `GoalEvents.DECOMPOSITION_FAILED`. | User-facing error message is specific enough to act on ("AI couldn't generate a plan for this goal — try a more specific title") rather than generic. | S |

---

## 10. Sprint 5 — Goal Templates, Limits & Celebration

**Sprint goal:** new users have a fast path into their first goal via templates, every plan-tier limit from `constants/plans.py` is actually enforced somewhere, and completing a phase or goal produces a moment worth sharing — for the reasons in §3, not as a streak gate.

| ID | Item | Description | Acceptance Criteria | Effort |
|---|---|---|---|---|
| GS-5.1 | `goalTemplates` query | A small static seed set (8–12 templates spanning the existing `GoalCategory` values) stored as a simple config module, not a new collection — no admin tooling needed yet. Per §2.1's GraphQL-first decision, this can be the one query servable without auth, since it's effectively static marketing/onboarding content. | Each template includes a pre-filled title, category, horizon, and a starter set of phase/action suggestions matching the structure a real `decomposeGoal` call would produce. | M |
| GS-5.2 | Enforce `MAX_GOALS_BY_PLAN` everywhere it's reachable | GS-1.2 already enforces this at creation; confirm it's also re-checked correctly on any path that could resurrect an `ABANDONED` goal back to `ACTIVE`, and add a clear, upgrade-oriented error message (already half-built in `GoalLimitExceededError`). | A `FREE`-plan user at their 3-goal cap gets a specific, friendly upgrade prompt, tested explicitly — this is a monetization-critical path, worth getting right. | S |
| GS-5.3 | Phase/goal completion celebration payload | On `PhaseEvents.COMPLETED` and `GoalEvents.COMPLETED`, enrich the event with everything the MFE needs to render the blueprint's shareable card (goal title, completion date, phase count, total actions completed) — no personal journey data, per the blueprint's own privacy note on this feature. | Payload shape reviewed against the MFE's actual rendering needs (coordinate with the MFE-Goals work when it starts) before being treated as final. | S |
| GS-5.4 | Plan-downgrade enforcement | `_handle_plan_change` in `events/subscribers.py` is currently a stub for the downgrade direction. On downgrade, goals beyond the new plan's cap should move to `PAUSED` (not deleted) with a reason, not silently stay `ACTIVE` over the limit. | Downgrading a `PRO` user with 20 active goals to `FREE` results in exactly 3 staying `ACTIVE` and 17 moving to `PAUSED`, deterministically (oldest-activated-first), tested explicitly. | M |

---

## 11. Sprint 6 — Apollo Federation & Production Hardening

**Sprint goal:** the Goals Service is a real federated subgraph other services can resolve against, test coverage is high enough to trust, and the service is genuinely ready for the "two real users logging for two weeks" gate from the platform blueprint's Phase 1.

| ID | Item | Description | Acceptance Criteria | Effort |
|---|---|---|---|---|
| GS-6.1 | Convert to `strawberry.federation.Schema` | Add `@strawberry.federation.type(keys=["id"])` to `GoalGQLType` and a reference resolver, so the Money Service's `Envelope.linkedGoalId` and any future cross-service query can resolve a goal's `title`/`momentumScore` without a second round-trip. Verify whether the installed `strawberry-graphql==0.316.0` needs the `apollo-federation` extra added to `requirements.txt` for this — confirm against the package's current docs rather than assuming. | A federation entity-resolution query (`_entities`) against a `Goal` reference returns correctly in an integration test. Mirror this only on `Goal` for now — `Phase`/`Action` don't need to be federation entities since nothing outside this service references them directly. | M |
| GS-6.2 | Full test coverage pass | Backfill unit tests for every service-layer function across Sprints 1–5 that didn't get one inline, plus integration tests for every GraphQL query/mutation. Target meaningfully above the current near-zero domain coverage — track the number `pytest --cov` reports and don't let it regress sprint-to-sprint going forward. | `pytest --cov=app --cov-report=term-missing` run and reviewed line-by-line at least once; any glaring gap (e.g., an untested error branch in a money-relevant path like quota enforcement) gets a test before this sprint closes. | L |
| GS-6.3 | mypy / bandit / flake8 zero-new-warnings pass | Run the full lint suite locally exactly as `ci.yml` does, fix anything accumulated across five sprints of fast iteration. | CI green on a clean run, no `# noqa` or `# type: ignore` added without a one-line comment explaining why. | M |
| GS-6.4 | README and GraphQL schema docs | Update this repo's README to reflect what's actually built (replace the aspirational `api/v1/` structure note), and ensure every GraphQL field/type has a docstring-derived description visible in introspection. | A new contributor (or future you, in three months) can run `docker-compose up` and explore the entire API from GraphiQL's schema docs alone, no other document required. | S |
| GS-6.5 | Demo readiness check against the blueprint's own Phase 1 gate | Walk through the exact scenario the blueprint specifies — a real user creating a goal, completing actions daily for two weeks — end to end against a local Docker Compose stack with the real Auth Service running alongside (not just this service in isolation). | Momentum score reflects reality after the simulated two weeks; no manual database surgery required at any point in the walkthrough. | M |

---

## 12. Cross-Service Dependency Timeline

| When needed | Dependency | Status |
|---|---|---|
| Sprint 1 (immediately) | Auth Service `/internal/validate-token` | Already live and stable — no risk here. |
| Sprint 3 | Health Service publishes `health_log_saved` on `lifeops:events:health` | Assumed per blueprint's own event contract for that service; confirm the exact payload shape once Health Service work starts, since GS-3.4 reads `morning_energy` specifically by name. |
| Sprint 4 | AI Service `/internal/decompose` + `ai.decomposition_result` event | **Not verified — highest-risk dependency in this plan.** Revisit Sprint 4's scope once `lifeops-ai-service` is reviewed. |
| Sprint 5 | Notification Service consumes this service's enriched event payloads | This service only needs to publish correctly; no blocking dependency, but coordinate payload shape before considering GS-5.3 fully final. |
| Sprint 6 | Apollo Router federation | The platform-wide router isn't built yet (confirmed — even the more mature Auth Service hasn't wired federation directives yet, only a plain schema + JWKS endpoint). Sprint 6 makes this service federation-*ready*; actually composing the supergraph is a separate, later piece of work outside this plan's scope. |

---

## 13. Success Metrics

Borrowing the platform blueprint's own Phase 1 gate ("two real users logging for two weeks") as the bar, plus a few service-level numbers worth tracking from Sprint 1 onward: full goal-lifecycle completion rate without manual database intervention; momentum recalculation completing within its 6-hour worker interval at realistic data volume; recurring-action generation producing the mathematically correct next date 100% of the time across all five recurrence patterns (this is exactly the kind of bug that erodes trust silently if it's ever off by one day); GraphQL p95 latency on the `goals` query staying low even as a user's goal count approaches the `MAX`-tier cap of 200; and test coverage trending up, not flat, sprint over sprint.

---

## 14. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| AI Service contract assumption (§2.6) is wrong | Medium | High — reshapes Sprint 4 | Review `lifeops-ai-service` before Sprint 4 starts, not during it. |
| §2.3 (numeric progress fields) gets skipped or deferred indefinitely | Medium | Medium — Goal Detail UX silently degrades from the blueprint's vision | Get an explicit yes/no before Sprint 2, not a default. |
| Solo-developer context-switching across the other LifeOps repos causes sprint slip | High | Medium | Already priced into the 7–8 effective-day-per-sprint assumption in §4.1; if slip still happens, cut scope from Sprint 5 (templates can wait) before cutting from Sprints 1–3 (core lifecycle can't). |
| Momentum/streak logic drifts toward shame-based design under future "growth" pressure | Low now, rises over time | High — directly undermines the retention strategy in §3 and the blueprint's own anti-nag commitment | Treat §3 as a standing constraint on any future engagement feature, not a one-time Sprint 3 decision. |
| Federation directive support in installed `strawberry-graphql` version doesn't match what Sprint 6 assumes | Low | Low | Verify package docs at Sprint 6 start, per the explicit note in GS-6.1. |

---

## 15. Research & References

This plan's engagement philosophy (§3) and a few technical choices were informed by external research rather than just the blueprint. Key sources, paraphrased throughout rather than quoted: industry retention benchmarking for 2026 (UXCam, Appcues, and enable3.io's app retention reports) on day-1/day-7/day-30 retention patterns and what separates durable engagement from compulsive engagement; Yu-kai Chou's and others' 2025–2026 writing on the Fogg Behavior Model's dual use for both ethical habit formation and dark-pattern design, including Fogg's own published position on designing for outcomes users would endorse on reflection; Nielsen Norman Group's coverage of Self-Determination Theory (autonomy/competence/relatedness) applied to UX; Smashing Magazine's and other 2025–2026 writing specifically on streak-system UX psychology and the documented failure mode of shame-based streak design; and Apollo GraphQL's own documentation and the `strawberry-graphql` PyPI page for the Strawberry/FastAPI/Federation integration patterns referenced in §2.1 and Sprint 6.

---

## Sprint Log

*(Append a short retro note here at the end of each sprint — what shipped, what slipped, what was learned. Keeping this in the same file as the plan it's tracking against is deliberate.)*
