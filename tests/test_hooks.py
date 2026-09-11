"""The hooks are shell, not Python, so they are tested by actually committing
through them in a throwaway repo — a hook that reads correctly and does not
fire is the only kind of hook bug that matters."""
import subprocess

import pytest

from reconciler.hooks import MARKER, install_hooks


def _run(cmd, cwd, check=True):
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _run(["git", "init", "-q"], r)
    _run(["git", "config", "user.email", "test@example.com"], r)
    _run(["git", "config", "user.name", "Test"], r)
    return r


def _commit(repo, name, msg, check=True):
    (repo / name).write_text(name)
    _run(["git", "add", name], repo)
    return _run(["git", "commit", "-m", msg], repo, check=check)


def _last_message(repo):
    return _run(["git", "log", "-1", "--format=%B"], repo).stdout


def test_install_writes_both_hooks_executable(repo):
    result = install_hooks(repo)
    assert result["ok"] is True
    for name in ("prepare-commit-msg", "commit-msg"):
        path = repo / ".git" / "hooks" / name
        assert path.exists() and path.stat().st_mode & 0o111
        assert MARKER in path.read_text()


def test_install_refuses_to_clobber_a_foreign_hook(repo):
    path = repo / ".git" / "hooks" / "commit-msg"
    path.write_text("#!/bin/sh\n# somebody else's hook\n")
    result = install_hooks(repo)
    assert result["ok"] is False
    assert path.read_text() == "#!/bin/sh\n# somebody else's hook\n"
    assert any(r["action"] == "skipped" for r in result["results"])


def test_force_replaces_a_foreign_hook(repo):
    path = repo / ".git" / "hooks" / "commit-msg"
    path.write_text("#!/bin/sh\n# somebody else's hook\n")
    assert install_hooks(repo, force=True)["ok"] is True
    assert MARKER in path.read_text()


def test_reinstalling_over_our_own_hook_is_allowed(repo):
    install_hooks(repo)
    result = install_hooks(repo)
    assert result["ok"] is True
    assert all(r["action"] == "replaced" for r in result["results"])


def test_non_git_directory_errors_rather_than_writing(tmp_path):
    result = install_hooks(tmp_path / "nope")
    assert result["ok"] is False
    assert "no .git directory" in result["error"]


# --- prepare-commit-msg behaviour ---------------------------------------

def test_branch_naming_an_idea_gets_a_zero_padded_trailer(repo):
    install_hooks(repo)
    _run(["git", "checkout", "-qb", "feature/idea-24-anchor-tags"], repo)
    _commit(repo, "a.txt", "fix: anchor tags")
    assert "Idea-Id: willow-ideas-024" in _last_message(repo)


def test_branch_with_an_already_padded_number_is_not_double_padded(repo):
    install_hooks(repo)
    _run(["git", "checkout", "-qb", "ideas-007"], repo)
    _commit(repo, "a.txt", "feat: thing")
    assert "Idea-Id: willow-ideas-007" in _last_message(repo)


def test_branch_without_a_number_gets_nothing(repo):
    """The hook can never INVENT a link — no number in the branch, no trailer."""
    install_hooks(repo)
    _run(["git", "checkout", "-qb", "chore/repo-scaffold"], repo)
    _commit(repo, "a.txt", "chore: scaffold")
    assert "Idea-Id" not in _last_message(repo)


def test_an_author_written_trailer_is_never_overwritten(repo):
    install_hooks(repo)
    _run(["git", "checkout", "-qb", "feature/idea-7"], repo)
    _commit(repo, "a.txt", "feat: x\n\nIdea-Id: willow-ideas-099")
    msg = _last_message(repo)
    assert "willow-ideas-099" in msg
    assert "willow-ideas-007" not in msg


def test_the_trailer_joins_the_existing_trailer_block(repo):
    """interpret-trailers should keep it beside Co-Authored-By rather than
    starting a new paragraph after it."""
    install_hooks(repo)
    _run(["git", "checkout", "-qb", "idea-3"], repo)
    _commit(repo, "a.txt", "feat: x\n\nCo-Authored-By: Someone <s@example.com>")
    body = _last_message(repo)
    assert "Idea-Id: willow-ideas-003" in body
    trailing = [ln for ln in body.strip().splitlines() if ln.strip()][-2:]
    assert all(":" in ln for ln in trailing)


# --- commit-msg validation ----------------------------------------------

def test_malformed_trailer_is_rejected_and_no_commit_is_made(repo):
    install_hooks(repo)
    _run(["git", "checkout", "-qb", "main-work"], repo)
    _commit(repo, "a.txt", "chore: first")
    before = _run(["git", "rev-parse", "HEAD"], repo).stdout
    proc = _commit(repo, "b.txt", "feat: y\n\nIdea-Id: willow-ideas-7", check=False)
    assert proc.returncode == 1
    assert "malformed Idea-Id trailer" in proc.stderr
    assert _run(["git", "rev-parse", "HEAD"], repo).stdout == before


