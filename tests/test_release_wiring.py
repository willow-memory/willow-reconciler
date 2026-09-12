"""G2-pr-title-reconciler — the release wiring, checked rather than trusted.

`release-please.yml` here arms auto-merge on the release PR, so whatever
release-please decides is releasable ships to PyPI unattended. Two things
decide that, and neither is code anyone runs locally:

* the PR *title* — this repo merges with merge commits, GitHub writes the
  title into the merge commit body, and release-please parses it alongside
  the commits (willow-mcp v2.1.1 was cut for CI-only changes exactly this
  way). `.github/workflows/pr-title.yml` is the guard, and (a) below says it
  must exist wherever auto-merge is armed;
* the `PACKAGED` constant inside that guard — the one thing in the file that
  must differ per repo. A copied value would clear every "nothing installable
  changed" check silently, so (b) below reads it back out of the workflow and
  holds it to pyproject's own packaged directory;
* the hidden-type set in `release-please-config.json` — an un-hidden type
  cuts a release on its own (jeles v0.4.1, one `ci:` commit). (c) below pins
  the set and requires the recorded reasoning (`$comment-hidden-rule`) to sit
  beside it, so the setting cannot drift from the explanation.

Every scan here is planted: a helper that reads a tree and reports on it is
shown, in this same file, to report on a tree built to violate it. A scan
that has never fired has not been shown to check anything.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

RELEASE_PLEASE = ".github/workflows/release-please.yml"
PR_TITLE_GUARD = ".github/workflows/pr-title.yml"
RELEASE_CONFIG = "release-please-config.json"
PYPROJECT = "pyproject.toml"

#: The line in release-please.yml that hands the release PR to GitHub to
#: merge on its own. Matched as text, not parsed as YAML (stdlib has no YAML
#: parser and this repo adds no dependencies for its tests): the arming is
#: one `gh` invocation and this is its spelling.
ARMS_AUTOMERGE = "gh pr merge --auto"

#: The four types release-please must not release on. Fixed here, not read
#: from the config, so that a config edit un-hiding one of them fails this
#: test instead of quietly redefining what "hidden" means.
EXPECTED_HIDDEN = frozenset({"chore", "ci", "docs", "test"})

_WORKFLOW_PACKAGED = re.compile(r"^\s*PACKAGED\s*=\s*\((.*?)\)\s*$", re.MULTILINE)
_PYPROJECT_PACKAGES = re.compile(
    r"^\[tool\.hatch\.build\.targets\.wheel\]\s*\npackages\s*=\s*\[(.*?)\]", re.MULTILINE
)


def _arms_automerge(root: Path) -> bool:
    """True if this tree's release-please workflow arms auto-merge on the
    release PR — the condition under which a PR title can publish to PyPI
    with nobody looking."""
    workflow = root / RELEASE_PLEASE
    return workflow.exists() and ARMS_AUTOMERGE in workflow.read_text(encoding="utf-8")


def _pr_title_guard_offenders(root: Path) -> list[str]:
    """The guard files missing from a tree that arms auto-merge. Empty when
    the tree does not arm it (nothing to guard) or carries the guard."""
    if not _arms_automerge(root):
        return []
    return [PR_TITLE_GUARD] if not (root / PR_TITLE_GUARD).exists() else []


def _workflow_packaged(workflow_text: str) -> tuple[str, ...]:
    """The `PACKAGED = (...)` tuple as the workflow's inline Python spells
    it — read back as text so the test holds the *file* to pyproject, not a
    copy of the constant that could drift on its own."""
    m = _WORKFLOW_PACKAGED.search(workflow_text)
    assert m, "pr-title.yml must define PACKAGED = (...) on one line"
    return tuple(part.strip().strip("'\"") for part in m.group(1).split(",") if part.strip())


def _pyproject_packaged(pyproject_text: str) -> tuple[str, ...]:
    """The wheel's `packages = [...]` under hatch's build config. A regex,
    not `tomllib` — this repo runs on 3.10, which has none."""
    m = _PYPROJECT_PACKAGES.search(pyproject_text)
    assert m, "pyproject.toml must declare [tool.hatch.build.targets.wheel] packages = [...]"
    return tuple(part.strip().strip("'\"") for part in m.group(1).split(",") if part.strip())


def _hidden_types(config: dict) -> frozenset[str]:
    """The changelog-section types release-please will not release on."""
    sections = config["packages"]["."]["changelog-sections"]
    return frozenset(s["type"] for s in sections if s.get("hidden"))


# ── (a) the guard exists wherever auto-merge is armed ────────────────────────


def test_pr_title_guard_exists_wherever_automerge_is_armed():
    """The real tree. release-please.yml arms auto-merge here, so the PR
    title guard must be present — and if arming is ever removed, this passes
    vacuously on purpose: there is then nothing for the title to cut."""
    assert _arms_automerge(REPO_ROOT), (
        f"{RELEASE_PLEASE} is expected to arm auto-merge ({ARMS_AUTOMERGE!r}); if that "
        "changed on purpose, this docstring and the fleet convention need to know"
    )
    assert _pr_title_guard_offenders(REPO_ROOT) == []


def _tree(tmp_path: Path, *, arms: bool, guard: bool) -> Path:
    root = tmp_path / ("armed" if arms else "manual") / ("guarded" if guard else "bare")
    (root / ".github" / "workflows").mkdir(parents=True)
    body = "jobs:\n  release-please:\n    steps:\n      - run: |\n"
    body += f"          {ARMS_AUTOMERGE} \"$pr\"\n" if arms else "          gh pr list\n"
    (root / RELEASE_PLEASE).write_text(body, encoding="utf-8")
    if guard:
        (root / PR_TITLE_GUARD).write_text("name: PR title\n", encoding="utf-8")
    return root


def test_the_guard_check_fires_on_a_planted_tree_that_arms_automerge_without_it(tmp_path):
    """Planted: a tree whose release-please.yml arms auto-merge and which
    carries no pr-title.yml — the exact state this repo was in before this
    bite, and the state a fresh sibling copies into by default."""
    assert _pr_title_guard_offenders(_tree(tmp_path, arms=True, guard=False)) == [PR_TITLE_GUARD]
    assert _pr_title_guard_offenders(_tree(tmp_path, arms=True, guard=True)) == []
    assert _pr_title_guard_offenders(_tree(tmp_path, arms=False, guard=False)) == [], (
        "a tree that merges release PRs by hand has nothing to guard"
    )


# ── (b) PACKAGED agrees with pyproject ──────────────────────────────────────


def test_packaged_in_the_workflow_agrees_with_pyproject():
    """The one per-repo constant in pr-title.yml, held to the packaging
    config it stands in for. `pyproject.toml` is always in PACKAGED (a
    dependency or metadata change alters the installed artifact); the rest
    must be exactly pyproject's own wheel packages, each as a `dir/` prefix."""
    packaged = _workflow_packaged((REPO_ROOT / PR_TITLE_GUARD).read_text(encoding="utf-8"))
    packages = _pyproject_packaged((REPO_ROOT / PYPROJECT).read_text(encoding="utf-8"))
    assert PYPROJECT in packaged
    assert set(packaged) - {PYPROJECT} == {f"{pkg}/" for pkg in packages}, (
        f"pr-title.yml PACKAGED={packaged} but pyproject packages={packages}: the "
        "'nothing installable changed' check would clear or block the wrong files"
    )


