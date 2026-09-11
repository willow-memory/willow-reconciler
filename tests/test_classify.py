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
    RULE_MERGED_PR_MENTION,
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
    commits = (Commit(sha="c" * 40, subject="Merge pull request #456 from x/y",
                      body="", parents=("a" * 40, "b" * 40)),)
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


# --- legend-tag anchoring -------------------------------------------------
# A marker mid-prose is a MENTION, not a tag. Regression guard for the
# over-claim found by running the reconciler against its own docs/ideas.md:
# an item merely *discussing* legend tags classified LANDED/explicit.

def test_shipped_marker_mid_prose_is_not_a_tag():
    text = "`reconciler annotate` — propose ✅/🟡 legend tags back into the doc."
    v = classify_item("willow-ideas-016", 16, text, EMPTY_GITLOG)
    assert v.status == NOT_STARTED
    assert v.evidence_kind == NONE_KIND


def test_partial_marker_mid_prose_is_not_a_tag():
    text = "the legend uses 🟡 for partially landed items, which is fine"
    v = classify_item("willow-ideas-025", 25, text, EMPTY_GITLOG)
    assert v.status == NOT_STARTED
    assert v.evidence_kind == NONE_KIND


def test_tag_leading_the_item_text_is_a_tag():
    v = classify_item("willow-ideas-026", 26, "✅ shipped in v0.1.0", EMPTY_GITLOG)
    assert v.status == LANDED
    assert v.evidence_kind == EXPLICIT


def test_tag_after_a_double_hyphen_separator_is_a_tag():
    v = classify_item("willow-ideas-027", 27, "an idea -- 🟡 **partial**", EMPTY_GITLOG)
    assert v.status == PARTIAL
    assert v.evidence_kind == EXPLICIT


def test_evidence_text_excludes_the_separator():
    """Group 1 is the marker onward, so anchoring did not change what a
    reader is shown as the evidence for an explicit verdict."""
    v = classify_item("willow-ideas-028", 28, "an idea — ✅ **shipped**: in `x.py`.",
                      EMPTY_GITLOG)
    assert v.evidence == "✅ **shipped**: in `x.py`."


