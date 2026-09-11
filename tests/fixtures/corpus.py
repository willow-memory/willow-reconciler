"""Builds the git history that pairs with `adversarial_ideas.md`.

The doc supplies the traps; this supplies the evidence they are traps AGAINST.
Kept as a scripted build rather than a checked-in bundle so the traps are
readable as intent ("this commit exists to tempt rule 2b") instead of as an
opaque binary, and so the merge commits are real merges — two parents — which
is the whole point of several of them.

`EXPECTED` is the ground truth: what each item must classify as once the doc
and this history are put together. It is written by hand from the traps'
intent, NOT generated from the classifier, so it cannot drift into agreeing
with a regression the way the original `echo_check` did.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess

from reconciler.classify import EXPLICIT, INFERRED, LANDED, NONE_KIND, NOT_STARTED, PARTIAL

DOC_RELPATH = "docs/ideas.md"
_FIXTURE_DOC = pathlib.Path(__file__).with_name("adversarial_ideas.md")

# item num -> (status, evidence_kind). Hand-written from the doc's own text.
EXPECTED: dict[int, tuple[str, str]] = {
    1: (LANDED, EXPLICIT),
    2: (PARTIAL, EXPLICIT),
    3: (NOT_STARTED, NONE_KIND),    # joke item naming a real tool
    4: (NOT_STARTED, NONE_KIND),    # "former #103" is not a PR reference
    5: (NOT_STARTED, NONE_KIND),    # "(#42)" subject is not a squash merge
    6: (LANDED, INFERRED),          # real merge commit for PR #77
    7: (LANDED, INFERRED),          # Idea-Id trailer, merged
    8: (PARTIAL, INFERRED),         # Idea-Id + Idea-Status: partial
    9: (NOT_STARTED, NONE_KIND),    # trailer only on an abandoned branch
    10: (NOT_STARTED, NONE_KIND),   # prose em-dash before a marker
    11: (NOT_STARTED, NONE_KIND),   # marker mid-prose
    12: (LANDED, EXPLICIT),         # leading marker, no keyword
    14: (LANDED, EXPLICIT),         # tagged; also trailered, for the hold-out
}

# Items whose legend tag, once stripped, IS recoverable from real evidence.
# Everything else hand-tagged must fall to not_started — abstain, never a guess.
HOLDOUT_RECOVERABLE = {14}

# An id no item in the doc carries, so `verify` has something to catch.
DANGLING_ID = "willow-ideas-404"


def _git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _commit(repo: pathlib.Path, filename: str, message: str) -> None:
    (repo / filename).write_text(f"{filename}\n", encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "-q", "-m", message)


def build_corpus(dest: pathlib.Path) -> pathlib.Path:
    """Create the fixture repo at `dest` and return its path."""
    dest.mkdir(parents=True, exist_ok=True)
    _git_init(dest)

    (dest / "docs").mkdir(exist_ok=True)
    shutil.copyfile(_FIXTURE_DOC, dest / DOC_RELPATH)
    _git(dest, "add", DOC_RELPATH)
    _git(dest, "commit", "-q", "-m", "chore: the idea pile")

    # Trap for item 3: a real commit naming a real tool the joke item mentions.
    _commit(dest, "whoami.py", "feat: teach whoami to answer reliably")

    # Trap for item 5: the conventional-commit habit rule 2b used to misread.
    _commit(dest, "cleanup.txt", "chore: cleanup unrelated issue (#42)")

    # Trap for item 4 AND control for item 6: two REAL merges, two parents each.
    _merge_pr(dest, 103, "retired-work")
    _merge_pr(dest, 77, "real-delivery")

    # Controls for rule 2a.
    _commit(dest, "item7.py", "feat: land item 7\n\nIdea-Id: willow-ideas-007")
    _commit(dest, "item8.py",
            "feat: half-land item 8\n\nIdea-Id: willow-ideas-008\nIdea-Status: partial")
    _commit(dest, "item14.py", "feat: land item 14\n\nIdea-Id: willow-ideas-014")

    # For `verify`: a trailer naming an item the doc does not contain.
    _commit(dest, "dangling.txt", f"chore: typo'd key\n\nIdea-Id: {DANGLING_ID}")

    # Trap for item 9: a trailer on work deliberately never merged. Built LAST
    # so the branch stays unmerged, and left behind as a live ref — the whole
    # point is that a ref exists and must still not count.
    _git(dest, "checkout", "-q", "-b", "abandoned")
    _commit(dest, "item9.py", "feat: rejected approach\n\nIdea-Id: willow-ideas-009")
    _git(dest, "checkout", "-q", "-")
    return dest


def _git_init(repo: pathlib.Path) -> None:
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "fixture@example.com")
    _git(repo, "config", "user.name", "Fixture")
    # The corpus must not inherit a developer's own hooks or template dir.
    _git(repo, "config", "core.hooksPath", "/dev/null")


def _merge_pr(repo: pathlib.Path, pr_num: int, slug: str) -> None:
    """A genuine merge commit: GitHub's subject AND two parents."""
    _git(repo, "checkout", "-q", "-b", slug)
    _commit(repo, f"{slug}.py", f"feat: work for {slug}")
    _git(repo, "checkout", "-q", "-")
    _git(repo, "merge", "--no-ff", "-q", "-m",
         f"Merge pull request #{pr_num} from fixture/{slug}", slug)
