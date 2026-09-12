"""Git hooks that write the `Idea-Id` trailer, and the installer for them.

This is the only part of willow-reconciler that ever writes outside its own
repo, so it is an explicit verb (`reconciler install-hook`) and never a side
effect of a `run`. The tool's read-only promise is about the reconcile path —
`run`/`verify` still only ever call `git log` — and keeping the one writing
operation behind its own opt-in subcommand is what keeps that promise legible.

Two hooks, both plain POSIX sh with no dependency on this package (they keep
working in a checkout that has never installed it):

  prepare-commit-msg — if the branch name names an idea number, add the
      trailer. Authoring is where the convention actually fails: the doc lives
      in another repo, so the id has to be typed from memory, and a trailer
      nobody writes is worth exactly the 0.0 recovery Slice 0 measured.
  commit-msg — reject a malformed `Idea-Id` line. A trailer that does not
      match the id shape can never resolve, and rule 2a treats a trailer as
      the strongest evidence there is, so catching the typo at commit time is
      far cheaper than discovering a dangling key in `verify` months later.

Neither hook can INVENT a link: the prepare hook fires only when the branch
name already carries the number, and it never overwrites a trailer the author
wrote by hand.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

MARKER = "# installed by `reconciler install-hook` (willow-reconciler)"

PREPARE_COMMIT_MSG = (
    "#!/bin/sh\n"
    + MARKER
    + "\n"
    + r"""
# Adds an `Idea-Id` trailer when the branch name names an idea number, e.g.
#   idea-24  |  ideas-024  |  feature/idea_24-anchor-tags   ->  willow-ideas-024
# Does nothing when: the message already has a trailer, the branch does not
# name a number, or the commit is a merge/squash (whose message is not the
# author's to annotate).
set -e
msg_file="$1"
source="$2"

case "$source" in
  merge|squash) exit 0 ;;
esac

# An author-written trailer always wins — never second-guess an explicit one.
if grep -qi '^Idea-Id:' "$msg_file"; then
  exit 0
fi

branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null) || exit 0
[ -n "$branch" ] || exit 0

# Every idea number the branch names. A single greedy sed took the LAST one,
# so `idea-42-followup-to-idea-7` wrote a well-formed trailer for item 7 — a
# confidently wrong, permanent join key that `verify` cannot flag, because it
# resolves. Two numbers means the branch is ambiguous about what it lands, and
# guessing is the one thing this convention must never do (`reconciler id`
# refuses an ambiguous --grep for the same reason). Leading zeros are stripped
# before printf, which may otherwise read `024` as octal.
nums=$(printf '%s\n' "$branch" | grep -oi 'idea[s]*[-_/][0-9][0-9]*' \
         | grep -o '[0-9][0-9]*$' | sed 's/^0*//' | grep -v '^$' | sort -u)
count=$(printf '%s' "$nums" | grep -c '^[0-9]' || true)

# `[ ... ] && exit 0` would be a set -e landmine: when the test is FALSE the
# list's status is non-zero, set -e fires, and a non-zero prepare-commit-msg
# aborts the commit. Always the `if` form in a hook.
if [ "$count" -eq 0 ]; then
  exit 0
fi
if [ "$count" -gt 1 ]; then
  echo "prepare-commit-msg: branch '$branch' names more than one idea number;" >&2
  echo "  not guessing. Add the trailer yourself:" >&2
  echo "  reconciler id --repo R --doc D --num N" >&2
  exit 0
fi

# printf sets a MINIMUM width, so an id past 999 keeps its own digits — the
# fixed 3-wide padding is a floor, exactly as reconciler/ids.py defines it.
id=$(printf 'willow-ideas-%03d' "$nums")

# interpret-trailers keeps the trailer inside the existing trailer block
# (alongside Co-Authored-By) rather than starting a new paragraph after it.
if ! git interpret-trailers --in-place --trailer "Idea-Id: $id" "$msg_file" 2>/dev/null; then
  printf '\nIdea-Id: %s\n' "$id" >> "$msg_file"
fi
"""
)

COMMIT_MSG = (
    "#!/bin/sh\n"
    + MARKER
    + "\n"
    + r"""
# Rejects a malformed `Idea-Id` trailer. The id shape is fixed at
# `willow-ideas-NNN` (at least 3 digits, zero-padded) by reconciler/ids.py;
# anything else can never resolve against a doc, and rule 2a would still rank
# it as the strongest evidence the classifier has. Cheaper to catch here than
# to find a dangling key in `reconciler verify` months later.
set -e
msg_file="$1"

