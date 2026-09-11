"""Read-only git-log evidence for the "inferred" tier of the rule stack.

Never mutates the target repo: this module only ever calls `git log`, never
`git checkout`/`git reset`/anything that touches the worktree or refs. One
subprocess call per repo per run (`GitLog.load`), then every lookup below is
in-memory — so a doc with 100+ items costs one `git log`, not one per item.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

_SEP = "\x01"        # field separator inside one commit's record
_END = "\x02"        # record separator between commits

_IDEA_ID_TRAILER_RE = re.compile(r"(?im)^Idea-Id:\s*(willow-ideas-\S+)\s*$")
_PR_REF_RE = re.compile(r"#(\d+)\b")

# A "strong" token: a backtick-quoted code identifier of enough length that
# matching it against a commit subject/body is unlikely to be coincidence.
# Kept short and named here (not buried in classify.py) since it is the one
# knob that trades inferred-recall for inferred-precision.
_MIN_TOKEN_LEN = 6


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

    def find_idea_trailer(self, idea_id: str) -> Commit | None:
        """Exact `Idea-Id: <idea_id>` trailer match. Highest-confidence
        inferred evidence: an explicit, structured link a commit author
        wrote on purpose."""
        for c in self.commits:
            m = _IDEA_ID_TRAILER_RE.search(c.full_text)
            if m and m.group(1) == idea_id:
                return c
        return None

    def find_pr_reference(self, pr_num: int) -> Commit | None:
        """A commit whose subject/body names this exact PR number (`#123`).
        Only consulted when the ITEM TEXT itself names a PR number (see
        classify.py) — this module never invents one."""
        needle = f"#{pr_num}"
        for c in self.commits:
            if any(m.group(0) == needle for m in _PR_REF_RE.finditer(c.full_text)):
                return c
        return None

    def find_token_match(self, tokens: tuple[str, ...]) -> tuple[Commit, str] | None:
        """First commit whose subject or body contains one of `tokens` (a
        backtick-quoted identifier lifted from the item's own text) as a
        whole word, longest token first. Returns (commit, token) so the
        caller can name exactly what matched. `tokens` shorter than
        `_MIN_TOKEN_LEN` are skipped — short identifiers (`run`, `db`) match
        by accident too often to count as evidence."""
        candidates = sorted(
            (t for t in tokens if len(t) >= _MIN_TOKEN_LEN), key=len, reverse=True
        )
        for token in candidates:
            pat = re.compile(r"\b" + re.escape(token) + r"\b")
            for c in self.commits:
                if pat.search(c.full_text):
                    return c, token
        return None
