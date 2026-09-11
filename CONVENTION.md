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

## Tooling (you should not be typing these by hand)

    reconciler id --repo <repo> --doc <doc> --num 42      # print the trailer line
    reconciler id --repo <repo> --doc <doc> --grep "text"  # ... or find it by text
    reconciler install-hook --repo <repo>                  # write it automatically
    reconciler verify --repo <repo> --doc <doc>            # check they all resolve

`install-hook` adds a `prepare-commit-msg` hook that derives the trailer from
a branch name that names an idea number (`idea-42`, `ideas-042`,
`feature/idea_42-thing`), and a `commit-msg` hook that rejects a malformed
`Idea-Id` or `Idea-Status` line. Neither hook can invent a link: the first
fires only when the branch already carries the number, and it never overwrites
a trailer written by hand.

A commit may carry several `Idea-Id` trailers when it lands several ideas.
`Idea-Status` is commit-level, so a commit saying `partial` says it about
every id it names.

## A wrong id is worse than no id

An `Idea-Id` that resolves to nothing is not a harmless typo. Rule 2a asserts
LANDED from a trailer ahead of every other inferred signal, and nothing else in
the rule stack can distinguish a real join key from a plausible-looking dead
one — so a dangling trailer is a silent, permanent, confident wrong answer.
That is why the id shape is fixed (`willow-ideas-NNN`, three digits), why the
commit-msg hook rejects anything else, and why `reconciler verify` runs in CI.

## Nothing to backfill on the doc side

The doc-side id is *derived* by `reconciler/ids.py` from the entry's position
in the doc — it is not stored in the doc. So no edit to ideas.md is required.
The only new discipline is on the commit side: emit the trailer when a commit
lands an idea. This sits alongside the `Co-Authored-By` / `Claude-Session`
trailers the harness already appends, so it is one more line.

## What counts as landing evidence

- The `Idea-Id` trailer on a commit **reachable from the checkout being
  reconciled** (primary key). Evidence is scoped to `git log HEAD`, not
  `git log --all`: a trailer on an abandoned or rejected branch is not a
  landing, and reading it as one was a false LANDED sourced from the ref scope.
- A commit body that says "PR #N" *and* git shows PR #N merged **as a real
  merge commit** (two or more parents, with GitHub's own merge subject). A bare
  `#N`, or an idea-number cross-reference like "former #103", is NOT a PR ref —
  the reconciler rejects it (see tests/).

Deliberately NOT evidence: a subject ending `(#N)`. That is GitHub's
squash-merge title shape, but it is also the ordinary conventional-commit habit
of naming an issue, and the two are indistinguishable from git alone — it
asserted LANDED for unrelated commits. Repos that squash-merge should rely on
the trailer, which is the durable key regardless of merge strategy.

A legend tag in the doc is read as a tag only when it LEADS the item text or
when its dash-introduced clause NAMES its legend keyword (`shipped` / `partial`).
An ordinary sentence containing an em-dash and a marker is prose, not a tag.