def test_malformed_status_is_rejected(repo):
    install_hooks(repo)
    _run(["git", "checkout", "-qb", "main-work"], repo)
    _commit(repo, "a.txt", "chore: first")
    proc = _commit(repo, "b.txt",
                   "feat: y\n\nIdea-Id: willow-ideas-001\nIdea-Status: mostly",
                   check=False)
    assert proc.returncode == 1
    assert "landed" in proc.stderr


def test_a_well_formed_trailer_passes_validation(repo):
    install_hooks(repo)
    _run(["git", "checkout", "-qb", "main-work"], repo)
    _commit(repo, "a.txt", "feat: y\n\nIdea-Id: willow-ideas-001\nIdea-Status: partial")
    assert "willow-ideas-001" in _last_message(repo)


# --- post-write-side audit regressions ------------------------------------

def test_a_branch_naming_two_ideas_gets_no_trailer(repo):
    """Finding #3: the old greedy sed took the LAST number, so this branch
    wrote a well-formed trailer for item 7 — a confidently wrong join key
    `verify` cannot flag, because it resolves. Never guess."""
    install_hooks(repo)
    _run(["git", "checkout", "-qb", "idea-42-followup-to-idea-7"], repo)
    proc = _commit(repo, "a.txt", "feat: land idea 42, mentions idea 7")
    assert "Idea-Id" not in _last_message(repo)
    assert "more than one idea number" in proc.stderr


def test_an_ambiguous_branch_still_lets_the_commit_through(repo):
    """Refusing to guess must not block the author — `set -e` plus a bare
    `[ ... ] && exit 0` would have aborted the commit outright."""
    install_hooks(repo)
    _run(["git", "checkout", "-qb", "idea-1-and-idea-2"], repo)
    proc = _commit(repo, "a.txt", "feat: two ideas")
    assert proc.returncode == 0


def test_a_branch_repeating_one_idea_number_is_not_ambiguous(repo):
    install_hooks(repo)
    _run(["git", "checkout", "-qb", "idea-42-rework-of-idea-42"], repo)
    _commit(repo, "a.txt", "feat: rework")
    assert "Idea-Id: willow-ideas-042" in _last_message(repo)


def test_an_idea_past_999_commits_successfully(repo):
    """Finding #4: ids.py pads to a MINIMUM of 3 digits precisely so ids stay
    correct past #999, but the validator capped at exactly 3 — making every
    item from #1000 on uncommittable through the hooks."""
    install_hooks(repo)
    _run(["git", "checkout", "-qb", "idea-1500-big-number"], repo)
    proc = _commit(repo, "a.txt", "feat: big number")
    assert proc.returncode == 0
    assert "Idea-Id: willow-ideas-1500" in _last_message(repo)


def test_hooks_are_installed_where_core_hookspath_points(repo):
    """Finding #6: the install reported success for files git would never run."""
    _run(["git", "config", "core.hooksPath", "custom-hooks"], repo)
    result = install_hooks(repo)
    assert result["ok"] is True
    assert result["hooks_dir"].endswith("custom-hooks")
    assert (repo / "custom-hooks" / "commit-msg").exists()

    _run(["git", "checkout", "-qb", "idea-88-hookspath"], repo)
    _commit(repo, "a.txt", "feat: should get a trailer")
    assert "Idea-Id: willow-ideas-088" in _last_message(repo)


def test_prose_discussing_the_convention_is_not_rejected(repo):
    """The validator read `Idea-Status:` anywhere in the message, so a commit
    EXPLAINING the convention was rejected as carrying a malformed trailer —
    this repo's own tooling blocked its own commit that way. A mention is not
    a claim, here as everywhere else."""
    install_hooks(repo)
    _run(["git", "checkout", "-qb", "docs-work"], repo)
    proc = _commit(repo, "a.txt",
                   "docs: explain the convention\n\n"
                   "Alongside them sit the controls — a resolving trailer, an\n"
                   "Idea-Status: partial — because a precision fix that simply\n"
                   "disables a rule should fail too.\n\n"
                   "Co-Authored-By: Someone <s@example.com>",
                   check=False)
    assert proc.returncode == 0, proc.stderr


def test_a_malformed_trailer_in_the_real_trailer_block_is_still_rejected(repo):
    install_hooks(repo)
    _run(["git", "checkout", "-qb", "real-work"], repo)
    _commit(repo, "a.txt", "chore: first")
    proc = _commit(repo, "b.txt",
                   "feat: y\n\nsome prose.\n\nIdea-Id: willow-ideas-7\n\n"
                   "Co-Authored-By: Someone <s@example.com>",
                   check=False)
    assert proc.returncode == 1
    assert "malformed Idea-Id trailer" in proc.stderr
