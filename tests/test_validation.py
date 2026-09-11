"""Slice 0's acceptance test — REDESIGNED after an Opus audit found the
original version circular (ground truth was built from the same function
rule 1 reads; `accuracy=1.0` proved only that rule 1 echoes a tag it just
read). The real test here is the hold-out: strip each hand-tagged item's own
legend tag, reclassify with only the inferred/not_started tiers, and compare
against the human label the tag used to carry.

Runs against the REAL willow-mcp/docs/ideas.md, which exists only in a full
fleet checkout — so these skip on a CI runner and always have. They are a
SUPPLEMENT, not the coverage: `tests/test_corpus.py` asserts the same
behaviours against the in-repo adversarial corpus and runs everywhere. What
these add is the one thing a fixture cannot fake — the real doc's real shape.
"""
import pathlib

import pytest

from reconciler.classify import NOT_STARTED, classify_item
from reconciler.gitevidence import GitLog
from reconciler.ids import idea_id
from reconciler.parse import parse_doc
from reconciler.validate import echo_check, hand_tags, holdout_score, strip_legend_tag

FLEET_ROOT = pathlib.Path(__file__).resolve().parents[2]
IDEAS_DOC = FLEET_ROOT / "willow-mcp" / "docs" / "ideas.md"


@pytest.fixture
def real_run():
    if not IDEAS_DOC.exists():
        pytest.skip("willow-mcp sibling absent; test_corpus.py covers this "
                    "behaviour against the in-repo fixture")
    text = IDEAS_DOC.read_text(encoding="utf-8")
    items, dropped = parse_doc(text)
    gitlog = GitLog.load(str(FLEET_ROOT / "willow-mcp"))
    verdicts = [classify_item(idea_id(i.num), i.num, i.text, gitlog) for i in items]
    return items, verdicts, gitlog


def test_at_least_twenty_hand_tagged_items_exist(real_run):
    items, _, _ = real_run
    truth = hand_tags(items)
    assert len(truth) >= 20


def test_strip_legend_tag_removes_the_tag_but_not_the_idea():
    text = "**🌱 idea title** — some description here. — ✅ **shipped**: in `x.py`."
    stripped = strip_legend_tag(text)
    assert "✅" not in stripped
    assert "shipped" not in stripped
    assert "idea title" in stripped


def test_strip_legend_tag_is_a_noop_when_no_tag_present():
    text = "an item with no legend tag at all"
    assert strip_legend_tag(text) == text


def test_echo_check_is_trivially_perfect_and_labelled_as_such(real_run):
    """Sanity guard on rule 1 only — NOT the acceptance metric. Kept to
    prove rule 1 hasn't regressed, but its own `note` field says so."""
    items, verdicts, _ = real_run
    truth = hand_tags(items)
    result = echo_check(truth, verdicts)
    assert result["accuracy"] == 1.0
    assert "trivial" in result["note"]


def test_holdout_score_is_the_honest_number(real_run):
    """THE gradable claim, post-redesign: with legend tags stripped, the
    inferred tier currently has no real (Idea-Id-trailer / merged-PR)
    evidence to recover any of the 22 hand-tagged items from on the real
    willow-mcp doc — willow-mcp's git history carries no `Idea-Id:` trailers
    and no item names a PR as `PR #N`/`pull request #N`. Recovery is
    honestly 0/22 rather than a false 22/22. If this ever creeps upward
    without a corresponding real signal (a trailer, a resolved PR mention)
    actually existing, that is itself worth investigating — see
    `test_holdout_never_over_claims_via_removed_signals` below for the
    invariant that guards against silently reintroducing a weak signal."""
    items, _, gitlog = real_run
    result = holdout_score(items, gitlog)
    assert result["n_hand_tagged"] >= 20
    assert result["n_recovered"] == 0
    assert result["recovery_rate"] == 0.0
    # every miss must fall to not_started (abstain), never a wrong landed/partial
    for d in result["detail"]:
        assert d["got"] == NOT_STARTED


def test_holdout_never_over_claims_via_removed_signals(real_run):
    """Structural guard for audit finding #3: no hold-out miss should ever
    come back with evidence_kind=inferred pointing at a bare token or an
    idea-number cross-reference — every inferred hit must trace to a real,
    resolvable signal (Idea-Id trailer or a merged PR the item names as a
    PR). On the current doc + git history that means: no inferred hits at
    all in the hold-out, by design."""
    items, _, gitlog = real_run
    result = holdout_score(items, gitlog)
    inferred_hits = [d for d in result["detail"] if d["evidence_kind"] == "inferred"]
    assert inferred_hits == []


def test_strip_legend_tag_removes_the_anchored_separator_too():
    """The anchored span now covers the ` — ` in front of the tag, so the
    stripped text is the idea alone — no dangling separator for the inferred
    tier to see."""
    assert strip_legend_tag("an idea — ✅ **shipped**: in `x.py`.") == "an idea"


def test_strip_legend_tag_leaves_a_mid_prose_marker_alone():
    """A mention is not a tag, so there is nothing to strip — and stripping it
    would silently delete real item text."""
    text = "propose ✅/🟡 legend tags back into the doc"
    assert strip_legend_tag(text) == text
