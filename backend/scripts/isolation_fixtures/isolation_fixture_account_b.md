# Meridian Fulcrum Holdings -- Isolation Proof Fixture (Account B)

## Summary

Meridian Fulcrum Holdings is a fixture vendor used by Story 6.2's
cross-tenant isolation proof (`backend/scripts/isolation_proof.py`). The
exact same vendor name is deliberately reused in Account A's fixture
(`isolation_fixture_account_a.md`) with different contract terms and a
different contact -- this is what stresses Neo4j's `user_id`-scoped
entity merge specifically: if that scoping ever slipped, the two
accounts' same-named vendor nodes (and their distinct contacts) would
blend into one shared graph entity instead of staying two separate ones.

## Verification Token

This document's unique verification token is
ISOLATION-TOKEN-BRAVO-9C1A47E2. This token belongs only to Account B and
must never appear in any response returned to another account.

## Contract Terms

The vendor agreement with Meridian Fulcrum Holdings, arranged on behalf of
Account B, runs for 30 months, starting 2027-06-01, at a flat rate of
$11,750 per month.

## Contact

The primary account contact at Meridian Fulcrum Holdings for this
engagement is Denny Okafor, Isolation Test Coordinator.
