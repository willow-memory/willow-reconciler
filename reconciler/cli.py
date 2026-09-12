"""reconciler CLI.

    reconciler run --repo willow-mcp --doc docs/ideas.md [--format markdown|json] [--validate]
    reconciler id --repo willow-mcp --doc docs/ideas.md (--num N | --grep TEXT)
    reconciler verify --repo willow-mcp --doc docs/ideas.md [--format markdown|json]
    reconciler install-hook --repo willow-mcp [--force]
    reconciler benchmark --repo willow-mcp --doc docs/ideas.md [--format markdown|json]
    reconciler fleet --repo willow-mcp --repo willow-reconciler [--doc docs/ideas.md] [--format markdown|json]
    reconciler conventions [--json]

`run` and `verify` are read-only (`git log` only). `install-hook` is the one
verb that writes into the target repo, which is why it is a verb and not a
flag on anything else — see hooks.py.

Read-only, deterministic, stdlib-only — mirrors corpus-lens/corpuslens/cli.py's
one-verb-per-subcommand shape and its refusal to print a traceback: every
failure is a clear `error:` line on stderr and a non-zero exit.

`--repo` accepts either a PATH (absolute, or relative to the current working
directory — anything carrying a `/` or `\\`, or already absolute) to a repo
directory, used as-is, or a bare NAME, resolved in this order, first hit
wins, each candidate required to contain `.git`:

  1. a sibling of the current working directory's own enclosing git checkout
     (walk up from cwd to the nearest `.git`, then take that directory's
     parent);
  2. a sibling of the cwd itself;
  3. a sibling of THIS PACKAGE's own checkout (`_fleet_root` below) — the
     fleet's recommended layout (willow-mcp, corpus-lens, willow-reconciler
     all under one parent), kept because it is what makes a source checkout
     work with no cwd set up at all.

A packaged install (from PyPI) has no meaningful package-checkout sibling —
candidate 3 lands in `site-packages` and never resolves — so (1)/(2) are
what let `reconciler run --repo willow-mcp ...` work from an arbitrary
directory once installed. See `_resolve_repo`. `--doc` is a path relative to
the resolved repo's root.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import validate as validatemod
from .benchmark import benchmark
from .classify import classify_item
from .conventions import conventions, render_json, render_markdown
from .emit import VALID_STATUSES, find_items, trailer_block
from .failure_classes import classify_file
from .fleet import DOC_OK, build_fleet
from .gitevidence import GitLog
from .hooks import install_hooks
from .ids import idea_id
from .ledger import build_ledger
from .parse import parse_doc
from .verify import verify_trailers


def _fleet_root() -> Path:
    """The directory containing this package's own repo (willow-reconciler)
    — e.g. `~/github/willow-memory`. Computed from `__file__`, never from an
    environment variable or a hardcoded username, so the tool works the same
    on any checkout of the fleet tree. From an installed (PyPI) package this
    lands inside `site-packages` and its sibling is never a real repo — that
    is exactly why `_resolve_repo` tries the caller's own checkout first."""
    return Path(__file__).resolve().parents[2]


