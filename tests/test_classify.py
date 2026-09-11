from reconciler.classify import (
    EXPLICIT,
    INFERRED,
    LANDED,
    NONE_KIND,
    NOT_STARTED,
    PARTIAL,
    classify_item,
)
from reconciler.gitevidence import Commit, GitLog

EMPTY_GITLOG = GitLog(repo_path="/nonexistent", commits=(), available=True)
UNAVAILABLE_GITLOG = GitLog(repo_path="/nonexistent", available=False, error="not a git repo")


def test_explicit_shipped_tag_wins():
    text = "**idea** — ✅ **shipped**: lives in `foo.py`."
    v = classify_item("willow-ideas-001", 1, text, EMPTY_GITLOG)
    assert v.status == LANDED
    assert v.evidence_kind == EXPLICIT
    assert "✅" in v.evidence


def test_explicit_partial_tag():
    text = "**idea** — 🟡 **partial**: the primitive exists."
    v = classify_item("willow-ideas-002", 2, text, EMPTY_GITLOG)
    assert v.status == PARTIAL
    assert v.evidence_kind == EXPLICIT
    assert "🟡" in v.evidence


def test_explicit_beats_inferred():
    """Even when the git log WOULD match, an explicit tag on the item wins —
    rule 1 outranks rule 2."""
    commits = (Commit(sha="a" * 40, subject="Idea-Id: willow-ideas-003", body=""),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    text = "**idea** — ✅ **shipped**: done."
    v = classify_item("willow-ideas-003", 3, text, gitlog)
    assert v.status == LANDED
    assert v.evidence_kind == EXPLICIT


def test_inferred_via_idea_id_trailer():
    commits = (Commit(sha="b" * 40, subject="feat: build the thing",
                      body="Idea-Id: willow-ideas-010\n"),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    text = "an idea with no legend tag at all"
    v = classify_item("willow-ideas-010", 10, text, gitlog)
    assert v.status == LANDED
    assert v.evidence_kind == INFERRED
    assert "Idea-Id" in v.evidence


def test_inferred_via_pr_number_named_in_item_text():
    commits = (Commit(sha="c" * 40, subject="fix: ship the feature (#456)", body=""),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    text = "an idea that references (#456) directly"
    v = classify_item("willow-ideas-011", 11, text, gitlog)
    assert v.status == LANDED
    assert v.evidence_kind == INFERRED
    assert "#456" in v.evidence


def test_pr_number_in_item_text_with_no_matching_commit_falls_through():
    gitlog = GitLog(repo_path="/x", commits=(Commit(sha="d" * 40, subject="unrelated", body=""),),
                    available=True)
    text = "an idea that references (#999) but nothing in git names it"
    v = classify_item("willow-ideas-012", 12, text, gitlog)
    assert v.status == NOT_STARTED
    assert v.evidence_kind == NONE_KIND


def test_inferred_via_strong_backtick_token():
    commits = (Commit(sha="e" * 40, subject="add friction_floor module", body=""),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    text = "wire in `friction_floor` detection"
    v = classify_item("willow-ideas-013", 13, text, gitlog)
    assert v.status == LANDED
    assert v.evidence_kind == INFERRED
    assert "friction_floor" in v.evidence


def test_short_backtick_token_is_not_strong_evidence():
    """A short identifier (below the length floor) must not match by
    accident — see gitevidence._MIN_TOKEN_LEN."""
    commits = (Commit(sha="f" * 40, subject="db migration for something else", body=""),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    text = "touches the `db` layer"
    v = classify_item("willow-ideas-014", 14, text, gitlog)
    assert v.status == NOT_STARTED


def test_no_evidence_is_not_started_with_none_kind():
    text = "just an idea, no tag, no backticks, no PR number"
    v = classify_item("willow-ideas-015", 15, text, EMPTY_GITLOG)
    assert v.status == NOT_STARTED
    assert v.evidence_kind == NONE_KIND
    assert "no evidence" in v.evidence.lower()
    assert "not that the idea is proven unbuilt" in v.evidence


def test_unavailable_gitlog_still_classifies_explicit_tags():
    text = "**idea** — ✅ **shipped**: done."
    v = classify_item("willow-ideas-016", 16, text, UNAVAILABLE_GITLOG)
    assert v.status == LANDED
    assert v.evidence_kind == EXPLICIT


def test_unavailable_gitlog_falls_to_not_started_and_says_so():
    text = "no tag here"
    v = classify_item("willow-ideas-017", 17, text, UNAVAILABLE_GITLOG)
    assert v.status == NOT_STARTED
    assert "git history was unavailable" in v.evidence
