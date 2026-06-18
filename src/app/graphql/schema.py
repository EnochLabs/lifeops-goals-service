"""
Strawberry schema for the Goals Service.

Plain `strawberry.Schema` — federation conversion is Sprint 6.
Auth is handled per-query/mutation via `info.context["user"]`
rather than a blanket middleware, so unauthenticated queries
(future `goalTemplates`) can be added without fighting the schema.
"""

from datetime import datetime

import strawberry

from app.graphql.mutations import Mutation
from app.graphql.queries import Query
from app.graphql.scalars import DateTime

schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    scalar_overrides={datetime: DateTime},
)
