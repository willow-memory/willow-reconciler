"""Slice 0's acceptance test, as a library function: does the tool's
classification reproduce the doc's own hand-tagged items?

Ground truth is the doc's own explicit legend tags (✅ shipped / 🟡 partial)
— the same signal rule 1 of the rule stack reads (see `classify.py`). This
is deliberate, not circular: rule 1 exists BECAUSE the doc's author already
did this labelling, and Slice 0's whole point is proving the tool's output
equals that labelling on the subset where it exists, before trusting the
tool's inferred/not_started calls on everything else. A caller who wants a
harder test can compare against a label set from a different source; this
module only ever computes precision/recall, it does not manufacture ground
truth.
"""
from __future__ import annotations

from .classify import LANDED, PARTIAL, Verdict, _explicit_tag
from .parse import Item


def hand_tags(items: list[Item]) -> dict[int, str]:
    """{item.num: status} for every item carrying an explicit legend tag."""
    out: dict[int, str] = {}
    for item in items:
        tag = _explicit_tag(item.text)
        if tag is not None:
            out[item.num] = tag[0]
    return out


def score(truth: dict[int, str], verdicts: list[Verdict]) -> dict:
    """Precision/recall/accuracy of `verdicts` against `truth`, restricted
    to the items `truth` actually covers (items outside `truth` say nothing
    about agreement — there is no hand tag to agree or disagree with)."""
    by_num = {v.num: v for v in verdicts}
    covered = [n for n in truth if n in by_num]
    missing = sorted(n for n in truth if n not in by_num)

    correct = [n for n in covered if by_num[n].status == truth[n]]
    disagreements = [
        {"num": n, "idea_id": by_num[n].idea_id, "expected": truth[n],
         "got": by_num[n].status}
        for n in covered if by_num[n].status != truth[n]
    ]

    per_class = {}
    for status in (LANDED, PARTIAL):
        tp = sum(1 for n in covered if truth[n] == status and by_num[n].status == status)
        fp = sum(1 for n in covered if truth[n] != status and by_num[n].status == status)
        fn = sum(1 for n in covered if truth[n] == status and by_num[n].status != status)
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        per_class[status] = {"tp": tp, "fp": fp, "fn": fn,
                             "precision": precision, "recall": recall}

    n = len(covered)
    accuracy = len(correct) / n if n else None
    return {
        "n_hand_tagged": len(truth),
        "n_covered": n,
        "missing_from_run": missing,
        "accuracy": accuracy,
        "disagreements": disagreements,
        "per_class": per_class,
    }
