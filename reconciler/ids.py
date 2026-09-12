"""Idea-id derivation. One function, kept apart from parse/classify because
both need it and neither should own it.

`willow-ideas-<zero-padded-localnum>` — derived from the doc's own number,
recomputable from the doc alone, no migration table, no counter file. Width
is fixed at 3 digits: the doc's numbers currently run 1-123, and a fixed
width means the id never reflows when the doc's own max grows past a power
of ten mid-life (an id computed today stays correct after #999 arrives,
where a "width = len(str(max_num))" scheme would silently reflow every
existing id)."""

from __future__ import annotations

_WIDTH = 3


def idea_id(num: int) -> str:
    return f"willow-ideas-{num:0{_WIDTH}d}"
