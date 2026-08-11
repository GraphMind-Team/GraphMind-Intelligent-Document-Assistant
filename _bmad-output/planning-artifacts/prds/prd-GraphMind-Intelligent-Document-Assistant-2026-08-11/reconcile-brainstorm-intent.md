# Reconciliation: brainstorm-intent.md vs PRD + Addendum

Input: `_bmad-output/brainstorming/brainstorm-graphmind-mvp-2026-08-11/brainstorm-intent.md`

## Gaps Found

1. **Citations-as-means vs. citations-as-end framing softened**: the brainstorm insight is explicit that "citations are the verification shortcut that earns this trust, not the goal in themselves," but PRD §1 states GraphMind "treats citation and honest refusal as the product's core promise," which reads as elevating citation itself to the goal rather than preserving it as a means to the trust north star.
2. **Write-desync mitigation strength downgraded without flagging it as a PRD-level open question**: the addendum risk register correctly notes "unified ingestion job status tracking both writes — not yet a committed design," but this un-committed status isn't carried into the PRD's own Open Questions (§8), so a reader of the PRD alone could mistake it for settled scope.
3. **"LLM answers using another user's documents" mechanism not distinctly named**: the brainstorm risk specifically flags leakage happening *through the LLM's answer*, not just through direct DB reads; PRD FR-2/SM-3 verify cross-tenant retrieval isolation via test accounts but don't call out testing/verifying that the LLM's generated answer itself never blends another user's retrieved context, which is a subtly different failure mode from a raw unauthorized query.
4. **20-day timeline / 2-developer KISS-YAGNI framing as a scope-shaping constraint** is present as background context (Vision §1, addendum Team) but the brainstorm's explicit causal link — that KISS/YAGNI is *why* the Must-list is shaped the way it is — isn't restated as a rationale anywhere in the PRD's MoSCoW-derived sections (§6), so the "why" behind scope cuts is only implicit.

No items were found fully absent — all MoSCoW entries, architecture decisions, and named risks trace to at least one PRD or addendum location; the gaps above are framing/nuance dilutions rather than missing content.
