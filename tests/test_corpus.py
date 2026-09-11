"""The adversarial corpus's own test suite.

Every assertion here is a trap one of this repo's audits actually reproduced.
The suite's job is to make any future loosening of the rule stack prove itself
against them first — both audits so far found bugs a fixture like this would
have caught before they shipped, and unlike the willow-mcp checks these run
everywhere, including on a CI runner with no fleet siblings.
"""
from __future__ import annotations

import pytest

from fixtures.corpus import DANGLING_ID, EXPECTED, HOLDOUT_RECOVERABLE
from reconciler.classify import INFERRED, LANDED, NOT_STARTED, PARTIAL
from reconciler.ledger import build_ledger
from reconciler.validate import hand_tags, holdout_score
from reconciler.verify import verify_trailers


def _by_num(verdicts):
    """First verdict per number — item 11 appears twice on purpose."""
    out = {}
    for v in verdicts:
        out.setdefault(v.num, v)
    return out


# --- the precision guard -------------------------------------------------

def test_no_item_is_ever_falsely_landed(corpus_run):
    """THE invariant. Over-claiming is the cardinal error: every LANDED or
    PARTIAL in this corpus must be one the fixture says is real. A regression
    that reintroduces a weak signal fails here first, and names the item."""
    _, verdicts, _, _ = corpus_run
    for num, v in _by_num(verdicts).items():
        expected_status, _ = EXPECTED[num]
        if v.status in (LANDED, PARTIAL):
            assert expected_status == v.status, (
                f"item {num} claimed {v.status} on: {v.evidence}")


@pytest.mark.parametrize("num", sorted(EXPECTED))
def test_each_item_classifies_as_the_fixture_says(corpus_run, num):
    _, verdicts, _, _ = corpus_run
    v = _by_num(verdicts)[num]
    assert (v.status, v.evidence_kind) == EXPECTED[num]


# --- the individual traps, named so a failure says which one broke -------

def test_a_joke_item_naming_a_real_tool_is_not_landed(corpus_run):
    """~0/11 precision before the first audit removed token matching."""
    _, verdicts, _, _ = corpus_run
    assert _by_num(verdicts)[3].status == NOT_STARTED


def test_an_idea_cross_reference_is_not_a_pr_reference(corpus_run):
    """PR #103 really did merge here; "former #103" still is not a claim on it."""
    _, verdicts, _, _ = corpus_run
    assert _by_num(verdicts)[4].status == NOT_STARTED


def test_a_conventional_commit_naming_an_issue_is_not_a_squash_merge(corpus_run):
    _, verdicts, _, _ = corpus_run
    assert _by_num(verdicts)[5].status == NOT_STARTED


def test_a_real_merge_commit_is_evidence(corpus_run):
    """The control: rule 2b must still fire on git's own merge record, or the
    precision fixes above have simply disabled the rule."""
    _, verdicts, _, _ = corpus_run
    v = _by_num(verdicts)[6]
    assert (v.status, v.evidence_kind) == (LANDED, INFERRED)


def test_a_trailer_on_an_abandoned_branch_is_not_a_landing(corpus_run):
    _, verdicts, _, _ = corpus_run
    assert _by_num(verdicts)[9].status == NOT_STARTED


def test_prose_containing_a_marker_is_not_a_legend_tag(corpus_run):
    _, verdicts, _, _ = corpus_run
    assert _by_num(verdicts)[10].status == NOT_STARTED
    assert _by_num(verdicts)[11].status == NOT_STARTED


def test_partial_is_data_driven_from_the_commit(corpus_run):
    _, verdicts, _, _ = corpus_run
    v = _by_num(verdicts)[8]
    assert (v.status, v.evidence_kind) == (PARTIAL, INFERRED)


# --- parse-level hygiene, surfaced rather than silently absorbed ---------

def test_a_malformed_numbered_line_is_dropped_and_counted(corpus_run):
    _, _, _, dropped = corpus_run
    assert dropped == 1


def test_a_gap_in_numbering_is_preserved(corpus_run):
    items, _, _, _ = corpus_run
    nums = [i.num for i in items]
    assert 13 not in nums and 14 in nums


def test_a_duplicate_item_number_is_surfaced(corpus_run):
    items, verdicts, _, dropped = corpus_run
    ledger = build_ledger("docs/ideas.md", "corpus", len(items) + dropped, dropped,
                          verdicts)
    assert ledger["duplicate_nums"] == [11]


# --- verify --------------------------------------------------------------

def test_verify_catches_the_dangling_trailer(corpus, corpus_run):
    items, _, gitlog, _ = corpus_run
    result = verify_trailers("docs/ideas.md", "corpus", items, gitlog)
    assert result["ok"] is False
    assert [r["idea_id"] for r in result["unresolved"]] == [DANGLING_ID]


