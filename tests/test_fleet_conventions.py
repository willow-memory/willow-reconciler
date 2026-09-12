"""This repo's own tree, held to the fleet's published convention set.

Fleet plan decision 4: every repo carries this file, and the rules it checks
have ONE home — `reconciler.conventions`, which `reconciler conventions
--json` publishes. Nothing here restates a rule: the required files, the
hidden-type set and the required config comments are all *read* from the
published document, so a fleet-wide change to a rule reaches this test by
changing the one place it lives. Sibling repos consume the same document
from an installed `willow-reconciler` rather than from this import.

Every scan is planted in this same file: a helper that reads a tree and
reports on it is shown to report on a tree built to violate it (see
`tests/test_scans_fire.py` for the rule that requires this).
"""

from __future__ import annotations

import json
from pathlib import Path

from reconciler.conventions import conventions

REPO_ROOT = Path(__file__).resolve().parents[1]
RULES = conventions()

RELEASE_PLEASE = ".github/workflows/release-please.yml"
RELEASE_CONFIG = "release-please-config.json"
CONTRIBUTING = "CONTRIBUTING.md"
PILE = "docs/ideas.md"

#: The `gh` invocation that arms auto-merge on the release PR — matched as
#: text; the arming is one line and this is its spelling.
ARMS_AUTOMERGE = "gh pr merge --auto"

#: The one test command this repo's CONTRIBUTING must name — the exact
#: string the PR template's Evidence line quotes.
TEST_COMMAND = "python -m pytest tests/ -q"


def _arms_automerge(root: Path) -> bool:
    workflow = root / RELEASE_PLEASE
    return workflow.exists() and ARMS_AUTOMERGE in workflow.read_text(encoding="utf-8")


def _missing_when_armed(root: Path, required: list[str]) -> list[str]:
    """Of `required` (the published `required_when_release_please_arms_automerge`),
    the files absent from a tree that arms auto-merge. Empty for a tree that
    does not arm it: a release PR merged by hand has a reader."""
    if not _arms_automerge(root):
        return []
    return [f for f in required if not (root / f).exists()]


def _config_hidden_types(config_text: str) -> set[str]:
    sections = json.loads(config_text)["packages"]["."]["changelog-sections"]
    return {s["type"] for s in sections if s.get("hidden")}


def _config_missing_comments(config_text: str, required: list[str]) -> list[str]:
    package = json.loads(config_text)["packages"]["."]
    return [c for c in required if c not in package]


def _missing_when_pile_exists(root: Path, required: list[str]) -> list[str]:
    """Of `required` (the published `required_when_pile_exists`), the files
    absent from a tree that keeps a numbered pile at `docs/ideas.md`."""
    if not (root / PILE).exists():
        return []
    return [f for f in required if not (root / f).exists()]


def _names_test_command(contributing_text: str) -> bool:
    return TEST_COMMAND in contributing_text


# ── the real tree ───────────────────────────────────────────────────────────


def test_pr_title_guard_is_present_wherever_automerge_is_armed():
    assert _arms_automerge(REPO_ROOT), (
        f"{RELEASE_PLEASE} is expected to arm auto-merge; if that changed on purpose "
        "the fleet convention needs to know"
    )
    assert (
        _missing_when_armed(
            REPO_ROOT, RULES["required_when_release_please_arms_automerge"]
        )
        == []
    )


def test_the_configs_hidden_set_equals_the_published_set():
    text = (REPO_ROOT / RELEASE_CONFIG).read_text(encoding="utf-8")
    assert _config_hidden_types(text) == set(RULES["hidden_types"])


def test_the_config_carries_every_required_reasoning_comment():
    text = (REPO_ROOT / RELEASE_CONFIG).read_text(encoding="utf-8")
    assert _config_missing_comments(text, RULES["required_config_comments"]) == []
    assert "$comment-hidden-rule" in RULES["required_config_comments"]


def test_contributing_names_the_test_command():
    assert RULES["contributing_must_name_test_command"] is True
    assert _names_test_command((REPO_ROOT / CONTRIBUTING).read_text(encoding="utf-8"))


def test_trailers_workflow_is_present_because_a_pile_exists():
    assert (REPO_ROOT / PILE).exists(), "this repo keeps its pile at docs/ideas.md"
    assert (
        _missing_when_pile_exists(REPO_ROOT, RULES["required_when_pile_exists"]) == []
    )


# ── the plants ──────────────────────────────────────────────────────────────


def _tree(
    tmp_path: Path, label: str, *, arms: bool, files: tuple[str, ...] = ()
) -> Path:
    root = tmp_path / label
    (root / ".github" / "workflows").mkdir(parents=True)
    body = "jobs:\n  release-please:\n    steps:\n      - run: |\n"
    body += f'          {ARMS_AUTOMERGE} "$pr"\n' if arms else "          gh pr list\n"
    (root / RELEASE_PLEASE).write_text(body, encoding="utf-8")
    for f in files:
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_text("# planted\n", encoding="utf-8")
    return root


def test_the_armed_tree_check_fires_on_a_planted_tree_missing_the_guard(tmp_path):
    """Planted: a tree that arms auto-merge and carries none of the published
    required files — the state every repo in the fleet was in before Wave 2."""
    required = RULES["required_when_release_please_arms_automerge"]
    assert _missing_when_armed(_tree(tmp_path, "bare", arms=True), required) == required
    assert (
        _missing_when_armed(
            _tree(tmp_path, "guarded", arms=True, files=tuple(required)), required
        )
        == []
    )
    assert _missing_when_armed(_tree(tmp_path, "manual", arms=False), required) == []


def test_the_hidden_set_check_catches_a_planted_config_that_unhides_ci():
    """Planted: a fixture config un-hiding `ci` (jeles v0.4.1) and dropping
    the reasoning block — both must be reported against the published set."""
    planted = json.dumps(
        {
            "packages": {
                ".": {
                    "changelog-sections": [
                        {"type": "feat", "section": "Added"},
                        {"type": "docs", "section": "Docs", "hidden": True},
                        {"type": "test", "section": "Tests", "hidden": True},
                        {"type": "ci", "section": "CI"},
                        {"type": "chore", "section": "Chores", "hidden": True},
                    ],
                    "$comment-what-cuts-a-release": "kept",
                }
            }
        }
    )
    assert _config_hidden_types(planted) == {"chore", "docs", "test"}
    assert _config_hidden_types(planted) != set(RULES["hidden_types"])
    assert _config_missing_comments(planted, RULES["required_config_comments"]) == [
        "$comment-hidden-rule"
    ]


def test_the_pile_check_fires_on_a_planted_tree_with_a_pile_and_no_verify_gate(
    tmp_path,
):
    """Planted: a repo that keeps a numbered pile but never runs `reconciler
    verify` in CI — the shape in which a dangling Idea-Id is never caught."""
    required = RULES["required_when_pile_exists"]
    with_pile = _tree(tmp_path, "pile", arms=False, files=(PILE,))
    assert _missing_when_pile_exists(with_pile, required) == required
    gated = _tree(tmp_path, "gated", arms=False, files=(PILE, *required))
    assert _missing_when_pile_exists(gated, required) == []
    assert (
        _missing_when_pile_exists(_tree(tmp_path, "nopile", arms=False), required) == []
    )


def test_the_contributing_check_catches_a_planted_contributing_without_the_command():
    """Planted: a CONTRIBUTING that says to run the tests without naming the
    command — nothing for a PR's Evidence line to quote."""
    assert not _names_test_command("# Contributing\n\nRun the tests before pushing.\n")
    assert _names_test_command(f"```sh\n{TEST_COMMAND}\n```\n")
