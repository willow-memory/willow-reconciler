"""Slice 0's acceptance test, as a library function.

REDESIGN (post Opus-audit rework): the original version of this module
scored the tool's classification against ground truth built by calling the
SAME `_explicit_tag()` function rule 1 of the classifier calls — so
`truth == verdict` by construction for every item that reaches rule 1, and
the resulting "accuracy=1.0" proved only that the tool echoes a tag it just
read, nothing about its actual capability. That metric is kept below as
`echo_check` for what it is worth (a sanity check that rule 1 has not
regressed), but it is NOT the acceptance number anymore.

The real number is `holdout_score`: for every hand-tagged item, STRIP the
legend tag out of its text (so rule 1 cannot fire) and re-classify with only
the inferred/not_started tiers available, then compare that result to the
human label the tag used to carry. This measures what the tool can actually
recover without being handed the answer — which is the whole point of a
reconciler whose real job is the ~89 items nobody has hand-tagged yet.
"""
from __future__ import annotations

from .classify import Verdict, _explicit_tag, classify_item, explicit_tag_span
from .gitevidence import GitLog
from .ids import idea_id
from .parse import Item


def hand_tags(items: list[Item]) -> dict[int, str]:
    """{item.num: status} for every item carrying an explicit legend tag —
    the doc's own ground truth, read once, used by both metrics below."""
    out: dict[int, str] = {}
    for item in items:
        tag = _explicit_tag(item.text)
        if tag is not None:
            out[item.num] = tag[0]
    return out


def strip_legend_tag(text: str) -> str:
    """Remove the item's own ✅/🟡 evidence clause, plus a dangling
    separator left in front of it (` — `, ` -- `), so the inferred tier is
    classifying the same information a fresh, unlabelled item would carry —
    not silently reading the answer back out of the tag it is supposed to be
    tested without. Returns `text` unchanged if it carries no legend tag."""
    m = explicit_tag_span(text)
    if m is None:
        return text
    head = text[: m.start()]
    head = head.rstrip()
    for sep in ("—", "--", "-"):
        if head.endswith(sep):
            head = head[: -len(sep)].rstrip()
            break
    return head


def echo_check(truth: dict[int, str], verdicts: list[Verdict]) -> dict:
    """The TRIVIAL metric: does the tool's normal (tag-intact) run reproduce
    the tag it just read via rule 1? This is expected to be 1.0 whenever
    rule 1 is implemented correctly — it is a regression guard on rule 1,
    NOT evidence the tool can classify anything it wasn't handed the answer
    for. Kept separate from, and clearly subordinate to, `holdout_score`."""
    by_num = {v.num: v for v in verdicts}
    covered = [n for n in truth if n in by_num]
    correct = [n for n in covered if by_num[n].status == truth[n]]
    n = len(covered)
    return {
        "n": n,
        "correct": len(correct),
        "accuracy": (len(correct) / n) if n else None,
        "note": "trivial by construction — rule 1 reads the same tag this truth set "
                "reads; see holdout_score for the real capability number.",
    }


def holdout_score(items: list[Item], gitlog: GitLog) -> dict:
    """The REAL Slice-0 acceptance metric: strip each hand-tagged item's own
    tag, reclassify with the tag gone, and compare against the human label.
    Reports overall recovery plus a breakdown of what the inferred tier
    actually returned for each item (so a reader can see exactly which
    became `landed`, `partial`, or `not_started`, and why) — see
    `cli.py --validate` for how this renders."""
    truth = hand_tags(items)
    by_num = {item.num: item for item in items}
    # A WORD ON WHAT A HIGH SCORE HERE DOES AND DOES NOT MEAN.
    #
    # Unlike `echo_check`, this is a genuinely different code path from the
    # ground truth — a real `git log` trailer lookup, not the same regex read
    # twice — so it does prove the trailer mechanism resolves end to end.
    #
    # But it is still only as honest as the trailers it reads. When the same
    # author writes a commit's `Idea-Id` trailer and the doc's legend tag for
    # that item in the SAME commit, perfect correspondence is guaranteed by
    # construction: the score then measures plumbing ("a correct trailer is
    # found"), not capability ("landings can be recovered"). Such a number must
    # never be set beside the willow-mcp corpus's 0.0 as though the two
    # measured the same thing — the corpus number is about trailers that
    # accumulated organically, disconnected from doc edits, which is the only
    # condition this tool actually has to survive.
    detail = []
    for num, expected in sorted(truth.items()):
        item = by_num[num]
        stripped = strip_legend_tag(item.text)
        v = classify_item(idea_id(num), num, stripped, gitlog)
        detail.append({
            "num": num,
            "idea_id": v.idea_id,
            "expected": expected,
            "got": v.status,
            "evidence_kind": v.evidence_kind,
            "recovered": v.status == expected,
        })
    n = len(detail)
    recovered = sum(1 for d in detail if d["recovered"])
    return {
        "n_hand_tagged": n,
        "n_recovered": recovered,
        "recovery_rate": (recovered / n) if n else None,
        "detail": detail,
    }
