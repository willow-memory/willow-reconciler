"""willow-reconciler: the idea-to-landing reconciler.

Slice 0 answers one narrow question deterministically: of the numbered items
in a fleet doc (an "idea pile" like willow-mcp's docs/ideas.md), how many
have landed, partially landed, or show no evidence of having started —
according to a fixed rule stack, never a model call.

Modules:
  parse.py       — turn a doc's text into numbered Item records.
  gitevidence.py — read-only git log queries used by the inferred tier.
  classify.py    — the deterministic rule stack, one verdict per item.
  ledger.py      — aggregate verdicts into a per-doc ledger (corpus-lens
                   result-shape: headline / n / reading, per verdict too).
  validate.py    — score a ledger against a doc's own hand-tags (the
                   Slice-0 acceptance test).
  cli.py         — `reconciler run --repo <name> --doc <path>`.
"""

from __future__ import annotations
