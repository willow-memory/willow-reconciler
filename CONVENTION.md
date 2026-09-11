# The Idea-Id trailer convention

Adopted 2026-09-11 (operator ruling: "adopt the trailers going forward").
Recorded as governance decision `decision-2026-09-11-adopt-idea-id-trailers`;
proposed to Nestor as draft `11a1744c-6b83-48f5-9fd8-d7a929b5eabf` (seal pending).

## What

A commit that lands an idea recorded in a fleet doc carries a git trailer:

    Idea-Id: <corpus>-<docslug>-<num>

matching the id this reconciler derives for that doc entry
(e.g. `willow-ideas-042` for the 42nd entry of willow-mcp/docs/ideas.md).
When a commit only partly lands an idea, add:

    Idea-Status: partial

The default (trailer present, no status) means landed.

## Why it is prospective, not retroactive

willow-reconciler Slice 0 measured, on a held-out split of the *current*
corpus with tags stripped, a landing-recovery of **0.0**: no durable join
key was ever written, so deterministic inference recovers nothing, and a
model-based guess would violate the cheapest-capable rule. The ID's absence
is itself why "format predicts landing." The fix cannot look backward — it
starts writing the key now, and this reconciler grows useful as trailers
accumulate.

## Nothing to backfill on the doc side

The doc-side id is *derived* by `reconciler/ids.py` from the entry's position
in the doc — it is not stored in the doc. So no edit to ideas.md is required.
The only new discipline is on the commit side: emit the trailer when a commit
lands an idea. This sits alongside the `Co-Authored-By` / `Claude-Session`
trailers the harness already appends, so it is one more line.

## What counts as landing evidence

- The `Idea-Id` trailer on a merged commit (primary key).
- A commit body that says "PR #N" *and* git shows PR #N merged. A bare `#N`,
  or an idea-number cross-reference like "former #103", is NOT a PR ref — the
  reconciler rejects it (see tests/).
