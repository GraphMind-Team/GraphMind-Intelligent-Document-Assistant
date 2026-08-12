"""Shared data-access layer.

Per architecture decision AD-2, this package is the sole path to Weaviate,
Neo4j, and Postgres. Every module's `repository.py` must go through code
here rather than opening its own client/connection, so per-user tenancy
filtering is enforced structurally instead of by convention.

Empty in Story 1.1 (running project skeleton) -- no real data-access code
exists yet. Future stories add clients/session factories here.
"""
