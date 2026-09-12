from reconciler.classify import (
    EXPLICIT,
    INFERRED,
    LANDED,
    NONE_KIND,
    NOT_STARTED,
    PARTIAL,
    RULE_ABSTAIN,
    RULE_EXPLICIT_TAG,
    RULE_IDEA_ID_TRAILER,
    Verdict,
)
from reconciler.ledger import build_ledger


def test_counts_by_status_and_evidence_kind():
    verdicts = [
        Verdict("willow-ideas-001", 1, LANDED, "ev1", EXPLICIT, RULE_EXPLICIT_TAG),
        Verdict("willow-ideas-002", 2, PARTIAL, "ev2", EXPLICIT, RULE_EXPLICIT_TAG),
        Verdict("willow-ideas-003", 3, NOT_STARTED, "ev3", NONE_KIND, RULE_ABSTAIN),
    ]
    ledger = build_ledger(
        doc="docs/ideas.md",
        repo="willow-mcp",
        items_total=3,
        dropped=0,
        verdicts=verdicts,
    )
    assert ledger["n"] == 3
    assert ledger["counts_by_status"] == {LANDED: 1, PARTIAL: 1, NOT_STARTED: 1}
    assert ledger["counts_by_evidence_kind"] == {EXPLICIT: 2, NONE_KIND: 1}
    assert ledger["n"] == len(ledger["items"])


def test_headline_never_pools_explicit_and_inferred_landed():
    """Audit finding #5: explicit-landed and inferred-landed must never be
    summed into one unqualified figure in the headline a reader sees."""
    verdicts = [
        Verdict("willow-ideas-001", 1, LANDED, "ev", EXPLICIT, RULE_EXPLICIT_TAG),
        Verdict("willow-ideas-002", 2, LANDED, "ev", EXPLICIT, RULE_EXPLICIT_TAG),
        Verdict("willow-ideas-003", 3, LANDED, "ev", INFERRED, RULE_IDEA_ID_TRAILER),
    ]
    ledger = build_ledger(
        doc="d.md", repo="r", items_total=3, dropped=0, verdicts=verdicts
    )
    headline = ledger["headline"]
    # the pooled total (3) must not appear as an unqualified "3 landed" claim;
    # the explicit (2) and inferred (1) counts must each appear split out.
    assert "3 landed" not in headline
    assert "2 landed" in headline
    assert "1 landed" in headline
    assert ledger["counts_by_status_and_kind"][f"{LANDED}/{EXPLICIT}"] == 2
    assert ledger["counts_by_status_and_kind"][f"{LANDED}/{INFERRED}"] == 1


def test_every_item_row_carries_evidence_kind():
    verdicts = [
        Verdict("willow-ideas-001", 1, LANDED, "ev", INFERRED, RULE_IDEA_ID_TRAILER)
    ]
    ledger = build_ledger(
        doc="d.md", repo="r", items_total=1, dropped=0, verdicts=verdicts
    )
    assert ledger["items"][0]["evidence_kind"] == INFERRED
    assert ledger["items"][0]["status"] == LANDED


def test_every_item_row_carries_rule_provenance():
    """Task 2: which rule fired must be visible on the emitted row, not just
    inferable from evidence_kind — the whole point is inspectability without
    reading the source."""
    verdicts = [
        Verdict("willow-ideas-001", 1, LANDED, "ev", EXPLICIT, RULE_EXPLICIT_TAG),
        Verdict("willow-ideas-002", 2, LANDED, "ev", INFERRED, RULE_IDEA_ID_TRAILER),
        Verdict("willow-ideas-003", 3, NOT_STARTED, "ev", NONE_KIND, RULE_ABSTAIN),
    ]
    ledger = build_ledger(
        doc="d.md", repo="r", items_total=3, dropped=0, verdicts=verdicts
    )
    rules = {row["idea_id"]: row["rule"] for row in ledger["items"]}
    assert rules == {
        "willow-ideas-001": RULE_EXPLICIT_TAG,
        "willow-ideas-002": RULE_IDEA_ID_TRAILER,
        "willow-ideas-003": RULE_ABSTAIN,
    }


def test_reports_dropped_and_items_total_separately():
    verdicts = [
        Verdict("willow-ideas-001", 1, LANDED, "ev", EXPLICIT, RULE_EXPLICIT_TAG)
    ]
    ledger = build_ledger(
        doc="d.md", repo="r", items_total=2, dropped=1, verdicts=verdicts
    )
    assert ledger["items_parsed"] == 1
    assert ledger["items_total"] == 2
    assert ledger["dropped"] == 1


def test_surfaces_duplicate_item_numbers():
    verdicts = [
        Verdict("willow-ideas-001", 1, LANDED, "ev", EXPLICIT, RULE_EXPLICIT_TAG),
        Verdict("willow-ideas-001", 1, PARTIAL, "ev2", EXPLICIT, RULE_EXPLICIT_TAG),
    ]
    ledger = build_ledger(
        doc="d.md", repo="r", items_total=2, dropped=0, verdicts=verdicts
    )
    assert ledger["duplicate_nums"] == [1]


def test_no_duplicates_is_empty_list():
    verdicts = [
        Verdict("willow-ideas-001", 1, LANDED, "ev", EXPLICIT, RULE_EXPLICIT_TAG)
    ]
    ledger = build_ledger(
        doc="d.md", repo="r", items_total=1, dropped=0, verdicts=verdicts
    )
    assert ledger["duplicate_nums"] == []
