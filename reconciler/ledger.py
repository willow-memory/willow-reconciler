"""Build the per-doc ledger from a list of `Verdict`s.

Follows corpus-lens's result-shape convention (see
corpus-lens/corpuslens/analyze/__init__.py's module docstring): a `headline`
sentence stating the result in words, an `n` that is the same count the
headline describes, and a `reading` line giving direction guidance. This
module is the one place that shape is assembled, so every renderer/consumer
sees the same three fields regardless of format.

REDESIGN (post Opus-audit rework): the previous headline pooled
explicit-landed and inferred-landed into a single "N landed" figure with no
split visible where a reader would actually see it (finding #5 of the
audit — 12 real + 11 false inferred both counted as "landed" in the
headline sentence). `counts_by_status` alone is not enough to prevent this,
because a reader can look at ONE number without opening `counts_by_status`;
the headline sentence itself must carry the split now, and every per-item
row already carries `evidence_kind` alongside `status` for the same reason.
"""

from __future__ import annotations

from .classify import EXPLICIT, INFERRED, LANDED, NOT_STARTED, PARTIAL, Verdict

#: The caveat sentence every renderer of a ledger prints alongside its
#: headline. Module-level (not inlined in `build_ledger`) so `reconciler
#: fleet` can quote it verbatim across many repos' rows without paraphrasing
#: it — see `fleet.py`.
READING = (
    "NEVER read 'landed' as one pooled figure — explicit and inferred landed "
    "counts are kept apart on purpose (an explicit tag is the doc author's own "
    "word; an inferred hit is this tool's own git-log resolution, weaker and "
    "reported as such). 'not_started' means 'no evidence found', not 'proven "
    "unbuilt'. See each item's evidence_kind: explicit outranks inferred, which "
    "outranks none (nothing located). See `--validate`'s hold-out score for what "
    "the inferred tier can actually recover without being handed a tag."
)


def build_ledger(
    doc: str, repo: str, items_total: int, dropped: int, verdicts: list[Verdict]
) -> dict:
    by_status = {LANDED: 0, PARTIAL: 0, NOT_STARTED: 0}
    by_status_and_kind: dict[tuple[str, str], int] = {}
    for v in verdicts:
        by_status[v.status] += 1
        key = (v.status, v.evidence_kind)
        by_status_and_kind[key] = by_status_and_kind.get(key, 0) + 1
    n = len(verdicts)

    duplicates = _duplicate_nums(verdicts)

    n_explicit = sum(1 for v in verdicts if v.evidence_kind == EXPLICIT)
    landed_explicit = by_status_and_kind.get((LANDED, EXPLICIT), 0)
    landed_inferred = by_status_and_kind.get((LANDED, INFERRED), 0)
    partial_explicit = by_status_and_kind.get((PARTIAL, EXPLICIT), 0)
    partial_inferred = by_status_and_kind.get((PARTIAL, INFERRED), 0)
    n_untagged = n - n_explicit
    # NOT_STARTED is only ever reached with no evidence at all (rule 1 never
    # returns it, and rule 2 only returns when it found something) — so every
    # not_started item is, by construction, one of the untagged items.
    n_untagged_with_signal = n_untagged - by_status.get(NOT_STARTED, 0)

    headline = (
        f"Of {n} item(s) parsed from {doc} ({repo}): {n_explicit} carry the doc's own "
        f"explicit legend tag ({landed_explicit} landed, {partial_explicit} partial — "
        f"read back verbatim, not classified). Of the remaining {n_untagged} untagged "
        f"item(s), {n_untagged_with_signal} resolved to a real inferred signal "
        f"({landed_inferred} landed, {partial_inferred} partial) and "
        f"{by_status[NOT_STARTED]} show no reliable automatic landing signal."
    )
    return {
        "doc": doc,
        "repo": repo,
        "headline": headline,
        "n": n,
        "reading": READING,
        "items_total": items_total,
        "items_parsed": n,
        "dropped": dropped,
        "duplicate_nums": duplicates,
        "counts_by_status": by_status,
        "counts_by_evidence_kind": _by_evidence_kind(verdicts),
        "counts_by_status_and_kind": {
            f"{s}/{k}": v for (s, k), v in by_status_and_kind.items()
        },
        "items": [
            {
                "idea_id": v.idea_id,
                "num": v.num,
                "status": v.status,
                "evidence": v.evidence,
                "evidence_kind": v.evidence_kind,
                "rule": v.rule,
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
