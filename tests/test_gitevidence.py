import subprocess

import pytest

from reconciler.gitevidence import GitLog


def _run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def tiny_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)
    (repo / "f.txt").write_text("one\n")
    _run(["git", "add", "f.txt"], repo)
    _run(["git", "commit", "-q", "-m", "feat: build friction_floor (#77)\n\n"
                                       "Idea-Id: willow-ideas-066\n"], repo)
    return repo


def test_load_reads_commit_with_trailer_and_pr(tiny_repo):
    gitlog = GitLog.load(str(tiny_repo))
    assert gitlog.available
    assert len(gitlog.commits) == 1
    c = gitlog.find_idea_trailer("willow-ideas-066")
    assert c is not None
    assert "friction_floor" in c.subject


def test_find_pr_reference(tiny_repo):
    gitlog = GitLog.load(str(tiny_repo))
    assert gitlog.find_pr_reference(77) is not None
    assert gitlog.find_pr_reference(9999) is None


def test_find_token_match_whole_word_only(tiny_repo):
    gitlog = GitLog.load(str(tiny_repo))
    hit = gitlog.find_token_match(("friction_floor",))
    assert hit is not None
    c, token = hit
    assert token == "friction_floor"
    # a token that is a substring of a real word but not a whole word must not match
    assert gitlog.find_token_match(("riction_flo",)) is None


def test_never_mutates_the_repo(tiny_repo):
    before = subprocess.run(["git", "status", "--porcelain"], cwd=tiny_repo,
                            capture_output=True, text=True, check=True).stdout
    GitLog.load(str(tiny_repo))
    after = subprocess.run(["git", "status", "--porcelain"], cwd=tiny_repo,
                           capture_output=True, text=True, check=True).stdout
    assert before == after == ""


def test_unavailable_on_non_git_directory(tmp_path):
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    gitlog = GitLog.load(str(not_a_repo))
    assert gitlog.available is False
    assert gitlog.error
