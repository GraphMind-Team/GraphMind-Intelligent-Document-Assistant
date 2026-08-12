"""Shared data-access layer.

Per architecture decision AD-2, this package is the sole path to Weaviate,
Neo4j, and Postgres. Every module's `repository.py` must go through code
here rather than opening its own client/connection, so per-user tenancy
filtering is enforced structurally instead of by convention.

`session.py` (Story 1.3) adds the Postgres engine/session factory.
`tenancy.py` adds the `user_scoped_select` helper every per-user Postgres
query must go through. Future stories add Weaviate/Neo4j clients here too.
"""

from app.shared.data_access.session import get_db_session
from app.shared.data_access.tenancy import user_scoped_select

__all__ = ["get_db_session", "user_scoped_select"]