def test_the_packaged_parsers_catch_a_planted_disagreement():
    """Planted: a workflow copied from a sibling (`src/kartikeya/`) beside
    this repo's pyproject. Both parsers must read their constant back out
    of the text exactly, so the comparison the real test makes is over what
    the files say, not over a hand-typed expectation."""
    copied = "          PACKAGED = (\"src/kartikeya/\", \"pyproject.toml\")\n"
    assert _workflow_packaged(copied) == ("src/kartikeya/", "pyproject.toml")
    own = "[tool.hatch.build.targets.wheel]\npackages = [\"reconciler\"]\n"
    assert _pyproject_packaged(own) == ("reconciler",)
    assert set(_workflow_packaged(copied)) - {PYPROJECT} != {
        f"{pkg}/" for pkg in _pyproject_packaged(own)
    }, "the copied constant must read as a disagreement, not be normalised away"


# ── (c) the hidden set is pinned, with its reasoning beside it ──────────────


def test_hidden_types_are_exactly_the_four_and_the_reasoning_is_recorded():
    config = json.loads((REPO_ROOT / RELEASE_CONFIG).read_text(encoding="utf-8"))
    assert _hidden_types(config) == EXPECTED_HIDDEN
    package = config["packages"]["."]
    assert "$comment-hidden-rule" in package, (
        "the hidden set must carry its own reasoning in release-please-config.json, "
        "beside the setting it explains"
    )
    assert "$comment-what-cuts-a-release" in package


def test_the_hidden_set_check_catches_a_planted_unhidden_type():
    """Planted: a config that un-hides `ci` — the exact edit that cut jeles
    v0.4.1 — must read as a different set, not as 'close enough'."""
    config = {"packages": {".": {"changelog-sections": [
        {"type": "feat", "section": "Added"},
        {"type": "docs", "section": "Docs", "hidden": True},
        {"type": "test", "section": "Tests", "hidden": True},
        {"type": "ci", "section": "CI"},
        {"type": "chore", "section": "Chores", "hidden": True},
    ]}}}
    assert _hidden_types(config) == frozenset({"chore", "docs", "test"})
    assert _hidden_types(config) != EXPECTED_HIDDEN