def _enclosing_git_checkout(start: Path) -> Path | None:
    """Walk up from `start` to the nearest directory (inclusive) that
    contains a `.git` entry — a directory for an ordinary clone, a file for a
    worktree or submodule, either way `Path.exists()` alone is enough since
    this never needs to read it. None when no ancestor of `start` is inside a
    git checkout at all."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _is_path_like(repo: str) -> bool:
    """True when `--repo` was given a filesystem path rather than a bare name
    to resolve by convention. Checked for either separator (not just
    `os.sep`) so a POSIX-style relative path (`../willow-mcp`) reads as a
    path the same way on every platform this tool's CI runs, per the
    Windows-path CI lesson: never assume the platform's own separator is the
    only one a caller might type."""
    return "/" in repo or "\\" in repo or Path(repo).is_absolute()


def _name_candidates(name: str, fleet_root: Path | None) -> list[Path]:
    """Every directory a bare `--repo <name>` might mean, in resolution
    order — first one containing `.git` wins (see `_resolve_repo`). Listed in
    full (not lazily) so a failed resolution can name every candidate it
    tried, and deduplicated (by resolved path) so a repo laid out exactly per
    the fleet convention doesn't get the same directory listed three times in
    that error."""
    candidates: list[Path] = []
    cwd = Path.cwd()
    checkout_root = _enclosing_git_checkout(cwd)
    if checkout_root is not None:
        candidates.append(checkout_root.parent / name)
    candidates.append(cwd.parent / name)
    candidates.append((fleet_root or _fleet_root()) / name)

    seen: set[Path] = set()
    out: list[Path] = []
    for c in candidates:
        key = c.resolve()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _resolve_repo(repo: str, fleet_root: Path | None = None) -> tuple[Path | None, list[Path]]:
    """Resolve `--repo` to a real repo directory (one containing `.git`).

    Returns `(path, candidates)`: `path` is the first candidate that actually
    contains `.git`, or `None` if none did; `candidates` is every directory
    that was tried, in order, for the caller to report on failure. See the
    module docstring for the path-vs-name rule this implements."""
    if _is_path_like(repo):
        candidate = Path(repo)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if (candidate / ".git").exists():
            return candidate.resolve(), [candidate]
        return None, [candidate]

    candidates = _name_candidates(repo, fleet_root)
    for c in candidates:
        if (c / ".git").exists():
            return c.resolve(), candidates
    return None, candidates


def _repo_not_found_error(repo: str, candidates: list[Path]) -> str:
    tried = "; ".join(str(c) for c in candidates)
    return (f"error: repo '{repo}' not found — no `.git` at any candidate tried: "
            f"{tried}. Pass a path to the repo directory, or a bare name that "
            f"resolves beside your own checkout or willow-reconciler's own.")


def _load(repo: str, doc: str, fleet_root: Path | None):
    """Shared front half of every doc-reading verb: resolve the repo, read
    the doc, parse it. Returns (repo_path, items, dropped) or an int exit
    code — so `run`, `id` and `verify` report the same errors in the same
    words, and only one of them owns the wording."""
    repo_path, candidates = _resolve_repo(repo, fleet_root)
    if repo_path is None:
        print(_repo_not_found_error(repo, candidates), file=sys.stderr)
        return 2

    doc_path = repo_path / doc
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError as e:
        # `doc` and `repo` are echoed because the caller typed them; the
        # OSError's own text is NOT, because it carries the RESOLVED absolute
        # path (so the operating user and the fleet layout) that the caller
        # never typed. See reconciler/failure_classes.py.
        print(f"error: could not read --doc {doc} under {repo}: "
              f"{classify_file(str(e))}", file=sys.stderr)
        return 2

    items, dropped = parse_doc(text)
    if not items:
        print(f"error: no numbered items found in {doc} — wrong file, or a doc with "
              f"no top-level `N. ` list items.", file=sys.stderr)
        return 1
    return repo_path, items, dropped


def run(repo: str, doc: str, fmt: str = "markdown", do_validate: bool = False,
        fleet_root: Path | None = None) -> int:
    loaded = _load(repo, doc, fleet_root)
    if isinstance(loaded, int):
        return loaded
    repo_path, items, dropped = loaded

    gitlog = GitLog.load(str(repo_path))
    verdicts = [
        classify_item(idea_id(item.num), item.num, item.text, gitlog)
        for item in items
    ]
    ledger = build_ledger(doc=doc, repo=repo, items_total=len(items) + dropped,
                          dropped=dropped, verdicts=verdicts)

    if do_validate:
        truth = validatemod.hand_tags(items)
        ledger["validation"] = {
            "echo_check": validatemod.echo_check(truth, verdicts),
            "holdout": validatemod.holdout_score(items, gitlog),
        }

    print(_render(ledger, fmt))
    return 0


def cmd_id(repo: str, doc: str, num: int | None, grep: str | None,
           status: str = "landed", fleet_root: Path | None = None) -> int:
    """Print the trailer line for one item. STDOUT is the trailer and nothing
    else, so it pipes straight into a commit message; everything explanatory
    goes to stderr."""
    loaded = _load(repo, doc, fleet_root)
    if isinstance(loaded, int):
        return loaded
    _, items, _ = loaded

    matches = find_items(items, num=num, grep=grep)
    selector = f"--num {num}" if num is not None else f"--grep {grep!r}"

    if not matches:
        print(f"error: no item in {doc} matches {selector}.", file=sys.stderr)
        return 1
    if len(matches) > 1:
        # Never guess. Picking the wrong item writes a confident, permanent,
        # WRONG join key — precisely the failure the trailer exists to prevent.
        print(f"error: {selector} matches {len(matches)} items in {doc}; narrow it:",
              file=sys.stderr)
        for i in matches:
            print(f"  {i.num}. {i.text[:90]}", file=sys.stderr)
        return 1

    item = matches[0]
    print(f"# {doc}:{item.line_no} — {item.num}. {item.text[:90]}", file=sys.stderr)
    print(trailer_block(item.num, status))
    return 0


def cmd_verify(repo: str, doc: str, fmt: str = "markdown",
               fleet_root: Path | None = None) -> int:
    """Exit 1 when any trailer fails to resolve — a dangling key is a real
    defect in the evidence base, so this is meant to be a CI gate."""
    loaded = _load(repo, doc, fleet_root)
    if isinstance(loaded, int):
        return loaded
    repo_path, items, _ = loaded

    result = verify_trailers(doc, repo, items, GitLog.load(str(repo_path)))
    if fmt == "json":
        print(json.dumps(result, indent=2))
    else:
        lines = ["# reconciler verify", "", result["headline"], "", result["reading"], ""]
        for row in result["unresolved"]:
            lines.append(f"- **UNRESOLVED** `{row['idea_id']}` in {row['short_sha']}: "
                         f"{row['subject']}")
        for row in result["resolved"]:
            lines.append(f"- ok `{row['idea_id']}` ({row['status']}) in "
                         f"{row['short_sha']}: {row['subject']}")
        print("\n".join(lines))
    if not result["git_available"]:
        return 2
    return 0 if result["ok"] else 1


def cmd_install_hook(repo: str, force: bool = False,
                     fleet_root: Path | None = None) -> int:
    repo_path, candidates = _resolve_repo(repo, fleet_root)
    if repo_path is None:
        print(_repo_not_found_error(repo, candidates), file=sys.stderr)
        return 2

    result = install_hooks(repo_path, force=force)
    if result.get("error"):
        print(f"error: {result['error']}", file=sys.stderr)
        return 2
    print(f"hooks directory: {result['hooks_dir']}", file=sys.stderr)
    for row in result["results"]:
        if row["action"] == "skipped":
            print(f"skipped {row['hook']}: {row['reason']}", file=sys.stderr)
        else:
            print(f"{row['action']} {row['path']}")
    return 0 if result["ok"] else 1


def cmd_benchmark(repo: str, doc: str, fmt: str = "markdown",
                  fleet_root: Path | None = None) -> int:
    """Never exits non-zero on a low score. A 0.0 independent rate is the
    expected reading for a convention that has been demonstrated but not yet
    lived in — the fix is time, not code, and a gate here would only invite
    someone to game the number."""
    loaded = _load(repo, doc, fleet_root)
    if isinstance(loaded, int):
        return loaded
    repo_path, items, _ = loaded

    result = benchmark(items, GitLog.load(str(repo_path)), str(repo_path), doc)
    if fmt == "json":
        print(json.dumps(result, indent=2))
        return 0

    lines = ["# reconciler benchmark", "", result["headline"], "", result["reading"], "",
             f"- **independent recovery** (the quotable number): "
             f"{result['n_recovered_independent']}/{result['n_hand_tagged']} "
             f"(rate={result['independent_recovery_rate']})",
             f"- **raw recovery** (NOT a capability number): "
             f"{result['n_recovered']}/{result['n_hand_tagged']} "
             f"(rate={result['recovery_rate']})",
             f"- **trailer provenance across the whole history**: "
             f"{result['trailer_provenance']}", ""]
    for d in result["detail"]:
        if not d["recovered"]:
            lines.append(f"  - [MISS] {d['idea_id']}: expected={d['expected']} "
                         f"got={d['got']}")
        else:
            lines.append(f"  - [{d['provenance'].upper()}] {d['idea_id']}: "
                         f"recovered from {(d['evidence_sha'] or '?')[:10]}")
    print("\n".join(lines))
    return 0


def _render(ledger: dict, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(ledger, indent=2)
    lines = ["# reconciler run", "",
             ledger["headline"], "", ledger["reading"], "",
             f"- **doc**: {ledger['doc']} ({ledger['repo']})",
             f"- **items parsed**: {ledger['items_parsed']} of {ledger['items_total']} "
             f"({ledger['dropped']} dropped, unparseable)",
             f"- **by status**: {ledger['counts_by_status']}",
             f"- **by evidence kind**: {ledger['counts_by_evidence_kind']}"]
    if ledger["duplicate_nums"]:
        lines.append(f"- **duplicate item numbers** (surfaced, not resolved): "
                     f"{ledger['duplicate_nums']}")
    lines += ["", "## items", "",
             "Each item names the rule that fired (see classify.py's docstring: "
             "1 = explicit legend tag, 2a = Idea-Id trailer, 2b = merged-PR mention, "
             "3 = abstain) so a verdict is inspectable without reading the source."]
    for row in ledger["items"]:
        lines.append(f"- `{row['idea_id']}` **{row['status']}** (rule {row['rule']}, "
                     f"{row['evidence_kind']}): {row['evidence']}")
    if "validation" in ledger:
        ec = ledger["validation"]["echo_check"]
        ho = ledger["validation"]["holdout"]
        lines += ["", "## validation", "",
                  f"**echo check** (trivial — rule 1 reading its own tag back; NOT a "
                  f"capability number): n={ec['n']}, accuracy={ec['accuracy']}. {ec['note']}",
                  "",
                  f"**hold-out score** (the real Slice-0 acceptance number — legend tag "
                  f"stripped, then reclassified with only the inferred/not_started tiers): "
                  f"{ho['n_recovered']}/{ho['n_hand_tagged']} recovered "
                  f"(recovery_rate={ho['recovery_rate']})."]
        for d in ho["detail"]:
            mark = "OK" if d["recovered"] else "MISS"
            lines.append(f"  - [{mark}] {d['idea_id']}: expected={d['expected']} "
                         f"got={d['got']} ({d['evidence_kind']})")
    return "\n".join(lines)


def cmd_fleet(repos: list[str], doc: str = "docs/ideas.md", fmt: str = "markdown",
             fleet_root: Path | None = None) -> int:
    """One table across many repos. Each `--repo` is resolved exactly as
    `run`'s is (path or bare name — see the module docstring); a repo that
    fails to resolve at all still aborts the command the way `run` does
    (there is no repo to read anything from), but a repo that resolves and
    simply has no readable doc becomes a `doc_status: "missing"` row rather
    than aborting the rest of the fleet — see `fleet.py`."""
    resolved: list[tuple[str, Path]] = []
    for repo in repos:
        repo_path, candidates = _resolve_repo(repo, fleet_root)
        if repo_path is None:
            print(_repo_not_found_error(repo, candidates), file=sys.stderr)
            return 2
        resolved.append((repo, repo_path))

    result = build_fleet(resolved, doc)
    if fmt == "json":
        print(json.dumps(result, indent=2))
        return 0
    print(_render_fleet(result))
    return 0


_FLEET_COLUMNS = ("items", "dropped", "explicit landed", "explicit partial",
                  "inferred landed", "inferred partial", "none",
                  "independent", "raw")


def _fleet_row_cells(row: dict) -> tuple[str, ...]:
    if row["doc_status"] != DOC_OK:
        return (f"doc: missing ({row['doc_error']})",) + ("—",) * (len(_FLEET_COLUMNS) - 1)
    return (str(row["items_parsed"]), str(row["dropped"]), str(row["explicit_landed"]),
            str(row["explicit_partial"]), str(row["inferred_landed"]),
            str(row["inferred_partial"]), str(row["none"]),
            str(row["independent_recovery_rate"]), str(row["recovery_rate"]))


def _render_fleet(result: dict) -> str:
    t = result["totals"]
    lines = ["# reconciler fleet", "",
             f"- **doc**: {result['doc']} (checked in every repo listed below)",
             f"- **repos**: {len(result['rows'])} ({t['repos_ok']} readable, "
             f"{t['repos_doc_missing']} with `doc: missing`)",
             "",
             "| repo | " + " | ".join(_FLEET_COLUMNS) + " |",
             "|" + "---|" * (len(_FLEET_COLUMNS) + 1)]
    for row in result["rows"]:
        lines.append(f"| {row['repo']} | " + " | ".join(_fleet_row_cells(row)) + " |")
    lines.append(
        f"| **totals (pooled)** | {t['items_parsed']} | {t['dropped']} | "
        f"{t['explicit_landed']} | {t['explicit_partial']} | {t['inferred_landed']} | "
        f"{t['inferred_partial']} | {t['none']} | {t['pooled_independent_recovery_rate']} | "
        f"{t['pooled_recovery_rate']} |")
    lines += ["", "## reading", ""]
    for r in result["reading"]:
        lines += [f"- {r}", ""]
    return "\n".join(lines).rstrip("\n")


def cmd_conventions(as_json: bool = False) -> int:
    """Publish the fleet convention set (`conventions.py`). Takes no --repo:
    the rules are the fleet's, not any one repo's, and every consumer's
    `tests/test_fleet_conventions.py` is what holds a tree to them."""
    doc = conventions()
    print(render_json(doc) if as_json else render_markdown(doc))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="reconciler")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="parse a doc's numbered items and classify each "
                                   "landed/partial/not_started against the repo's own records")
    r.add_argument("--repo", required=True,
                   help="a path to the repo, or a bare name resolved beside your "
                        "checkout or willow-reconciler's own (see module docstring)")
    r.add_argument("--doc", required=True, help="path to the doc, relative to --repo's root")
    r.add_argument("--format", default="markdown", choices=("markdown", "json"), dest="fmt")
    r.add_argument("--validate", action="store_true",
                   help="score this run's verdicts against the doc's own hand-tagged "
                        "(✅/🟡) items and report precision/recall")

    i = sub.add_parser("id", help="print the Idea-Id trailer line for one item, "
                                  "ready to paste into a commit message")
    i.add_argument("--repo", required=True)
    i.add_argument("--doc", required=True)
    sel = i.add_mutually_exclusive_group(required=True)
    sel.add_argument("--num", type=int, help="the item's own number in the doc")
    sel.add_argument("--grep", help="case-insensitive substring of the item text; "
                                    "errors rather than guessing if it is ambiguous")
    i.add_argument("--status", default="landed", choices=VALID_STATUSES,
                   help="'partial' additionally emits an Idea-Status trailer")

    v = sub.add_parser("verify", help="check that every Idea-Id trailer in the repo's "
                                      "history resolves to a real item in the doc")
    v.add_argument("--repo", required=True)
    v.add_argument("--doc", required=True)
    v.add_argument("--format", default="markdown", choices=("markdown", "json"), dest="fmt")

    h = sub.add_parser("install-hook",
                       help="write the prepare-commit-msg/commit-msg hooks into the "
                            "target repo (the one verb that writes outside this repo)")
    h.add_argument("--repo", required=True)
    h.add_argument("--force", action="store_true",
                   help="replace a hook this tool did not write")

    b = sub.add_parser("benchmark",
                       help="how much recovered landing came from a trailer written "
                            "independently of the pile — the honest recall number")
    b.add_argument("--repo", required=True)
    b.add_argument("--doc", required=True)
    b.add_argument("--format", default="markdown", choices=("markdown", "json"), dest="fmt")

    f = sub.add_parser("fleet", help="reconcile the same doc across many repos and pool "
                                     "the result into one table")
    f.add_argument("--repo", required=True, action="append", dest="repos",
                   help="repeatable — a path or bare name, same rule as `run`'s --repo")
    f.add_argument("--doc", default="docs/ideas.md",
                   help="path relative to each --repo's root (same for every repo)")
    f.add_argument("--format", default="markdown", choices=("markdown", "json"), dest="fmt")

    c = sub.add_parser("conventions", help="publish the fleet's convention set — the one "
                                           "home of the rules every repo's "
                                           "tests/test_fleet_conventions.py reads")
    c.add_argument("--json", action="store_true", dest="as_json",
                   help="emit the schema-versioned JSON document instead of markdown")

    args = p.parse_args(argv)
    if args.cmd == "run":
        return run(args.repo, args.doc, args.fmt, args.validate)
    if args.cmd == "id":
        return cmd_id(args.repo, args.doc, args.num, args.grep, args.status)
    if args.cmd == "verify":
        return cmd_verify(args.repo, args.doc, args.fmt)
    if args.cmd == "benchmark":
        return cmd_benchmark(args.repo, args.doc, args.fmt)
    if args.cmd == "fleet":
        return cmd_fleet(args.repos, args.doc, args.fmt)
    if args.cmd == "conventions":
        return cmd_conventions(args.as_json)
    if args.cmd == "install-hook":
        return cmd_install_hook(args.repo, args.force)
    return 2


if __name__ == "__main__":
    sys.exit(main())
