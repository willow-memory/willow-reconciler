"""reconciler CLI.

    reconciler run --repo willow-mcp --doc docs/ideas.md [--format markdown|json] [--validate]
    reconciler id --repo willow-mcp --doc docs/ideas.md (--num N | --grep TEXT)
    reconciler verify --repo willow-mcp --doc docs/ideas.md [--format markdown|json]
    reconciler install-hook --repo willow-mcp [--force]
    reconciler benchmark --repo willow-mcp --doc docs/ideas.md [--format markdown|json]

`run` and `verify` are read-only (`git log` only). `install-hook` is the one
verb that writes into the target repo, which is why it is a verb and not a
flag on anything else — see hooks.py.

Read-only, deterministic, stdlib-only — mirrors corpus-lens/corpuslens/cli.py's
one-verb-per-subcommand shape and its refusal to print a traceback: every
failure is a clear `error:` line on stderr and a non-zero exit.

`--repo` names a directory SIBLING to this package (the fleet's own layout:
willow-mcp, corpus-lens, willow-reconciler all live under the same parent —
see `_fleet_root`), never an arbitrary filesystem path, so a typo can't walk
this read-only tool outside the fleet tree it was built to read. `--doc` is
a path relative to that repo's root.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import validate as validatemod
from .benchmark import benchmark
from .classify import classify_item
from .emit import VALID_STATUSES, find_items, trailer_block
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
    on any checkout of the fleet tree."""
    return Path(__file__).resolve().parents[2]


def _resolve_repo(repo: str, fleet_root: Path | None = None) -> Path:
    root = fleet_root or _fleet_root()
    return (root / repo).resolve()


def _load(repo: str, doc: str, fleet_root: Path | None):
    """Shared front half of every doc-reading verb: resolve the sibling repo,
    read the doc, parse it. Returns (repo_path, items, dropped) or an int exit
    code — so `run`, `id` and `verify` report the same errors in the same
    words, and only one of them owns the wording."""
    repo_path = _resolve_repo(repo, fleet_root)
    if not repo_path.is_dir():
        print(f"error: repo '{repo}' not found at {repo_path} — pass a directory "
              f"sibling to willow-reconciler's own repo.", file=sys.stderr)
        return 2

    doc_path = repo_path / doc
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"error: could not read --doc {doc} under {repo}: {e}", file=sys.stderr)
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
    repo_path = _resolve_repo(repo, fleet_root)
    if not repo_path.is_dir():
        print(f"error: repo '{repo}' not found at {repo_path} — pass a directory "
              f"sibling to willow-reconciler's own repo.", file=sys.stderr)
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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="reconciler")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="parse a doc's numbered items and classify each "
                                   "landed/partial/not_started against the repo's own records")
    r.add_argument("--repo", required=True,
                   help="a repo directory sibling to willow-reconciler's own checkout")
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

    args = p.parse_args(argv)
    if args.cmd == "run":
        return run(args.repo, args.doc, args.fmt, args.validate)
    if args.cmd == "id":
        return cmd_id(args.repo, args.doc, args.num, args.grep, args.status)
    if args.cmd == "verify":
        return cmd_verify(args.repo, args.doc, args.fmt)
    if args.cmd == "benchmark":
        return cmd_benchmark(args.repo, args.doc, args.fmt)
    if args.cmd == "install-hook":
        return cmd_install_hook(args.repo, args.force)
    return 2


if __name__ == "__main__":
    sys.exit(main())