def test_verify_resolves_the_real_trailers(corpus_run):
    items, _, gitlog, _ = corpus_run
    result = verify_trailers("docs/ideas.md", "corpus", items, gitlog)
    assert set(result["distinct_items_covered"]) == {
        "willow-ideas-007", "willow-ideas-008",
        "willow-ideas-014", "willow-ideas-015"}


def test_verify_does_not_see_the_abandoned_branchs_trailer(corpus_run):
    """willow-ideas-009 resolves against the doc, so if `verify` ever saw it
    again it would report ok — a dangling-key check cannot catch this class."""
    items, _, gitlog, _ = corpus_run
    result = verify_trailers("docs/ideas.md", "corpus", items, gitlog)
    seen = {r["idea_id"] for r in result["resolved"] + result["unresolved"]}
    assert "willow-ideas-009" not in seen


# --- the hold-out, on a corpus where it can actually move ----------------

def test_holdout_recovers_exactly_what_real_evidence_supports(corpus_run):
    """The willow-mcp hold-out can only ever show 0/22, which proves the metric
    does not over-claim but never exercises the recovering path. Here one
    hand-tagged item also carries a trailer, so both directions are covered."""
    items, _, gitlog, _ = corpus_run
    result = holdout_score(items, gitlog)
    assert result["n_hand_tagged"] == len(hand_tags(items))
    recovered = {d["num"] for d in result["detail"] if d["recovered"]}
    assert recovered == HOLDOUT_RECOVERABLE


def test_every_holdout_miss_abstains_rather_than_guessing(corpus_run):
    items, _, gitlog, _ = corpus_run
    for d in holdout_score(items, gitlog)["detail"]:
        if not d["recovered"]:
            assert d["got"] == NOT_STARTED


def test_echo_check_is_trivially_perfect_and_says_so(corpus_run):
    """Rule 1 regression guard, and nothing more — the corpus version of the
    check whose willow-mcp twin has never run on a CI runner."""
    from reconciler.validate import echo_check

    items, verdicts, _, _ = corpus_run
    result = echo_check(hand_tags(items), verdicts)
    assert result["accuracy"] == 1.0
    assert "trivial" in result["note"]


def test_every_inferred_verdict_traces_to_a_resolvable_signal(corpus_run):
    """Structural guard against silently reintroducing a weak signal. An
    inferred hit must cite an Idea-Id trailer or a PR git shows merged — the
    two signals that resolve to something real. A future rule that starts
    matching bare tokens again would produce evidence citing neither."""
    _, verdicts, _, _ = corpus_run
    for v in verdicts:
        if v.evidence_kind == INFERRED:
            assert ("trailer" in v.evidence or "git history shows it merged" in v.evidence), (
                f"item {v.num} inferred from unrecognised evidence: {v.evidence}")


# --- the capability benchmark (item 25) -----------------------------------

def test_benchmark_separates_independent_from_self_witnessed(corpus, corpus_run):
    """The whole point: item 14's trailer was written by a commit that never
    touched the pile; item 15's was written by the commit that added its tag.
    Both recover under the hold-out, and only one of them is evidence."""
    from fixtures.corpus import EXPECTED_PROVENANCE
    from reconciler.benchmark import benchmark

    items, _, gitlog, _ = corpus_run
    result = benchmark(items, gitlog, str(corpus), "docs/ideas.md")
    got = {d["num"]: d["provenance"] for d in result["detail"] if d["recovered"]}
    assert got == EXPECTED_PROVENANCE


def test_independent_rate_is_lower_than_raw_recovery(corpus, corpus_run):
    """The number that must not be quoted, and the one that may."""
    from reconciler.benchmark import benchmark

    items, _, gitlog, _ = corpus_run
    result = benchmark(items, gitlog, str(corpus), "docs/ideas.md")
    assert result["n_recovered"] == 2
    assert result["n_recovered_independent"] == 1
    assert result["n_recovered_self_witnessed"] == 1
    assert result["independent_recovery_rate"] < result["recovery_rate"]


def test_corpus_provenance_counts_every_trailer(corpus, corpus_run):
    from reconciler.benchmark import benchmark

    items, _, gitlog, _ = corpus_run
    prov = benchmark(items, gitlog, str(corpus), "docs/ideas.md")["trailer_provenance"]
    # 007, 008, 014 and the dangling 404 never touch the doc; 015 does.
    assert prov == {"independent": 4, "self_witnessed": 1}


def test_a_tag_with_no_trailer_at_all_is_not_credited(corpus, corpus_run):
    from reconciler.benchmark import benchmark

    items, _, gitlog, _ = corpus_run
    result = benchmark(items, gitlog, str(corpus), "docs/ideas.md")
    unrecovered = {d["num"] for d in result["detail"] if not d["recovered"]}
    assert unrecovered == {1, 2, 12}
    for d in result["detail"]:
        if not d["recovered"]:
            assert d["provenance"] is None
