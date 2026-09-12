"""`reconciler fleet` — one table across many repos.

Builds real git repos (same technique as test_cli.py's `tiny_repo` /
test_hooks.py's `repo` fixture) rather than mocking `GitLog`, so these tests
exercise the actual `git log` path a real fleet run would."""

from __future__ import annotations

import json
import subprocess

from reconciler.benchmark import READING as BENCHMARK_READING
from reconciler.cli import cmd_fleet
from reconciler.fleet import build_fleet
from reconciler.ledger import READING as LEDGER_READING


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _init(repo):
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")


def _write_doc(repo, text):
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs" / "ideas.md").write_text(text, encoding="utf-8")


def _commit_all(repo, message):
    """Commit whatever is already on disk (a doc `_write_doc` already wrote,
    say) — never overwrites it, unlike a helper that also creates the file
    it commits."""
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _touch_and_commit(repo, message, filename):
    """Create a small placeholder file and commit it — for commits whose
    CONTENT doesn't matter, only that they exist in history (e.g. the one
    carrying an `Idea-Id` trailer)."""
    (repo / filename).write_text(filename, encoding="utf-8")
    _commit_all(repo, message)


def _repo_with_trailer(tmp_path):
    """Two items: one explicit (✅ shipped), one landed only via an
    `Idea-Id` trailer written in a commit that never touches the doc."""
    repo = tmp_path / "repo-with-trailer"
    _init(repo)
    _write_doc(
        repo,
        "1. shipped idea — ✅ **shipped**: in `x.py`.\n"
        "2. landed via a trailer, no legend tag\n",
    )
    _commit_all(repo, "chore: the idea pile")
    _touch_and_commit(
        repo, "feat: land item 2\n\nIdea-Id: willow-ideas-002", "item2.py"
    )
    return repo


def _repo_without_trailer(tmp_path):
    """One bare item, no trailer anywhere in history."""
    repo = tmp_path / "repo-without-trailer"
    _init(repo)
    _write_doc(repo, "1. a bare idea with no evidence at all\n")
    _commit_all(repo, "chore: the idea pile")
    return repo


def _repo_missing_doc(tmp_path):
    """A real repo that simply has no docs/ideas.md."""
    repo = tmp_path / "repo-missing-doc"
    _init(repo)
    _touch_and_commit(repo, "chore: init", "README.md")
    return repo


def test_two_repo_rows_have_the_expected_counts(tmp_path):
    with_trailer = _repo_with_trailer(tmp_path)
    without_trailer = _repo_without_trailer(tmp_path)

    result = build_fleet(
        [("with-trailer", with_trailer), ("without-trailer", without_trailer)],
        doc="docs/ideas.md",
    )

    assert [r["repo"] for r in result["rows"]] == ["with-trailer", "without-trailer"]

    row_a, row_b = result["rows"]
    assert row_a["doc_status"] == "ok"
    assert row_a["items_parsed"] == 2
    assert row_a["dropped"] == 0
    assert row_a["explicit_landed"] == 1
    assert row_a["explicit_partial"] == 0
    assert row_a["inferred_landed"] == 1
    assert row_a["inferred_partial"] == 0
    assert row_a["none"] == 0

    assert row_b["doc_status"] == "ok"
    assert row_b["items_parsed"] == 1
    assert row_b["explicit_landed"] == 0
    assert row_b["inferred_landed"] == 0
    assert row_b["none"] == 1

    totals = result["totals"]
    assert totals["items_parsed"] == 3
    assert totals["explicit_landed"] == 1
    assert totals["inferred_landed"] == 1
    assert totals["none"] == 1
    assert totals["repos_ok"] == 2
    assert totals["repos_doc_missing"] == 0


def test_a_missing_doc_is_a_row_not_an_error(tmp_path):
    ok_repo = _repo_with_trailer(tmp_path)
    missing = _repo_missing_doc(tmp_path)

    result = build_fleet(
        [("ok", ok_repo), ("missing-doc", missing)], doc="docs/ideas.md"
    )

    assert len(result["rows"]) == 2
    missing_row = result["rows"][1]
    assert missing_row["repo"] == "missing-doc"
    assert missing_row["doc_status"] == "missing"
    assert missing_row.get("doc_error")
    # never leaks a raw path into the reported error (failure_classes.py contract)
    assert str(missing) not in missing_row["doc_error"]

    totals = result["totals"]
    assert totals["repos_ok"] == 1
    assert totals["repos_doc_missing"] == 1
    # the missing repo contributes nothing to the pooled sums
    assert totals["items_parsed"] == 2


def test_schema_version_and_field_names_match_run_json(tmp_path):
    repo = _repo_with_trailer(tmp_path)
    result = build_fleet([("with-trailer", repo)], doc="docs/ideas.md")
    assert result["schema_version"] == 1
    row = result["rows"][0]
    # same field names `run --format json`'s ledger uses for the same counts
    assert row["items_parsed"] == 2
    assert row["dropped"] == 0
    assert "independent_recovery_rate" in row
    assert "recovery_rate" in row


def test_cmd_fleet_json_and_markdown_agree(tmp_path, capsys):
    with_trailer = _repo_with_trailer(tmp_path)
    without_trailer = _repo_without_trailer(tmp_path)
    missing = _repo_missing_doc(tmp_path)
    repos = [str(with_trailer), str(without_trailer), str(missing)]

    rc = cmd_fleet(repos, doc="docs/ideas.md", fmt="json")
    assert rc == 0
    doc = json.loads(capsys.readouterr().out)

    rc = cmd_fleet(repos, doc="docs/ideas.md", fmt="markdown")
    assert rc == 0
    md = capsys.readouterr().out

    assert str(with_trailer) in md
    assert str(without_trailer) in md
    assert str(missing) in md
    assert "doc: missing" in md

    row_a = doc["rows"][0]
    assert f"| {row_a['items_parsed']} |" in md
    assert str(doc["totals"]["items_parsed"]) in md


def test_caveat_text_is_reused_verbatim_not_paraphrased(tmp_path, capsys):
    repo = _repo_with_trailer(tmp_path)
    rc = cmd_fleet([str(repo)], doc="docs/ideas.md", fmt="markdown")
    assert rc == 0
    md = capsys.readouterr().out
    assert LEDGER_READING in md
    assert BENCHMARK_READING in md

    rc = cmd_fleet([str(repo)], doc="docs/ideas.md", fmt="json")
    assert rc == 0
    doc = json.loads(capsys.readouterr().out)
    assert LEDGER_READING in doc["reading"]
    assert BENCHMARK_READING in doc["reading"]


def test_pooled_rate_is_over_pooled_counts_not_averaged_per_repo(tmp_path):
    """A repo with 1 hand-tagged item and a repo with many must not weigh the
    same — the pooled rate is sum(recovered)/sum(hand_tagged), never a mean
    of per-repo rates."""
    repo = _repo_with_trailer(tmp_path)
    result = build_fleet([("a", repo), ("b", repo)], doc="docs/ideas.md")
    totals = result["totals"]
    expected = (
        (2 * result["rows"][0]["n_recovered_independent"])
        / (2 * result["rows"][0]["n_hand_tagged"])
        if result["rows"][0]["n_hand_tagged"]
        else None
    )
    assert totals["pooled_independent_recovery_rate"] == expected
