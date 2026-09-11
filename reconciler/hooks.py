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
from pathlib import Path

MARKER = "# installed by `reconciler install-hook` (willow-reconciler)"

PREPARE_COMMIT_MSG = f"""#!/bin/sh
{MARKER}
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

# Strip leading zeros before printf: a shell printf may read `024` as octal.
num=$(printf '%s' "$branch" | sed -n 's/.*[Ii]dea[s]*[-_/]0*\\([0-9][0-9]*\\).*/\\1/p')
[ -n "$num" ] || exit 0

id=$(printf 'willow-ideas-%03d' "$num")

# interpret-trailers keeps the trailer inside the existing trailer block
# (alongside Co-Authored-By) rather than starting a new paragraph after it.
if ! git interpret-trailers --in-place --trailer "Idea-Id: $id" "$msg_file" 2>/dev/null; then
  printf '\\nIdea-Id: %s\\n' "$id" >> "$msg_file"
fi
"""

COMMIT_MSG = f"""#!/bin/sh
{MARKER}
# Rejects a malformed `Idea-Id` trailer. The id shape is fixed at
# `willow-ideas-NNN` (3 digits, zero-padded) by reconciler/ids.py; anything
# else can never resolve against a doc, and rule 2a would still rank it as the
# strongest evidence the classifier has. Cheaper to catch here than to find a
# dangling key in `reconciler verify` months later.
set -e
msg_file="$1"

bad=$(grep -i '^Idea-Id:' "$msg_file" | grep -cv '^Idea-Id: willow-ideas-[0-9][0-9][0-9]$' || true)
if [ "$bad" -gt 0 ]; then
  echo "commit-msg: malformed Idea-Id trailer." >&2
  grep -i '^Idea-Id:' "$msg_file" | grep -v '^Idea-Id: willow-ideas-[0-9][0-9][0-9]$' >&2
  echo "expected exactly: Idea-Id: willow-ideas-NNN   (3 digits, zero-padded)" >&2
  echo "get the right line with: reconciler id --repo R --doc D --num N" >&2
  exit 1
fi

bad_status=$(grep -i '^Idea-Status:' "$msg_file" | grep -cv '^Idea-Status: \\(landed\\|partial\\)$' || true)
if [ "$bad_status" -gt 0 ]; then
  echo "commit-msg: Idea-Status must be exactly 'landed' or 'partial'." >&2
  exit 1
fi
"""

HOOKS = {
    "prepare-commit-msg": PREPARE_COMMIT_MSG,
    "commit-msg": COMMIT_MSG,
}


def hooks_dir(repo_path: Path) -> Path:
    """The repo's hook directory, honouring `core.hooksPath` is deliberately
    NOT attempted here: reading config would mean running git, and a wrong
    guess installs a hook somewhere git will never call. `.git/hooks` is
    reported in the result so the caller can see exactly where it went."""
    return repo_path / ".git" / "hooks"


def install_hooks(repo_path: Path, force: bool = False) -> dict:
    """Write both hooks into `repo_path`. Never clobbers a hook this tool did
    not write unless `force` — somebody else's prepare-commit-msg is not ours
    to silently replace. Re-running over our own previous install is always
    allowed, so upgrading is just running it again."""
    hdir = hooks_dir(repo_path)
    results: list[dict] = []
    if not (repo_path / ".git").is_dir():
        return {"ok": False, "hooks_dir": str(hdir), "results": [],
                "error": f"{repo_path} has no .git directory (not a git repo, or a "
                         f"worktree/submodule whose .git is a file)"}
    hdir.mkdir(parents=True, exist_ok=True)

    for name, body in HOOKS.items():
        path = hdir / name
        if path.exists():
            existing = path.read_text(encoding="utf-8", errors="replace")
            if MARKER not in existing and not force:
                results.append({"hook": name, "path": str(path), "action": "skipped",
                                "reason": "a hook this tool did not write is already "
                                          "installed; re-run with --force to replace it"})
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


__all__ = ["COMMIT_MSG", "HOOKS", "MARKER", "PREPARE_COMMIT_MSG",
           "hooks_dir", "install_hooks"]
