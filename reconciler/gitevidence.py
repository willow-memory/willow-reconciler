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

_SEP = "\x01"        # field separator inside one commit's record
_END = "\x02"        # record separator between commits

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
_SQUASH_MERGE_RE = re.compile(r"\(#(\d+)\)\s*$")


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str
    body: str

    @property
    def full_text(self) -> str:
        return f"{self.subject}\n{self.body}"


@dataclass(frozen=True)
class GitLog:
    repo_path: str
    commits: tuple[Commit, ...] = field(default_factory=tuple)
    available: bool = True
    error: str = ""

    @classmethod
    def load(cls, repo_path: str) -> "GitLog":
        """Read the full commit history of `repo_path` once. Never raises on
        a missing/non-git repo — returns `available=False` with `error` set,
        so a caller can report the gap rather than crash: an idea-doc in a
        repo with no `.git` (or git not installed) still parses and
        classifies, it just gets no inferred evidence."""
        fmt = f"%H{_SEP}%s{_SEP}%b{_END}"
        try:
            proc = subprocess.run(
                ["git", "-C", repo_path, "log", "--all", f"--format={fmt}"],
                capture_output=True, text=True, timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as e:
            return cls(repo_path=repo_path, available=False, error=str(e))
        if proc.returncode != 0:
            return cls(repo_path=repo_path, available=False,
                       error=proc.stderr.strip() or f"git log exited {proc.returncode}")
        commits = []
        for rec in proc.stdout.split(_END):
            rec = rec.strip("\n")
            if not rec:
                continue
            parts = rec.split(_SEP)
            if len(parts) != 3:
                continue
            sha, subject, body = parts
            commits.append(Commit(sha=sha, subject=subject, body=body))
        return cls(repo_path=repo_path, commits=tuple(commits), available=True)

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
            for m in _IDEA_ID_TRAILER_RE.finditer(c.full_text):
                if m.group(1) == idea_id:
                    status_m = _IDEA_STATUS_TRAILER_RE.search(c.full_text)
                    status = status_m.group(1).lower() if status_m else "landed"
                    return c, status
        return None

    def find_merged_pr(self, pr_num: int) -> Commit | None:
        """A commit whose SUBJECT shows GitHub's own record of merging PR
        `pr_num` — either a merge commit ("Merge pull request #N from ...")
        or a squash-merge title ("... (#N)"). This is what makes the PR
        number a REAL, resolved signal rather than a bare mention: it is
        git's own account of a merge having happened, not a string that
        merely contains the same digits. Only ever called with a `pr_num`
        the ITEM TEXT explicitly names as a PR (`PR_MENTION_RE` in
        classify.py) — this method never guesses which number to look for."""
        for c in self.commits:
            m = _MERGE_COMMIT_RE.match(c.subject)
            if m and int(m.group(1)) == pr_num:
                return c
            m = _SQUASH_MERGE_RE.search(c.subject)
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
            status_m = _IDEA_STATUS_TRAILER_RE.search(c.full_text)
            # `Idea-Status` is commit-level: a commit that lands several ideas
            # partially is saying so about all of them. Splitting status per id
            # would need a richer trailer shape than the convention defines.
            status = status_m.group(1).lower() if status_m else "landed"
            for m in _IDEA_ID_TRAILER_RE.finditer(c.full_text):
                out.append((c, m.group(1), status))
        return out
