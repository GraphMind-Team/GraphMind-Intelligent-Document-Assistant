"""Postgres tenancy-scoping helper (AD-2).

Any Postgres-backed feature repository (documents/chat/kg, from Epic 2
onward) that reads per-user data must build its statement through
`user_scoped_select` rather than hand-writing
`select(Model).where(Model.user_id == ...)` in its own `repository.py` --
this is the one place that filter is applied, so a call site can't ship
without it by omission. Mirrors the Weaviate/Neo4j tenancy rule documented
in `shapes.py`; `test_tenancy.py` covers the JWT-derived `user_id` this
helper is meant to be called with.
"""

import uuid
from typing import Any, Protocol, TypeVar

from sqlalchemy import Select, select


class _HasUserId(Protocol):
    user_id: Any


ModelT = TypeVar("ModelT", bound=_HasUserId)


def user_scoped_select(model: type[ModelT], user_id: uuid.UUID) -> Select[tuple[ModelT]]:
    """`select(model)` pre-filtered to rows owned by `user_id`.

    `model` must declare a `user_id` column -- every per-user Postgres
    table Epic 2/3 add is expected to. `user_id` should come from
    `get_current_user` (backend/app/auth/dependencies.py), never from
    client-supplied input.
    """
    return select(model).where(model.user_id == user_id)
