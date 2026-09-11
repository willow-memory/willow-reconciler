import pytest

from reconciler.emit import find_items, trailer_block
from reconciler.parse import parse_doc

DOC = (
    "1. anchor the legend-tag regexes so a mention is not a tag\n"
    "2. cross-repo trailer search\n"
    "42. release-aware landing, reachable from a release TAG\n"
)


@pytest.fixture
def items():
    parsed, _ = parse_doc(DOC)
    return parsed


def test_trailer_block_zero_pads_to_the_fixed_width():
    assert trailer_block(24) == "Idea-Id: willow-ideas-024"


def test_landed_is_the_default_and_writes_no_status_line():
    """A status line should always mean something was deliberately said."""
    assert "Idea-Status" not in trailer_block(1)


def test_partial_adds_a_status_trailer():
    assert trailer_block(7, "partial") == "Idea-Id: willow-ideas-007\nIdea-Status: partial"


def test_unknown_status_is_refused():
    with pytest.raises(ValueError):
        trailer_block(7, "mostly")


def test_find_by_num_is_exact(items):
    assert [i.num for i in find_items(items, num=42)] == [42]
    assert find_items(items, num=99) == []


def test_find_by_grep_is_case_insensitive(items):
    assert [i.num for i in find_items(items, grep="TAG")] == [1, 42]


def test_grep_returns_every_match_rather_than_picking_one(items):
    """Resolution is the caller's job: guessing which idea a commit lands is
    exactly the error the trailer exists to prevent."""
    assert len(find_items(items, grep="a")) > 1


def test_exactly_one_selector_is_required(items):
    with pytest.raises(ValueError):
        find_items(items)
    with pytest.raises(ValueError):
        find_items(items, num=1, grep="anchor")
