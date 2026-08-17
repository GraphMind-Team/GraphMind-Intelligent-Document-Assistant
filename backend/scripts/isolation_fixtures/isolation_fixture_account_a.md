# Meridian Fulcrum Holdings -- Isolation Proof Fixture (Account A)

## Summary

Meridian Fulcrum Holdings is a fixture vendor used by Story 6.2's
cross-tenant isolation proof (`backend/scripts/isolation_proof.py`). The
exact same vendor name is deliberately reused in Account B's fixture
(`isolation_fixture_account_b.md`) with different contract terms and a
different contact -- this is what stresses Neo4j's `user_id`-scoped
entity merge specifically: if that scoping ever slipped, the two
accounts' same-named vendor nodes (and their distinct contacts) would
blend into one shared graph entity instead of staying two separate ones.

## Verification Token

This document's unique verification token is
ISOLATION-TOKEN-ALPHA-6F3D9C21. This token belongs only to Account A and
must never appear in any response returned to another account.

## Contract Terms

The vendor agreement with Meridian Fulcrum Holdings, arranged on behalf of
Account A, runs for 12 months, starting 2026-01-01, at a flat rate of
$4,200 per month.

## Contact

The primary account contact at Meridian Fulcrum Holdings for this
engagement is Talia Voss, Isolation Test Coordinator.
