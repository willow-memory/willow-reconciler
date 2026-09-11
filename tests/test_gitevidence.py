import subprocess

import pytest

from reconciler.gitevidence import GitLog


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


def test_idea_trailer_defaults_to_landed(repo_factory):
    repo = repo_factory(["feat: build the thing\n\nIdea-Id: willow-ideas-010\n"])
    gitlog = GitLog.load(str(repo))
    hit = gitlog.find_idea_trailer("willow-ideas-010")
    assert hit is not None
    c, status = hit
    assert status == "landed"


def test_idea_trailer_honors_idea_status_partial(repo_factory):
    """The inferred tier's route to PARTIAL: a same-commit Idea-Status
    trailer overrides the landed default."""
    repo = repo_factory(["feat: half-build the thing\n\n"
                         "Idea-Id: willow-ideas-011\nIdea-Status: partial\n"])
    gitlog = GitLog.load(str(repo))
    hit = gitlog.find_idea_trailer("willow-ideas-011")
    assert hit is not None
    _, status = hit
    assert status == "partial"


def test_find_merged_pr_via_merge_commit(repo_factory):
    repo = repo_factory(["Merge pull request #77 from someone/branch"])
    gitlog = GitLog.load(str(repo))
    assert gitlog.find_merged_pr(77) is not None
    assert gitlog.find_merged_pr(78) is None


def test_find_merged_pr_via_squash_merge_title(repo_factory):
    repo = repo_factory(["feat: ship the widget (#88)"])
    gitlog = GitLog.load(str(repo))
    assert gitlog.find_merged_pr(88) is not None


def test_find_merged_pr_does_not_match_body_only_mention(repo_factory):
    """A '#123' in the commit BODY (e.g. 'fixes #123', an issue reference)
    is not proof of a merge — only the subject shapes GitHub itself writes
    for an actual merge count."""
    repo = repo_factory(["fix: unrelated bug\n\nfixes #123 as reported"])
    gitlog = GitLog.load(str(repo))
    assert gitlog.find_merged_pr(123) is None


def test_never_mutates_the_repo(repo_factory):
    repo = repo_factory(["feat: build friction_floor (#77)\n\nIdea-Id: willow-ideas-066\n"])
    before = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                            capture_output=True, text=True, check=True).stdout
    GitLog.load(str(repo))
    after = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                           capture_output=True, text=True, check=True).stdout
    assert before == after == ""


def test_unavailable_on_non_git_directory(tmp_path):
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    gitlog = GitLog.load(str(not_a_repo))
    assert gitlog.available is False
    assert gitlog.error


def test_all_idea_trailers_reports_what_the_commits_claim(repo_factory):
    """The inverse of find_idea_trailer: not "does this item have evidence?"
    but "what do the commits say?" — which is what catches a dangling key."""
    repo = repo_factory([
        "chore: no trailer here",
        "feat: a\n\nIdea-Id: willow-ideas-001",
        "feat: b\n\nIdea-Id: willow-ideas-002\nIdea-Status: partial",
    ])
    found = GitLog.load(str(repo)).all_idea_trailers()
    assert {(ident, status) for _, ident, status in found} == {
        ("willow-ideas-001", "landed"),
        ("willow-ideas-002", "partial"),
    }


def test_all_idea_trailers_is_empty_on_a_history_predating_the_convention(repo_factory):
    assert GitLog.load(str(repo_factory(["chore: scaffold"]))).all_idea_trailers() == []


def test_a_commit_landing_several_ideas_registers_every_trailer(repo_factory):
    """One commit, several trailers — `search` would have seen only the first
    and silently cost every later id its strongest evidence."""
    repo = repo_factory([
        "feat: the write-side loop\n\n"
        "Idea-Id: willow-ideas-001\nIdea-Id: willow-ideas-002\nIdea-Id: willow-ideas-003"
    ])
    log = GitLog.load(str(repo))
    assert len(log.all_idea_trailers()) == 3
    for n in ("001", "002", "003"):
        assert log.find_idea_trailer(f"willow-ideas-{n}") is not None
