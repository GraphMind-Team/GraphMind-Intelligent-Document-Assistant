"""Shared data-access layer.

Per architecture decision AD-2, this package is the sole path to Weaviate,
Neo4j, and Postgres. Every module's `repository.py` must go through code
here rather than opening its own client/connection, so per-user tenancy
filtering is enforced structurally instead of by convention.

`session.py` (Story 1.3) adds the Postgres engine/session factory.
`tenancy.py` adds the `user_scoped_select` helper every per-user Postgres
query must go through. `weaviate_client.py` (Story 2.3) adds the Weaviate
connection and the flat-shape passage write path. Future stories add a
Neo4j client here too.
"""

from app.shared.data_access.session import get_db_session
from app.shared.data_access.tenancy import user_scoped_select
from app.shared.data_access.weaviate_client import delete_passages_for_document, write_passages

__all__ = ["get_db_session", "user_scoped_select", "delete_passages_for_document", "write_passages"]
