"""The deterministic rule stack. One `classify_item` call per item, one
`Verdict` out. No model call anywhere in this module — every branch is a
regex or an exact/whole-word string match against text already in hand.

Rule order (first match wins):
  1. EXPLICIT legend tag on the item itself (✅ shipped / 🟡 partial) —
     `evidence_kind="explicit"`. The doc's own author already did the work;
     this tier just reads it back verbatim.
  2. INFERRED, from the target repo's git history — `evidence_kind="inferred"`,
     reported as such and never asserted as settled fact:
       a. an `Idea-Id: <id>` trailer naming this exact item, or
       b. a PR number the ITEM TEXT ITSELF names (`(#123)`) that a commit
          also names, or
       c. a strong backtick-identifier token from the item text found as a
          whole word in a commit subject/body.
  3. NOT_STARTED — no evidence found under either tier. This means exactly
     that: absence of evidence, not evidence of absence. `Verdict.evidence`
     says so explicitly so a reader never mistakes it for "proven not
     built".

KNOWN LIMITATION (observed on the real willow-mcp/docs/ideas.md, Slice 0):
rule 2c (backtick-token match) has weaker precision than 2a/2b. It correctly
finds real prior art for serious ideas (e.g. `friction_floor`, `session_id`),
but it also fires on THE CHAOS CANON's satirical items whenever their text
happens to name a real tool (e.g. #109's joke about `whoami` matches a real
`whoami`-touching commit and comes back LANDED, which is the wrong read of
that item's intent). This does not affect the Slice-0 acceptance test — none
of the hand-tagged items hit this path — but it means 2c's LANDED calls
outside the hand-tagged set should be read as "this identifier exists in the
codebase", not "this specific idea shipped". A future slice could scope 2c to
sections without a chaos-canon marker, or require corroborating context.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .gitevidence import GitLog

LANDED = "landed"
PARTIAL = "partial"
NOT_STARTED = "not_started"

EXPLICIT = "explicit"
INFERRED = "inferred"
NONE_KIND = "none"   # not "explicit"/"inferred" evidence — the absence of any

_SHIPPED_RE = re.compile(r"(✅[^\n]*)")
_PARTIAL_RE = re.compile(r"(🟡[^\n]*)")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_PR_IN_TEXT_RE = re.compile(r"#(\d+)\b")


@dataclass(frozen=True)
class Verdict:
    idea_id: str
    num: int
    status: str            # LANDED | PARTIAL | NOT_STARTED
    evidence: str           # human-readable — what was found, or that nothing was
    evidence_kind: str       # EXPLICIT | INFERRED | NONE_KIND


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


def _inferred_tier(idea_id: str, text: str, gitlog: GitLog) -> str | None:
    """Returns an evidence string, or None if no inferred evidence was
    found. Any inferred hit classifies as LANDED (a matched commit is
    evidence the idea exists in the codebase, not evidence of exactly how
    much of it does) — Slice 0 keeps this single-valued rather than guessing
    at a landed/partial split that git history alone cannot support."""
    if not gitlog.available:
        return None

    c = gitlog.find_idea_trailer(idea_id)
    if c is not None:
        return f"commit {c.sha[:10]} carries trailer 'Idea-Id: {idea_id}': {c.subject!r}"

    for m in _PR_IN_TEXT_RE.finditer(text):
        pr_num = int(m.group(1))
        c = gitlog.find_pr_reference(pr_num)
        if c is not None:
            return f"item names #{pr_num}; commit {c.sha[:10]} also names it: {c.subject!r}"

    tokens = tuple(_BACKTICK_RE.findall(text))
    if tokens:
        hit = gitlog.find_token_match(tokens)
        if hit is not None:
            c, token = hit
            return f"identifier `{token}` from the item text found in commit {c.sha[:10]}: {c.subject!r}"
    return None


def classify_item(idea_id: str, num: int, text: str, gitlog: GitLog) -> Verdict:
    explicit = _explicit_tag(text)
    if explicit is not None:
        status, evidence = explicit
        return Verdict(idea_id=idea_id, num=num, status=status,
                       evidence=evidence, evidence_kind=EXPLICIT)

    inferred = _inferred_tier(idea_id, text, gitlog)
    if inferred is not None:
        return Verdict(idea_id=idea_id, num=num, status=LANDED,
                       evidence=inferred, evidence_kind=INFERRED)

    reason = ("no evidence found (no legend tag, no Idea-Id trailer, no matching "
              "PR reference or identifier in git log) — this means no evidence was "
              "located, not that the idea is proven unbuilt")
    if not gitlog.available:
        reason += f"; git history was unavailable ({gitlog.error})"
    return Verdict(idea_id=idea_id, num=num, status=NOT_STARTED,
                   evidence=reason, evidence_kind=NONE_KIND)
