from reconciler.ids import idea_id


def test_idea_id_shape():
    assert idea_id(1) == "willow-ideas-001"
    assert idea_id(24) == "willow-ideas-024"
    assert idea_id(123) == "willow-ideas-123"


def test_idea_id_is_stable_and_recomputable():
    """Calling it twice for the same number always gives the same id — no
    hidden state, no counter."""
    assert idea_id(42) == idea_id(42)


def test_idea_id_distinct_per_number():
    ids = {idea_id(n) for n in range(1, 124)}
    assert len(ids) == 123
