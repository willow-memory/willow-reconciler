"""Build the per-doc ledger from a list of `Verdict`s.

Follows corpus-lens's result-shape convention (see
corpus-lens/corpuslens/analyze/__init__.py's module docstring): a `headline`
sentence stating the result in words, an `n` that is the same count the
headline describes, and a `reading` line giving direction guidance. This
module is the one place that shape is assembled, so every renderer/consumer
sees the same three fields regardless of format.
"""
from __future__ import annotations

from .classify import LANDED, NOT_STARTED, PARTIAL, Verdict


def build_ledger(doc: str, repo: str, items_total: int, dropped: int,
                 verdicts: list[Verdict]) -> dict:
    by_status = {LANDED: 0, PARTIAL: 0, NOT_STARTED: 0}
    for v in verdicts:
        by_status[v.status] += 1
    n = len(verdicts)

    duplicates = _duplicate_nums(verdicts)

    headline = (f"Of {n} item(s) parsed from {doc} ({repo}), "
                f"{by_status[LANDED]} landed, {by_status[PARTIAL]} partial, "
                f"{by_status[NOT_STARTED]} show no evidence of having started.")
    reading = ("'landed'/'partial' here mean 'evidence was found', not an audited "
               "completeness claim; 'not_started' means 'no evidence found', not "
               "'proven unbuilt'. See each item's evidence_kind: explicit (the doc's "
               "own legend tag) outranks inferred (a git-log match), which outranks "
               "none (nothing located).")

    return {
        "doc": doc,
        "repo": repo,
        "headline": headline,
        "n": n,
        "reading": reading,
        "items_total": items_total,
        "items_parsed": n,
        "dropped": dropped,
        "duplicate_nums": duplicates,
        "counts_by_status": by_status,
        "counts_by_evidence_kind": _by_evidence_kind(verdicts),
        "items": [
            {
                "idea_id": v.idea_id,
                "num": v.num,
                "status": v.status,
                "evidence": v.evidence,
                "evidence_kind": v.evidence_kind,
            }
            for v in verdicts
        ],
    }


def _by_evidence_kind(verdicts: list[Verdict]) -> dict:
    out: dict[str, int] = {}
    for v in verdicts:
        out[v.evidence_kind] = out.get(v.evidence_kind, 0) + 1
    return out


def _duplicate_nums(verdicts: list[Verdict]) -> list[int]:
    """Item numbers appearing more than once in the doc — surfaced, not
    silently resolved (see parse.py's docstring)."""
    seen: dict[int, int] = {}
    for v in verdicts:
        seen[v.num] = seen.get(v.num, 0) + 1
    return sorted(n for n, count in seen.items() if count > 1)
