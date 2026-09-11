from reconciler.parse import parse_doc


def test_parses_simple_numbered_items():
    text = "1. first idea\n2. second idea\n3. third\n"
    items, dropped = parse_doc(text)
    assert [i.num for i in items] == [1, 2, 3]
    assert [i.text for i in items] == ["first idea", "second idea", "third"]
    assert dropped == 0


def test_ignores_non_item_lines():
    text = "# heading\nsome prose\n1. an idea\n- a bullet, not numbered\n2. another\n"
    items, dropped = parse_doc(text)
    assert [i.num for i in items] == [1, 2]
    assert dropped == 0


def test_ignores_indented_numbered_lines():
    """A numbered line nested under something else (indented) is not a
    top-level idea item."""
    text = "1. real item\n    2. nested, not an item\n3. real item two\n"
    items, dropped = parse_doc(text)
    assert [i.num for i in items] == [1, 3]


def test_counts_near_miss_lines_as_dropped():
    text = "1. real item\n2.nospace after the dot\n3. real item two\n"
    items, dropped = parse_doc(text)
    assert [i.num for i in items] == [1, 3]
    assert dropped == 1


def test_keeps_duplicate_numbers_both_parsed():
    text = "1. first\n1. duplicate number\n"
    items, dropped = parse_doc(text)
    assert [i.num for i in items] == [1, 1]
    assert dropped == 0


def test_gaps_in_numbering_are_preserved_not_renumbered():
    text = "1. one\n5. five\n"
    items, _ = parse_doc(text)
    assert [i.num for i in items] == [1, 5]


def test_real_doc_yields_expected_item_count():
    """Locks the parse count against the real fleet doc this tool targets.
    If this ever fails, the doc changed shape (not just content) and the
    reconciler's parse assumptions need a fresh look."""
    import pathlib

    doc = (pathlib.Path(__file__).resolve().parents[2] / "willow-mcp" / "docs" / "ideas.md")
    if not doc.exists():
        import pytest

        pytest.skip("willow-mcp sibling absent; test_corpus.py covers parse "
                    "hygiene against the in-repo fixture")
    items, dropped = parse_doc(doc.read_text(encoding="utf-8"))
    assert len(items) == 111
    assert dropped == 0
