"""The capability benchmark: how much of this tool's recall is real?

`validate.holdout_score` strips a hand-tag and asks whether the inferred tier
can recover it. That is honest about its method, but it is not yet evidence
about recall, because of who wrote the evidence. Every trailer in this repo's
own history was written in the SAME commit that added the doc tag it recovers
— the author had both facts in hand and wrote them together, so correspondence
is guaranteed by construction. A hold-out of 1.0 built that way measures
plumbing ("a correct trailer is found"), not capability ("landings can be
recovered"), and must never be set beside the willow-mcp corpus's 0.0 as if
the two measured the same thing.

The distinction is mechanical, not a judgement call: did the commit carrying
the trailer ALSO edit the pile?

  self-witnessed — the trailer commit edited the doc too. The tag and the key
      were authored in one act, so recovering one from the other demonstrates
      the pipeline works and nothing about recall.
  independent — the trailer commit did not touch the doc. The key was written
      by someone landing work, and the tag by someone curating the pile, as
      two separate acts. Recovering a tag from THAT is the real claim.

`independent_recovery_rate` is therefore the only number here that may be
quoted as a capability result, and it stays 0.0 until the convention has been
lived in rather than demonstrated. That is the expected reading today, and
saying so plainly is the point of the module.
"""
from __future__ import annotations

from .classify import classify_item
from .gitevidence import GitLog, changed_paths
from .ids import idea_id
from .parse import Item
from .validate import hand_tags, strip_legend_tag

SELF_WITNESSED = "self_witnessed"
INDEPENDENT = "independent"
UNATTRIBUTED = "unattributed"   # recovered, but the evidence commit is unknown

#: The caveat sentence every renderer of a benchmark result prints alongside
#: its headline. Module-level (not inlined in `benchmark`) so `reconciler
#: fleet` can quote it verbatim across many repos' rows without paraphrasing
#: it — see `fleet.py`.
READING = ("Quote `independent_recovery_rate`, never `recovery_rate`. The latter "
           "counts trailers whose author was holding the answer while writing them, "
           "so it can read 1.0 on a tool that has never recovered anything nobody "
           "told it. A 0.0 here alongside a high recovery_rate is the expected shape "
           "for a convention that has been demonstrated but not yet lived in — it is "
           "not a regression, and the fix for it is time, not code.")


def _evidence_sha(evidence: str, gitlog: GitLog) -> str | None:
    """The commit a verdict's evidence points at. `classify` renders the short
    sha into its evidence string; matching it back to a full sha here keeps
    `Verdict` unchanged rather than widening it for one consumer."""
    for commit in gitlog.commits:
        if commit.sha[:10] in evidence:
            return commit.sha
    return None


def benchmark(items: list[Item], gitlog: GitLog, repo_path: str, doc: str) -> dict:
    truth = hand_tags(items)
    by_num = {item.num: item for item in items}
    paths = changed_paths(repo_path)

    detail: list[dict] = []
    for num, expected in sorted(truth.items()):
        v = classify_item(idea_id(num), num, strip_legend_tag(by_num[num].text), gitlog)
        recovered = v.status == expected
        row = {
            "num": num,
            "idea_id": v.idea_id,
            "expected": expected,
            "got": v.status,
            "recovered": recovered,
            "provenance": None,
            "evidence_sha": None,
        }
        if recovered and v.evidence_kind == "inferred":
            sha = _evidence_sha(v.evidence, gitlog)
            row["evidence_sha"] = sha
            if sha is None:
                row["provenance"] = UNATTRIBUTED
            elif doc in paths.get(sha, ()):
                row["provenance"] = SELF_WITNESSED
            else:
                row["provenance"] = INDEPENDENT
        detail.append(row)

    n = len(detail)
    recovered = [d for d in detail if d["recovered"]]
    independent = [d for d in recovered if d["provenance"] == INDEPENDENT]
    self_witnessed = [d for d in recovered if d["provenance"] == SELF_WITNESSED]

    headline = (
        f"Of {n} hand-tagged item(s) in {doc}, {len(recovered)} were recovered with the "
        f"tag stripped — but only {len(independent)} from a trailer written independently "
        f"of the pile ({len(self_witnessed)} came from a commit that edited the doc in "
        f"the same act, which demonstrates the pipeline, not recall)."
    )
    return {
        "doc": doc,
        "headline": headline,
        "n": n,
        "reading": READING,
        "n_hand_tagged": n,
        "n_recovered": len(recovered),
        "n_recovered_independent": len(independent),
        "n_recovered_self_witnessed": len(self_witnessed),
        "recovery_rate": (len(recovered) / n) if n else None,
        "independent_recovery_rate": (len(independent) / n) if n else None,
        "trailer_provenance": _corpus_provenance(gitlog, paths, doc),
        "detail": detail,
    }


def _corpus_provenance(gitlog: GitLog, paths: dict, doc: str) -> dict:
    """Every trailer in the history, split the same way — a health number for
    the corpus itself, independent of whether any item is hand-tagged. This is
    what should climb as the convention gets used."""
    counts = {INDEPENDENT: 0, SELF_WITNESSED: 0}
    for commit, _ident, _status in gitlog.all_idea_trailers():
        key = SELF_WITNESSED if doc in paths.get(commit.sha, ()) else INDEPENDENT
        counts[key] += 1
    return counts
