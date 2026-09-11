"""The write side of the convention: given a doc, hand back the exact trailer
line a commit should carry.

`CONVENTION.md` bets the whole tool on `Idea-Id` trailers accumulating from
today forward — the Slice-0 recovery of 0.0 is a measurement of their absence,
not of the rule stack. But nothing shipped a way to *emit* one, so every
trailer had to be typed from memory against a doc in another repo. This module
is the missing half: it reads the doc, resolves which item is being landed, and
prints the line.

Resolution is by the item's own number (`--num`) or by matching its text
(`--grep`). Matching is a DOC-SIDE CONVENIENCE ONLY — it picks which line you
meant, and its output is a string for a human to paste. It is never evidence,
never reaches `classify.py`, and cannot move a verdict. That separation is why
a loose substring match is safe here while the same looseness was removed from
the inferred tier: over-matching costs an ambiguity error, not a false LANDED.
"""
from __future__ import annotations

from .ids import idea_id
from .parse import Item

VALID_STATUSES = ("landed", "partial")


def find_items(items: list[Item], num: int | None = None,
               grep: str | None = None) -> list[Item]:
    """Items matching the selector, in document order. `num` is an exact match
    on the doc's own number; `grep` is a case-insensitive substring of the item
    text. Returns every match — resolving a 0- or many-match result is the
    caller's job, and `cli.py` reports it rather than guessing, since guessing
    which idea a commit lands is exactly the error the trailer exists to
    prevent."""
    if (num is None) == (grep is None):
        raise ValueError("pass exactly one of num/grep")
    if num is not None:
        return [i for i in items if i.num == num]
    needle = grep.lower()
    return [i for i in items if needle in i.text.lower()]


def trailer_block(num: int, status: str = "landed") -> str:
    """The trailer line(s) for one item. `landed` is the convention's default
    and writes no `Idea-Status`, so the common case stays a single line and a
    status line always means something was deliberately said."""
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}, got {status!r}")
    lines = [f"Idea-Id: {idea_id(num)}"]
    if status != "landed":
        lines.append(f"Idea-Status: {status}")
    return "\n".join(lines)
