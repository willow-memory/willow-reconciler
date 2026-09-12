import subprocess

import pytest

from reconciler.gitevidence import GitLog
from reconciler.parse import parse_doc
from reconciler.verify import verify_trailers

DOC = "1. first idea\n2. second idea\n"


def _run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo_factory(tmp_path):
    def make(commit_messages):
        repo = tmp_path / "repo"
        repo.mkdir()
        _run(["git", "init", "-q"], repo)
        _run(["git", "config", "user.email", "test@example.com"], repo)
        _run(["git", "config", "user.name", "Test"], repo)
        for i, msg in enumerate(commit_messages):
            (repo / f"f{i}.txt").write_text(f"{i}\n")
            _run(["git", "add", f"f{i}.txt"], repo)
            _run(["git", "commit", "-q", "-m", msg], repo)
        return repo

    return make


def _verify(repo):
    items, _ = parse_doc(DOC)
    return verify_trailers("docs/ideas.md", "repo", items, GitLog.load(str(repo)))


def test_no_trailers_is_not_a_failure(repo_factory):
    """The convention is prospective — a history predating it is expected."""
    result = _verify(repo_factory(["chore: scaffold"]))
    assert result["ok"] is True
    assert result["n"] == 0
    assert "nothing is wrong" in result["headline"]


def test_a_resolving_trailer_is_reported_ok(repo_factory):
    result = _verify(repo_factory(["feat: thing\n\nIdea-Id: willow-ideas-001"]))
    assert result["ok"] is True
    assert result["n_resolved"] == 1
    assert result["unresolved"] == []
    assert result["distinct_items_covered"] == ["willow-ideas-001"]


def test_a_trailer_naming_a_missing_item_fails(repo_factory):
    """The typo case: `-24` never resolves, but rule 2a would still rank it as
    the strongest evidence the classifier has."""
    result = _verify(repo_factory(["feat: thing\n\nIdea-Id: willow-ideas-999"]))
    assert result["ok"] is False
    assert result["n_unresolved"] == 1
    assert result["unresolved"][0]["idea_id"] == "willow-ideas-999"


def test_partial_status_is_carried_through(repo_factory):
    result = _verify(
        repo_factory(["feat: half\n\nIdea-Id: willow-ideas-002\nIdea-Status: partial"])
    )
    assert result["resolved"][0]["status"] == "partial"


def test_distinct_items_covered_deduplicates_repeat_trailers(repo_factory):
    result = _verify(
        repo_factory(
            [
                "feat: a\n\nIdea-Id: willow-ideas-001",
                "feat: b\n\nIdea-Id: willow-ideas-001",
            ]
        )
    )
    assert result["n_resolved"] == 2
    assert result["distinct_items_covered"] == ["willow-ideas-001"]


def test_unavailable_git_is_reported_not_passed(tmp_path):
    items, _ = parse_doc(DOC)
    result = verify_trailers(
        "docs/ideas.md",
        "repo",
        items,
        GitLog(repo_path=str(tmp_path), available=False, error="nope"),
    )
    assert result["ok"] is False
    assert "unavailable" in result["headline"]
