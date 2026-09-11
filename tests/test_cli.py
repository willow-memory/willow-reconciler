import json
import subprocess

import pytest

from reconciler.cli import cmd_id, cmd_install_hook, cmd_verify, run


@pytest.fixture
def tiny_repo(tmp_path):
    repo = tmp_path / "toyrepo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "ideas.md").write_text(
        "1. shipped idea — ✅ **shipped**: in `x.py`.\n"
        "2. partial idea — 🟡 **partial**: half done.\n"
        "3. bare idea with no evidence at all\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return repo


def test_run_writes_json_with_expected_counts(tiny_repo, capsys):
    rc = run(repo="toyrepo", doc="docs/ideas.md", fmt="json", do_validate=True,
             fleet_root=tiny_repo.parent)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["n"] == 3
    assert out["counts_by_status"] == {"landed": 1, "partial": 1, "not_started": 1}
    assert out["validation"]["echo_check"]["accuracy"] == 1.0
    # hold-out: stripping the tags from these two toy items leaves no real
    # (Idea-Id trailer / merged-PR) evidence in this empty toy repo, so
    # recovery is honestly 0 here too.
    assert out["validation"]["holdout"]["n_recovered"] == 0


def test_headline_splits_explicit_and_inferred_landed(tiny_repo, capsys):
    rc = run(repo="toyrepo", doc="docs/ideas.md", fmt="json", fleet_root=tiny_repo.parent)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "explicit legend tag" in out["headline"]
    assert "no reliable automatic landing signal" in out["headline"]


def test_run_unknown_repo_errors_cleanly(tmp_path, capsys):
    rc = run(repo="does-not-exist", doc="docs/ideas.md", fmt="json", fleet_root=tmp_path)
    assert rc == 2
    assert "error:" in capsys.readouterr().err


def test_run_never_mutates_the_doc(tiny_repo):
    path = tiny_repo / "docs" / "ideas.md"
    before = path.read_bytes()
    run(repo="toyrepo", doc="docs/ideas.md", fmt="json", fleet_root=tiny_repo.parent)
    assert path.read_bytes() == before


# --- the write-side verbs -------------------------------------------------

def test_id_prints_only_the_trailer_on_stdout(tiny_repo, capsys):
    """stdout has to pipe straight into a commit message, so the item it
    resolved to goes to stderr."""
    rc = cmd_id(repo="toyrepo", doc="docs/ideas.md", num=2, grep=None,
                fleet_root=tiny_repo.parent)
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip() == "Idea-Id: willow-ideas-002"
    assert "partial idea" in captured.err


def test_id_by_grep_resolves_a_unique_match(tiny_repo, capsys):
    rc = cmd_id(repo="toyrepo", doc="docs/ideas.md", num=None, grep="bare idea",
                fleet_root=tiny_repo.parent)
    assert rc == 0
    assert capsys.readouterr().out.strip() == "Idea-Id: willow-ideas-003"


def test_id_refuses_an_ambiguous_grep_rather_than_guessing(tiny_repo, capsys):
    rc = cmd_id(repo="toyrepo", doc="docs/ideas.md", num=None, grep="idea",
                fleet_root=tiny_repo.parent)
    assert rc == 1
    err = capsys.readouterr().err
    assert "matches 3 items" in err
    assert "Idea-Id" not in err


def test_id_on_a_missing_item_errors(tiny_repo, capsys):
    rc = cmd_id(repo="toyrepo", doc="docs/ideas.md", num=99, grep=None,
                fleet_root=tiny_repo.parent)
    assert rc == 1
    assert "no item" in capsys.readouterr().err


def test_id_partial_emits_a_status_trailer(tiny_repo, capsys):
    rc = cmd_id(repo="toyrepo", doc="docs/ideas.md", num=1, grep=None, status="partial",
                fleet_root=tiny_repo.parent)
    assert rc == 0
    assert capsys.readouterr().out.strip().endswith("Idea-Status: partial")


def test_verify_passes_on_a_history_with_no_trailers(tiny_repo, capsys):
    rc = cmd_verify(repo="toyrepo", doc="docs/ideas.md", fmt="json",
                    fleet_root=tiny_repo.parent)
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["n"] == 0


def test_verify_exits_nonzero_on_a_dangling_trailer(tiny_repo, capsys):
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tiny_repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tiny_repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tiny_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: x\n\nIdea-Id: willow-ideas-404"],
                   cwd=tiny_repo, check=True)
    rc = cmd_verify(repo="toyrepo", doc="docs/ideas.md", fmt="json",
                    fleet_root=tiny_repo.parent)
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["unresolved"][0]["idea_id"] == "willow-ideas-404"


def test_install_hook_writes_into_the_named_repo(tiny_repo, capsys):
    rc = cmd_install_hook(repo="toyrepo", fleet_root=tiny_repo.parent)
    assert rc == 0
    assert (tiny_repo / ".git" / "hooks" / "commit-msg").exists()
    assert "installed" in capsys.readouterr().out


def test_install_hook_on_a_missing_repo_errors_cleanly(tmp_path, capsys):
    rc = cmd_install_hook(repo="does-not-exist", fleet_root=tmp_path)
    assert rc == 2
    assert "error:" in capsys.readouterr().err
