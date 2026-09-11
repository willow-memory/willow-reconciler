"""The deterministic rule stack. One `classify_item` call per item, one
`Verdict` out. No model call anywhere in this module — every branch is a
regex or an exact/whole-word match against text and git evidence already in
hand.

Rule order (first match wins):
  1. EXPLICIT legend tag on the item itself (✅ shipped / 🟡 partial) —
     `evidence_kind="explicit"`. The doc's own author already did the work;
     this tier just reads it back verbatim.
  2. INFERRED, from the target repo's git history — `evidence_kind="inferred"`,
     reported as such and never asserted as settled fact:
       a. an `Idea-Id: <id>` trailer naming this exact item (status taken
          from a same-commit `Idea-Status:` trailer if present, else
          LANDED — see `gitevidence.GitLog.find_idea_trailer`); or
       b. a PR number the item text names AS A PULL REQUEST
          (`PR_MENTION_RE` — "PR #123" / "pull request #123", never a bare
          "#123") that git's own history shows was actually merged
          (`GitLog.find_merged_pr`) — always LANDED, since a merged PR is a
          concrete, resolved artifact.
  3. NOT_STARTED / abstain — no evidence found under either tier. This means
     exactly that: absence of evidence, not evidence of absence.
     `Verdict.evidence` says so explicitly.

REDESIGN (post Opus-audit rework, Slice 0): the previous version of rule 2
also matched a bare backtick-quoted identifier against ANY commit mention,
and rule 2b matched ANY `#\\d+` substring in the item text, not just an
explicit PR reference. An audit found that combination was ~0/11 precision
on the real target doc (chaos-canon joke items matching real tool names;
idea-number cross-references like "folds in former #103" mistaken for PR
numbers). Both were removed rather than tuned tighter — see
`gitevidence.py`'s module docstring for the full account. The result is
fewer inferred hits, on purpose: under-claiming (abstain to NOT_STARTED)
beats over-claiming (a false LANDED). See `validate.py` for the honest,
non-circular way this is now measured.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .gitevidence import PR_MENTION_RE, GitLog

LANDED = "landed"
PARTIAL = "partial"
NOT_STARTED = "not_started"

EXPLICIT = "explicit"
INFERRED = "inferred"
NONE_KIND = "none"   # not "explicit"/"inferred" evidence — the absence of any

# A legend tag is a tag only at a DEFINED POSITION: leading the item text, or
# leading the final separator-delimited clause (" — ✅ shipped: ..."). A marker
# sitting mid-prose is a MENTION, and the audit already established for the
# inferred tier that a mention is not evidence. The unanchored version of these
# two regexes matched anywhere on the line, so an item that merely *discussed*
# legend tags ("propose ✅/🟡 tags back into the doc") classified LANDED with
# evidence_kind=explicit — the same over-claim, in the tier the ledger treats as
# authoritative. Group 1 is the marker onward, so `_explicit_tag`'s evidence
# text is unchanged; the full match additionally spans the separator, which is
# what `validate.strip_legend_tag` wants to remove anyway.
_TAG_ANCHOR = r"(?:^|\s[—–-]{1,2}\s*)"
_SHIPPED_RE = re.compile(_TAG_ANCHOR + r"(✅[^\n]*)")
_PARTIAL_RE = re.compile(_TAG_ANCHOR + r"(🟡[^\n]*)")

_VALID_STATUSES = (LANDED, PARTIAL, NOT_STARTED)


@dataclass(frozen=True)
class Verdict:
    idea_id: str
    num: int
    status: str            # LANDED | PARTIAL | NOT_STARTED
    evidence: str           # human-readable — what was found, or that nothing was
    evidence_kind: str       # EXPLICIT | INFERRED | NONE_KIND


def explicit_tag_span(text: str):
    """Returns the `re.Match` for whichever legend tag is present (✅ checked
    before 🟡 — see `_explicit_tag`), or None. Exposed (not prefixed `_`) so
    `validate.py`'s hold-out can find and strip exactly this span without
    duplicating the regex — see `validate.strip_legend_tag`. The match spans
    the anchoring separator as well as the marker, which is precisely the
    text the hold-out wants gone."""
    m = _SHIPPED_RE.search(text)
    if m:
        return m
    return _PARTIAL_RE.search(text)


def _explicit_tag(text: str) -> tuple[str, str] | None:
    """Returns (status, evidence_text) or None. ✅ checked before 🟡 — an
    item can only carry one legend tag in this doc, but if a future edit
    ever left both, shipped is the stronger claim and wins deterministically
    rather than depending on which regex happens to run first."""
    m = _SHIPPED_RE.search(text)
    if m:
        return LANDED, m.group(1).strip()
    m = _PARTIAL_RE.search(text)
    if m:
        return PARTIAL, m.group(1).strip()
    return None


def _inferred_tier(idea_id: str, text: str, gitlog: GitLog) -> tuple[str, str] | None:
    """Returns (status, evidence_text), or None if no REAL evidence was
    found. `status` comes from the evidence itself (see rule 2a/2b in the
    module docstring) — this function does not hardcode a status, it reports
    whatever the resolved evidence actually supports, which is how the
    inferred tier is able to emit PARTIAL rather than always LANDED."""
    if not gitlog.available:
        return None

    hit = gitlog.find_idea_trailer(idea_id)
    if hit is not None:
        c, status = hit
        assert status in _VALID_STATUSES
        return status, (f"commit {c.sha[:10]} carries trailer 'Idea-Id: {idea_id}' "
                        f"(status={status}): {c.subject!r}")

    for m in PR_MENTION_RE.finditer(text):
        pr_num = int(m.group(1))
        c = gitlog.find_merged_pr(pr_num)
        if c is not None:
            return LANDED, (f"item names PR #{pr_num}; git history shows it merged "
                            f"in commit {c.sha[:10]}: {c.subject!r}")
    return None


def classify_item(idea_id: str, num: int, text: str, gitlog: GitLog) -> Verdict:
    explicit = _explicit_tag(text)
    if explicit is not None:
        status, evidence = explicit
        return Verdict(idea_id=idea_id, num=num, status=status,
                       evidence=evidence, evidence_kind=EXPLICIT)

    inferred = _inferred_tier(idea_id, text, gitlog)
    if inferred is not None:
        status, evidence = inferred
        return Verdict(idea_id=idea_id, num=num, status=status,
                       evidence=evidence, evidence_kind=INFERRED)

    reason = ("no evidence found (no legend tag, no Idea-Id trailer, no PR named in "
              "the item text that git history shows as merged) — this means no "
              "evidence was located, not that the idea is proven unbuilt")
    if not gitlog.available:
        reason += f"; git history was unavailable ({gitlog.error})"
    return Verdict(idea_id=idea_id, num=num, status=NOT_STARTED,
                   evidence=reason, evidence_kind=NONE_KIND)
