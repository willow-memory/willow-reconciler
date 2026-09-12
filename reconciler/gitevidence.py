"""Read-only git-log evidence for the "inferred" tier of the rule stack.

Never mutates the target repo: this module only ever calls `git log`, never
`git checkout`/`git reset`/anything that touches the worktree or refs. One
subprocess call per repo per run (`GitLog.load`), then every lookup below is
in-memory — so a doc with 100+ items costs one `git log`, not one per item.

REDESIGN NOTE (post Opus-audit rework, Slice 0): the original version of this
module also offered `find_token_match` — a bare backtick-identifier lookup
against commit text. An independent audit found that path was ~0/11 precision
on the real target doc: it fired on THE CHAOS CANON's joke items whenever
their satirical text happened to name a real tool (e.g. "whoami develops
doubt" matched a real whoami-touching commit), and separately on rule 2b's
old `find_pr_reference`, which matched ANY `#\\d+` substring — including idea
cross-references like "folds in former #103", not just real PR numbers. Both
were removed rather than tuned: a bare mention is not landing evidence, and
under-claiming (abstain) beats over-claiming (a false "landed"). What
replaces them below only asserts LANDED from evidence that resolves to
something real: an explicit author-written trailer, or a PR number that this
git history can show was actually merged.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

from .failure_classes import classify as _classify_failure

_SEP = "\x01"  # field separator inside one commit's record
_END = "\x02"  # record separator between commits

# A `Key: value` line — the shape git itself recognises as a trailer.
_TRAILER_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*:[ \t]")

_IDEA_ID_TRAILER_RE = re.compile(r"(?im)^Idea-Id:\s*(willow-ideas-\S+)\s*$")
_IDEA_STATUS_TRAILER_RE = re.compile(r"(?im)^Idea-Status:\s*(landed|partial)\s*$")

# A PR number is evidence ONLY when the item text names it as a pull request,
# not merely as a number that happens to follow '#' — an idea doc cross-
# referencing another idea ("folds in former #103", "idea #8, promoted to
# canon") uses the exact same '#123' shape a PR reference does, and the two
# must never be conflated (that conflation was finding #3c of the audit).
# Requiring the word 'PR' or 'pull request' immediately before the number is
# a real (if narrow) disambiguator: nothing in ideas.md's idea-cross-
# reference prose happens to read that way, and an author who actually meant
# a pull request has an unambiguous way to say so.
PR_MENTION_RE = re.compile(r"(?i)\b(?:PR|pull request)\s*#(\d+)\b")

# What GitHub itself writes into a commit SUBJECT when a PR is merged — the
# two shapes it produces depending on merge strategy. Matched against the
# subject only (never the free-text body, which is where an unrelated '#123'
# mention, like an issue reference, would otherwise leak in).
_MERGE_COMMIT_RE = re.compile(r"^Merge pull request #(\d+)\b")

# REMOVED (post-audit): `_SQUASH_MERGE_RE = r"\(#(\d+)\)\s*$"`, which read a
# trailing "(#N)" in a subject as GitHub's squash-merge title. That shape is
# indistinguishable from the ordinary conventional-commit habit of appending an
# issue or PR number to a normal commit subject, so an unrelated
# "chore: cleanup unrelated issue (#42)" asserted LANDED for any item naming
# "PR #42" — a reproducible false LANDED, the cardinal error. Nothing in git
# can tell a squash-merge subject from a commit that merely ends that way, so
# it is removed rather than tuned, exactly as the original audit removed
# `find_token_match`. Repos that squash-merge get their landing signal from the
# `Idea-Id` trailer (rule 2a), which is the durable key anyway.


def trailer_block(text: str) -> str:
    """The message's trailer block: the run of paragraphs at the END whose
    every line is `Key: value` shaped.

    Trailers were previously matched anywhere in the message, which made a
    commit that DISCUSSES the convention indistinguishable from one that
    CARRIES it — a commit body explaining `Idea-Status: partial`, or a revert
    quoting the original message, read as real evidence. That is the
    mention-is-not-evidence error a third time, now in the evidence layer;
    this repo's own tooling caught it by rejecting a commit whose prose
    happened to start a line that way.

    git proper counts only the final paragraph, but the convention's own
    commits put `Idea-Id` in a paragraph above the `Co-Authored-By` block, so
    that rule would discard every trailer written so far. Walking back over
    consecutive all-trailer-shaped paragraphs accepts both shapes and still
    stops dead at the first line of prose."""
    paragraphs = re.split(r"\n[ \t]*\n", text)
    kept: list[str] = []
    for para in reversed(paragraphs):
        lines = [ln for ln in para.splitlines() if ln.strip()]
        if not lines:
            continue
        if not all(_TRAILER_LINE_RE.match(ln) for ln in lines):
            break
        kept.insert(0, "\n".join(lines))
    return "\n".join(kept)


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str
    body: str
    parents: tuple[str, ...] = ()

    @property
    def is_merge(self) -> bool:
        """Two or more parents — git's own structural record that a merge
        happened, as opposed to a subject that merely looks like one."""
        return len(self.parents) >= 2

    @property
    def full_text(self) -> str:
        return f"{self.subject}\n{self.body}"

    @property
    def trailers(self) -> str:
        """Only the trailer block — what the commit CLAIMS, not what it
        mentions. Every trailer lookup reads this, never `full_text`."""
        return trailer_block(self.body)


@dataclass(frozen=True)
class GitLog:
    repo_path: str
    commits: tuple[Commit, ...] = field(default_factory=tuple)
    available: bool = True
    # A closed-vocabulary phrase from `failure_classes.FAILURE_CLASSES`, never
    # git's raw stderr or a caught exception's raw text — this field is
    # spliced into a verdict's reason (classify.py) and into verify.py's
    # headline, both of which are emitted, so it must never carry a path or
    # username git's own output happens to include.
    error: str = ""

    @classmethod
    def load(cls, repo_path: str) -> GitLog:
        """Read the full commit history of `repo_path` once. Never raises on
        a missing/non-git repo — returns `available=False` with `error` set,
        so a caller can report the gap rather than crash: an idea-doc in a
        repo with no `.git` (or git not installed) still parses and
        classifies, it just gets no inferred evidence."""
        fmt = f"%H{_SEP}%P{_SEP}%s{_SEP}%b{_END}"
        try:
            proc = subprocess.run(
                # HEAD, not --all. `--all` is reachable-from-ANY-ref, so a
                # trailer on an abandoned or rejected branch — work that was
                # deliberately never merged — resolved as LANDED, and `verify`
                # called it ok. That is a false LANDED sourced from the ref
                # scope rather than from a regex, which is the same cardinal
                # error this module was rebuilt to prevent. Evidence must be
                # reachable from the checkout being reconciled.
                ["git", "-C", repo_path, "log", f"--format={fmt}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as e:
            # `str(e)` here can carry an absolute path or, for a
            # `TimeoutExpired`, the full argv this tool invoked — read it to
            # classify, never store it: `GitLog.error` is spliced into a
            # verdict's reason and emitted (see failure_classes.py).
            return cls(
                repo_path=repo_path, available=False, error=_classify_failure(str(e))
            )
        if proc.returncode != 0:
            # A freshly-`git init`ed repo has an unborn HEAD, so `git log`
            # exits non-zero — but an empty history is a legitimate, usable
            # (if evidence-free) history, not a failure to read one. The old
            # `--all` form returned empty output with status 0 here and so
            # never hit this branch. One extra subprocess, in the failure path
            # only, tells "not a git repo" apart from "git repo, no commits".
            if cls._is_git_repo(repo_path):
                return cls(repo_path=repo_path, commits=(), available=True)
            # `proc.stderr` is git's own text and can carry an absolute path
            # (`fatal: cannot change to '/home/<user>/work/<client>/repo'`) —
            # read it to classify, never store it verbatim (see
            # failure_classes.py's module docstring for why).
            return cls(
                repo_path=repo_path,
                available=False,
                error=_classify_failure(proc.stderr),
            )
        commits = []
        for rec in proc.stdout.split(_END):
            rec = rec.strip("\n")
            if not rec:
                continue
            parts = rec.split(_SEP)
            if len(parts) != 4:
                continue
            sha, parents, subject, body = parts
            commits.append(
                Commit(
                    sha=sha, subject=subject, body=body, parents=tuple(parents.split())
                )
            )
        return cls(repo_path=repo_path, commits=tuple(commits), available=True)

    @staticmethod
    def _is_git_repo(repo_path: str) -> bool:
        try:
            proc = subprocess.run(
                ["git", "-C", repo_path, "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return proc.returncode == 0

    def find_idea_trailer(self, idea_id: str) -> tuple[Commit, str] | None:
        """Exact `Idea-Id: <idea_id>` trailer match — the highest-confidence
        inferred evidence, since an author wrote the exact link on purpose.

        Returns (commit, status). Status defaults to "landed" unless the
        SAME commit also carries an `Idea-Status: partial` trailer — this is
        the inferred tier's route to PARTIAL: it is data-driven from what the
        commit actually says, never a hardcoded LANDED regardless of
        evidence (that hardcoding was finding #4 of the audit). No commit in
        the current fleet history writes this trailer yet; the mechanism is
        proven by `tests/test_gitevidence.py`, not by a hit on the real
        doc — see `cli.py`'s reported counts."""
        for c in self.commits:
            # finditer, not search: one commit may land several ideas and
            # carry a trailer for each. `search` would see only the first,
            # silently costing every later id its highest-confidence evidence.
            for m in _IDEA_ID_TRAILER_RE.finditer(c.trailers):
                if m.group(1) == idea_id:
                    status_m = _IDEA_STATUS_TRAILER_RE.search(c.trailers)
                    status = status_m.group(1).lower() if status_m else "landed"
                    return c, status
        return None

    def find_merged_pr(self, pr_num: int) -> Commit | None:
        """A real merge commit (two or more parents) whose SUBJECT is GitHub's
        own record of merging PR `pr_num` ("Merge pull request #N from ...").
        Both conditions are required: the subject is a string anyone can
        write, while the parent count is structural. This is what makes the PR
        number a REAL, resolved signal rather than a bare mention: it is
        git's own account of a merge having happened, not a string that
        merely contains the same digits. Only ever called with a `pr_num`
        the ITEM TEXT explicitly names as a PR (`PR_MENTION_RE` in
        classify.py) — this method never guesses which number to look for."""
        for c in self.commits:
            # Both halves must hold: git's own merge-commit SUBJECT *and* two
            # or more parents. The subject alone is a string anyone can write;
            # the parent count is structural and cannot be faked by prose.
            if not c.is_merge:
                continue
            m = _MERGE_COMMIT_RE.match(c.subject)
            if m and int(m.group(1)) == pr_num:
                return c
        return None

    def all_idea_trailers(self) -> list[tuple[Commit, str, str]]:
        """Every `Idea-Id` trailer in the loaded history, as
        (commit, idea_id, status) in `git log` order.

        `find_idea_trailer` answers "does THIS item have evidence?" and is the
        classifier's question. This answers the inverse — "what do the commits
        claim?" — which is what `verify.py` needs in order to catch a trailer
        naming an item the doc does not contain. A typo'd or stale id is worse
        than a missing one: the classifier will assert LANDED from it, and
        nothing else in the rule stack can tell a real join key from a
        plausible-looking dead one."""
        out: list[tuple[Commit, str, str]] = []
        for c in self.commits:
            status_m = _IDEA_STATUS_TRAILER_RE.search(c.trailers)
            # `Idea-Status` is commit-level: a commit that lands several ideas
            # partially is saying so about all of them. Splitting status per id
            # would need a richer trailer shape than the convention defines.
            status = status_m.group(1).lower() if status_m else "landed"
            seen: set[str] = set()
            for m in _IDEA_ID_TRAILER_RE.finditer(c.trailers):
                # One commit repeating the same id is one claim, not two —
                # counting it twice would inflate `verify`'s totals.
                if m.group(1) in seen:
                    continue
                seen.add(m.group(1))
                out.append((c, m.group(1), status))
        return out


def changed_paths(repo_path: str) -> dict[str, tuple[str, ...]]:
    """{sha: paths changed} for every commit reachable from HEAD.

    A second `git log`, deliberately kept out of `GitLog.load`: the classify
    path stays at one subprocess per run, and only the benchmark — which asks
    a different question — pays for this.

    Merge commits list no paths under plain `git log --name-only`. That is
    accepted rather than worked around (`-m` would multiply every merge by its
    parent count): a merge commit's message is GitHub's, not an author's, so
    it is not where trailers get written.
    """
    fmt = f"{_END}%H"
    try:
        proc = subprocess.run(
            ["git", "-C", repo_path, "log", f"--format={fmt}", "--name-only"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if proc.returncode != 0:
        return {}

    out: dict[str, tuple[str, ...]] = {}
    for rec in proc.stdout.split(_END):
        lines = [ln for ln in rec.splitlines() if ln.strip()]
        if not lines:
            continue
        out[lines[0]] = tuple(lines[1:])
    return out
