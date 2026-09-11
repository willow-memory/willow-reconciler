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
    commits = (Commit(sha="a" * 40, subject="feat", body="Idea-Id: willow-ideas-003"),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    text = "**idea** — ✅ **shipped**: done."
    v = classify_item("willow-ideas-003", 3, text, gitlog)
    assert v.status == LANDED
    assert v.evidence_kind == EXPLICIT


def test_inferred_via_idea_id_trailer_defaults_landed():
    commits = (Commit(sha="b" * 40, subject="feat: build the thing",
                      body="Idea-Id: willow-ideas-010\n"),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    text = "an idea with no legend tag at all"
    v = classify_item("willow-ideas-010", 10, text, gitlog)
    assert v.status == LANDED
    assert v.evidence_kind == INFERRED
    assert "Idea-Id" in v.evidence


def test_inferred_tier_can_emit_partial_not_just_landed():
    """Structural requirement: the inferred tier must be able to represent
    PARTIAL, not force LANDED on every hit."""
    commits = (Commit(sha="p" * 40, subject="feat: half-build the thing",
                      body="Idea-Id: willow-ideas-020\nIdea-Status: partial\n"),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    v = classify_item("willow-ideas-020", 20, "no tag here", gitlog)
    assert v.status == PARTIAL
    assert v.evidence_kind == INFERRED


def test_inferred_via_pr_mention_that_resolves_to_a_merged_pr():
    commits = (Commit(sha="c" * 40, subject="feat: ship the feature (#456)", body=""),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    text = "an idea that names PR #456 directly"
    v = classify_item("willow-ideas-011", 11, text, gitlog)
    assert v.status == LANDED
    assert v.evidence_kind == INFERRED
    assert "#456" in v.evidence


def test_pr_mention_with_no_matching_merged_commit_abstains():
    gitlog = GitLog(repo_path="/x", commits=(Commit(sha="d" * 40, subject="unrelated", body=""),),
                    available=True)
    text = "an idea that names PR #999 but nothing in git merges it"
    v = classify_item("willow-ideas-012", 12, text, gitlog)
    assert v.status == NOT_STARTED
    assert v.evidence_kind == NONE_KIND


def test_bare_hash_number_is_never_treated_as_a_pr_reference():
    """A bare '#123' with no 'PR'/'pull request' context — e.g. an
    idea-number cross-reference like 'folds in former #103' — must NOT be
    treated as a PR mention, even if a commit with that exact number exists.
    This is the fix for audit finding #3c (idea-number/PR-number conflation)."""
    commits = (Commit(sha="e" * 40, subject="Merge pull request #103 from x/y", body=""),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    text = "folds in former #103, a retired duplicate idea"
    v = classify_item("willow-ideas-018", 18, text, gitlog)
    assert v.status == NOT_STARTED
    assert v.evidence_kind == NONE_KIND


def test_bare_backtick_identifier_is_never_evidence_on_its_own():
    """The removed rule 2c: a bare code identifier mentioned in the item
    text must never, by itself, produce a LANDED verdict — see
    gitevidence.py's module docstring for why (chaos-canon false positives)."""
    commits = (Commit(sha="f" * 40, subject="add friction_floor module", body=""),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    text = "a joke idea that happens to mention `friction_floor`"
    v = classify_item("willow-ideas-014", 14, text, gitlog)
    assert v.status == NOT_STARTED
    assert v.evidence_kind == NONE_KIND


def test_no_evidence_is_not_started_with_none_kind():
    text = "just an idea, no tag, no PR mention"
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