# Validate only the TRAILER BLOCK — the run of paragraphs at the end whose
# every line is `Key: value` shaped. A message that merely DISCUSSES the
# convention ("Idea-Status: partial means ...") is prose, not a claim, and
# rejecting it was this validator making the same mention-is-not-evidence
# mistake the classifier was twice audited for. Comments go first; git strips
# them from the final message anyway.
trailers=$(grep -v '^#' "$msg_file" | awk '
  { lines[NR] = $0 }
  END {
    n = NR
    while (n > 0 && lines[n] ~ /^[ \t]*$/) n--
    start = n + 1
    while (n > 0) {
      p = n
      while (p > 1 && lines[p-1] !~ /^[ \t]*$/) p--
      ok = 1
      for (i = p; i <= n; i++)
        if (lines[i] !~ /^[A-Za-z][A-Za-z0-9-]*:[ \t]/) ok = 0
      if (!ok) break
      start = p
      n = p - 1
      while (n > 0 && lines[n] ~ /^[ \t]*$/) n--
    }
    for (i = start; i <= NR; i++) if (lines[i] !~ /^[ \t]*$/) print lines[i]
  }')

bad=$(printf '%s\n' "$trailers" | grep -i '^Idea-Id:' \
        | grep -cv '^Idea-Id: willow-ideas-[0-9][0-9][0-9][0-9]*$' || true)
if [ "$bad" -gt 0 ]; then
  echo "commit-msg: malformed Idea-Id trailer." >&2
  printf '%s\n' "$trailers" | grep -i '^Idea-Id:' \
    | grep -v '^Idea-Id: willow-ideas-[0-9][0-9][0-9][0-9]*$' >&2
  echo "expected: Idea-Id: willow-ideas-NNN   (at least 3 digits, zero-padded)" >&2
  echo "get the right line with: reconciler id --repo R --doc D --num N" >&2
  exit 1
fi

bad_status=$(printf '%s\n' "$trailers" | grep -i '^Idea-Status:' \
               | grep -cv '^Idea-Status: \(landed\|partial\)$' || true)
if [ "$bad_status" -gt 0 ]; then
  echo "commit-msg: Idea-Status must be exactly 'landed' or 'partial'." >&2
  exit 1
fi
"""
)

HOOKS = {
    "prepare-commit-msg": PREPARE_COMMIT_MSG,
    "commit-msg": COMMIT_MSG,
}


def hooks_dir(repo_path: Path) -> Path:
    """The directory git will actually look in — `core.hooksPath` when the repo
    sets one, else `.git/hooks`.

    An earlier version hardcoded `.git/hooks` and documented not reading the
    config as a deliberate simplification. It was not a safe one: a repo with
    `core.hooksPath` set got a cheerful "installed" for two files git would
    never run, and the silence looked exactly like a repo where the convention
    simply was not being followed. Reporting success for an inert install is a
    reporting lie, and this tool's whole argument is about not making confident
    claims it cannot support."""
    configured = _config_hooks_path(repo_path)
    if configured is None:
        return repo_path / ".git" / "hooks"
    # git resolves a relative core.hooksPath against the current working
    # directory at hook time, which for a hook is the repo top level.
    path = Path(configured)
    return path if path.is_absolute() else repo_path / path


def _config_hooks_path(repo_path: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_path), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and value else None


def install_hooks(repo_path: Path, force: bool = False) -> dict:
    """Write both hooks into `repo_path`. Never clobbers a hook this tool did
    not write unless `force` — somebody else's prepare-commit-msg is not ours
    to silently replace. Re-running over our own previous install is always
    allowed, so upgrading is just running it again."""
    results: list[dict] = []
    if not (repo_path / ".git").is_dir():
        hdir = repo_path / ".git" / "hooks"
        return {
            "ok": False,
            "hooks_dir": str(hdir),
            "results": [],
            "error": f"{repo_path} has no .git directory (not a git repo, or a "
            f"worktree/submodule whose .git is a file)",
        }
    hdir = hooks_dir(repo_path)
    hdir.mkdir(parents=True, exist_ok=True)

    for name, body in HOOKS.items():
        path = hdir / name
        if path.exists():
            existing = path.read_text(encoding="utf-8", errors="replace")
            if MARKER not in existing and not force:
                results.append(
                    {
                        "hook": name,
                        "path": str(path),
                        "action": "skipped",
                        "reason": "a hook this tool did not write is already "
                        "installed; re-run with --force to replace it",
                    }
                )
                continue
            action = "replaced"
        else:
            action = "installed"
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        results.append({"hook": name, "path": str(path), "action": action})

    return {
        "ok": all(r["action"] != "skipped" for r in results),
        "hooks_dir": str(hdir),
        "results": results,
    }


__all__ = [
    "COMMIT_MSG",
    "HOOKS",
    "MARKER",
    "PREPARE_COMMIT_MSG",
    "hooks_dir",
    "install_hooks",
]
