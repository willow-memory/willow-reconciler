"""Parse a numbered idea-pile doc into `Item` records.

Only top-level numbered list items are items: a line beginning (at column 0,
no leading whitespace — a numbered item nested under something else is not
one of these top-level ideas) with `<digits>.` followed by whitespace. Every
line in the doc is accounted for: a line that LOOKS like it might be an item
but is not (e.g. leading whitespace, or a number with no trailing space) is
never silently absorbed into the wrong item — see `parse_doc`'s `dropped`
return for the corpus-lens rule this mirrors ("a dropped item is surfaced,
not silently discarded").
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ITEM_RE = re.compile(r"^(\d+)\.\s+(.*)$")

# A line that is clearly SUPPOSED to be a numbered item (starts with digits
# and a dot) but doesn't match the strict item shape — e.g. no trailing
# whitespace after the dot ("12.nospace"). Counted in `dropped`, never
# silently folded into the previous item.
_NEAR_MISS_RE = re.compile(r"^(\d+)\.\S")


@dataclass(frozen=True)
class Item:
    num: int          # the doc's own local number (may have gaps — retired
                       # numbers, section breaks — never renumbered here)
    text: str          # the full line, minus "N. " prefix
    line_no: int       # 1-indexed line number in the source doc, for audit


def parse_doc(text: str) -> tuple[list[Item], int]:
    """Returns (items, dropped). `items` is in document order; `dropped` is a
    count of near-miss lines that looked like a numbered item but did not
    parse — surfaced so a caller can report it rather than pretend the doc
    was fully accounted for. Duplicate item numbers are kept (both instances
    parsed; `ledger.py` reports the collision, `parse_doc` does not resolve
    it) since deciding which one is authoritative is a judgment call outside
    Slice 0's scope."""
    items: list[Item] = []
    dropped = 0
    for i, line in enumerate(text.splitlines(), start=1):
        m = _ITEM_RE.match(line)
        if m:
            items.append(Item(num=int(m.group(1)), text=m.group(2), line_no=i))
            continue
        if _NEAR_MISS_RE.match(line):
            dropped += 1
    return items, dropped
