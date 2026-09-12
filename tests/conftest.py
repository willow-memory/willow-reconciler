"""Shared fixtures.

The adversarial corpus is built ONCE per test session (it shells out to git a
dozen times) and handed to tests read-only — nothing in the suite may mutate
it, which is also true of the tool itself.
"""

from __future__ import annotations

import pytest
from fixtures.corpus import DOC_RELPATH, build_corpus


@pytest.fixture(scope="session")
def corpus(tmp_path_factory):
    """Path to the built adversarial fixture repo."""
    return build_corpus(tmp_path_factory.mktemp("fleet") / "adversarial-corpus")


@pytest.fixture(scope="session")
def corpus_doc(corpus):
    return corpus / DOC_RELPATH


@pytest.fixture(scope="session")
def corpus_run(corpus, corpus_doc):
    """(items, verdicts, gitlog) for the fixture corpus — the same shape the
    willow-mcp `real_run` fixture produces, so tests can be written once."""
    from reconciler.classify import classify_item
    from reconciler.gitevidence import GitLog
    from reconciler.ids import idea_id
    from reconciler.parse import parse_doc

    items, dropped = parse_doc(corpus_doc.read_text(encoding="utf-8"))
    gitlog = GitLog.load(str(corpus))
    verdicts = [classify_item(idea_id(i.num), i.num, i.text, gitlog) for i in items]
    return items, verdicts, gitlog, dropped
