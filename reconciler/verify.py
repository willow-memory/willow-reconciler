"""Verify that every `Idea-Id` trailer in a repo's history resolves to a real
item in the doc it names.

This is the guard the convention needs to be trustworthy rather than merely
documented. A trailer is the classifier's highest-confidence evidence: rule 2a
asserts LANDED from it directly, ahead of every other inferred signal. But a
trailer is also just a string an author typed, and nothing else in the rule
stack can distinguish a real join key from a plausible-looking dead one — a
typo (`willow-ideas-24` for `-024`), or an id for an item since retired from
the doc. Such a trailer is worse than no trailer at all: it is silent,
permanent, and reads as the strongest evidence the tool has.

So: resolve them all against the doc, and report the ones that do not land
anywhere. Follows `ledger.py`'s result-shape (headline / n / reading).
"""
from __future__ import annotations

from .gitevidence import GitLog
from .ids import idea_id
from .parse import Item


def verify_trailers(doc: str, repo: str, items: list[Item], gitlog: GitLog) -> dict:
    known = {idea_id(i.num) for i in items}
    resolved: list[dict] = []
    unresolved: list[dict] = []

    for commit, ident, status in gitlog.all_idea_trailers():
        row = {
            "sha": commit.sha,
            "short_sha": commit.sha[:10],
            "subject": commit.subject,
            "idea_id": ident,
            "status": status,
        }
        (resolved if ident in known else unresolved).append(row)

    n = len(resolved) + len(unresolved)
    covered = sorted({r["idea_id"] for r in resolved})

    if not gitlog.available:
        headline = (f"Could not verify trailers for {doc} ({repo}): git history was "
                    f"unavailable ({gitlog.error}).")
    elif n == 0:
        headline = (f"No Idea-Id trailers found in {repo}'s history. The doc has "
                    f"{len(known)} item(s) available to reference; nothing to verify "
                    f"yet, and nothing is wrong — the convention is prospective.")
    else:
        headline = (f"{n} Idea-Id trailer(s) in {repo}'s history: {len(resolved)} "
                    f"resolve to an item in {doc} (covering {len(covered)} distinct "
                    f"item(s)), {len(unresolved)} name an id the doc does not contain.")

    reading = ("An unresolved trailer is a FALSE JOIN KEY, not a missing one: rule 2a "
               "asserts LANDED from a trailer ahead of every other inferred signal, and "
               "nothing else in the rule stack can tell a real id from a dead one. Fix "
               "the trailer (a later commit may restate it correctly) or the doc — an "
               "item retired from the doc leaves its trailers dangling. A run with zero "
               "trailers is not a failure; the convention only starts paying from the "
               "commit that first writes one.")

    return {
        "doc": doc,
        "repo": repo,
        "headline": headline,
        "n": n,
        "reading": reading,
        "git_available": gitlog.available,
        "items_in_doc": len(known),
        "n_resolved": len(resolved),
        "n_unresolved": len(unresolved),
        "distinct_items_covered": covered,
        "resolved": resolved,
        "unresolved": unresolved,
        "ok": gitlog.available and not unresolved,
    }
