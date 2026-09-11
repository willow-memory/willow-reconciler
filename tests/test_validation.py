"""Slice 0's acceptance test: the tool must reproduce the doc's own
hand-tagged (✅/🟡) items. Runs against the REAL willow-mcp/docs/ideas.md —
skipped if that sibling repo is not present in this checkout (this package
is deliberately usable/testable without every other fleet repo checked out
alongside it)."""
import pathlib

import pytest

from reconciler.classify import classify_item
from reconciler.gitevidence import GitLog
from reconciler.ids import idea_id
from reconciler.parse import parse_doc
from reconciler.validate import hand_tags, score

FLEET_ROOT = pathlib.Path(__file__).resolve().parents[2]
IDEAS_DOC = FLEET_ROOT / "willow-mcp" / "docs" / "ideas.md"


@pytest.fixture
def real_run():
    if not IDEAS_DOC.exists():
        pytest.skip("willow-mcp sibling repo not present in this checkout")
    text = IDEAS_DOC.read_text(encoding="utf-8")
    items, dropped = parse_doc(text)
    gitlog = GitLog.load(str(FLEET_ROOT / "willow-mcp"))
    verdicts = [classify_item(idea_id(i.num), i.num, i.text, gitlog) for i in items]
    return items, verdicts


def test_at_least_twenty_hand_tagged_items_exist(real_run):
    items, _ = real_run
    truth = hand_tags(items)
    assert len(truth) >= 20


def test_reproduces_every_hand_tagged_item_exactly(real_run):
    """The gradable claim: 100% precision AND recall on both classes for the
    doc's hand-tagged subset."""
    items, verdicts = real_run
    truth = hand_tags(items)
    result = score(truth, verdicts)

    assert result["missing_from_run"] == []
    assert result["disagreements"] == []
    assert result["accuracy"] == 1.0
    for status, pc in result["per_class"].items():
        assert pc["precision"] == 1.0, f"{status} precision: {pc}"
        assert pc["recall"] == 1.0, f"{status} recall: {pc}"
