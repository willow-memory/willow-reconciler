import json
import subprocess

import pytest

from reconciler.cli import run


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
    assert out["validation"]["accuracy"] == 1.0


def test_run_unknown_repo_errors_cleanly(tmp_path, capsys):
    rc = run(repo="does-not-exist", doc="docs/ideas.md", fmt="json", fleet_root=tmp_path)
    assert rc == 2
    assert "error:" in capsys.readouterr().err


def test_run_never_mutates_the_doc(tiny_repo):
    path = tiny_repo / "docs" / "ideas.md"
    before = path.read_bytes()
    run(repo="toyrepo", doc="docs/ideas.md", fmt="json", fleet_root=tiny_repo.parent)
    assert path.read_bytes() == before