def test_a_conventional_commit_naming_an_issue_is_not_a_merged_pr():
    """Finding #2 of the post-write-side audit: a subject ending "(#42)" is the
    ordinary habit of naming an issue, not GitHub's squash-merge record. It
    asserted LANDED for any item naming PR #42 — a reproducible false LANDED."""
    commits = (Commit(sha="a" * 40, subject="chore: cleanup unrelated issue (#42)",
                      body="not a PR merge"),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    v = classify_item("willow-ideas-042", 42, "waiting on PR #42 to land", gitlog)
    assert v.status == NOT_STARTED
    assert v.evidence_kind == NONE_KIND


# --- legend keyword requirement (post-write-side audit, finding #5) --------

def test_an_ordinary_prose_em_dash_before_a_marker_is_not_a_tag():
    """Anchoring alone was not enough: ordinary sentences use em-dashes too."""
    text = "This discusses history — ✅ marks were abused before, so audit them."
    v = classify_item("willow-ideas-030", 30, text, EMPTY_GITLOG)
    assert v.status == NOT_STARTED
    assert v.evidence_kind == NONE_KIND


def test_a_marker_whose_keyword_is_buried_in_prose_is_not_a_tag():
    text = "a 🟡 mention — but partial is just a word here"
    v = classify_item("willow-ideas-031", 31, text, EMPTY_GITLOG)
    assert v.status == NOT_STARTED


def test_a_dash_clause_naming_its_legend_keyword_is_a_tag():
    v = classify_item("willow-ideas-032", 32, "an idea — ✅ **shipped**: in `x.py`.",
                      EMPTY_GITLOG)
    assert v.status == LANDED
    assert v.evidence_kind == EXPLICIT


def test_a_leading_marker_needs_no_keyword():
    """Leading position is unambiguous on its own — nothing precedes it to
    make it read as prose."""
    v = classify_item("willow-ideas-033", 33, "✅ done, no keyword", EMPTY_GITLOG)
    assert v.status == LANDED


def test_a_tag_with_no_space_before_the_dash_is_still_found():
    """The companion false-negative the audit flagged: a missed tag silently
    costs `validate.py`'s hold-out an item of ground truth."""
    v = classify_item("willow-ideas-034", 34, "an idea–✅ shipped in v0.1.0", EMPTY_GITLOG)
    assert v.status == LANDED


# --- rule provenance (Task 2: additive reporting, no behaviour change) -----
# Identifiers must match the module docstring's numbering exactly: 1 (explicit
# tag), 2a (Idea-Id trailer), 2b (merged-PR mention), 3 (abstain).

def test_rule_1_on_an_explicit_tag():
    v = classify_item("willow-ideas-001", 1, "✅ shipped in v0.1.0", EMPTY_GITLOG)
    assert v.rule == RULE_EXPLICIT_TAG == "1"


def test_rule_2a_on_an_idea_id_trailer():
    commits = (Commit(sha="b" * 40, subject="feat: build the thing",
                      body="Idea-Id: willow-ideas-010\n"),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    v = classify_item("willow-ideas-010", 10, "no tag here", gitlog)
    assert v.rule == RULE_IDEA_ID_TRAILER == "2a"


def test_rule_2b_on_a_merged_pr_mention():
    commits = (Commit(sha="c" * 40, subject="Merge pull request #456 from x/y",
                      body="", parents=("a" * 40, "b" * 40)),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    v = classify_item("willow-ideas-011", 11, "names PR #456 directly", gitlog)
    assert v.rule == RULE_MERGED_PR_MENTION == "2b"


def test_rule_3_on_abstain():
    v = classify_item("willow-ideas-015", 15, "just an idea, no signal", EMPTY_GITLOG)
    assert v.rule == RULE_ABSTAIN == "3"


def test_explicit_tag_wins_over_inferred_evidence_and_reports_rule_1():
    """rule 1 still outranks rule 2, and now visibly says so."""
    commits = (Commit(sha="a" * 40, subject="feat", body="Idea-Id: willow-ideas-003"),)
    gitlog = GitLog(repo_path="/x", commits=commits, available=True)
    v = classify_item("willow-ideas-003", 3, "**idea** — ✅ **shipped**: done.", gitlog)
    assert v.rule == RULE_EXPLICIT_TAG


def test_rule_provenance_is_additive_only_status_and_kind_unchanged():
    """This is the behaviour-preservation proof: for a fixed battery of
    inputs spanning every branch of the rule stack, adding `rule` must not
    move `status` or `evidence_kind` — only add information alongside them."""
    idea_trailer_gitlog = GitLog(
        repo_path="/x",
        commits=(Commit(sha="b" * 40, subject="feat: build the thing",
                        body="Idea-Id: willow-ideas-010\n"),),
        available=True)
    merged_pr_gitlog = GitLog(
        repo_path="/x",
        commits=(Commit(sha="c" * 40, subject="Merge pull request #456 from x/y",
                        body="", parents=("a" * 40, "b" * 40)),),
        available=True)

    cases = [
        ("willow-ideas-001", "✅ shipped in v0.1.0", EMPTY_GITLOG,
         LANDED, EXPLICIT, RULE_EXPLICIT_TAG),
        ("willow-ideas-002", "🟡 **partial**: half done", EMPTY_GITLOG,
         PARTIAL, EXPLICIT, RULE_EXPLICIT_TAG),
        ("willow-ideas-010", "no tag here", idea_trailer_gitlog,
         LANDED, INFERRED, RULE_IDEA_ID_TRAILER),
        ("willow-ideas-011", "names PR #456 directly", merged_pr_gitlog,
         LANDED, INFERRED, RULE_MERGED_PR_MENTION),
        ("willow-ideas-015", "just an idea, no signal", EMPTY_GITLOG,
         NOT_STARTED, NONE_KIND, RULE_ABSTAIN),
    ]
    for num, (idea_id, text, gitlog, expected_status, expected_kind,
             expected_rule) in enumerate(cases):
        v = classify_item(idea_id, num, text, gitlog)
        assert v.status == expected_status, text
        assert v.evidence_kind == expected_kind, text
        assert v.rule == expected_rule, text
