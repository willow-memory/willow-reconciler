"""reconciler CLI.

    reconciler run --repo willow-mcp --doc docs/ideas.md [--format markdown|json] [--validate]

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
from .classify import classify_item
from .gitevidence import GitLog
from .ids import idea_id
from .ledger import build_ledger
from .parse import parse_doc


def _fleet_root() -> Path:
    """The directory containing this package's own repo (willow-reconciler)
    — e.g. `~/github/willow-memory`. Computed from `__file__`, never from an
    environment variable or a hardcoded username, so the tool works the same
    on any checkout of the fleet tree."""
    return Path(__file__).resolve().parents[2]


def _resolve_repo(repo: str, fleet_root: Path | None = None) -> Path:
    root = fleet_root or _fleet_root()
    return (root / repo).resolve()


def run(repo: str, doc: str, fmt: str = "markdown", do_validate: bool = False,
        fleet_root: Path | None = None) -> int:
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

    gitlog = GitLog.load(str(repo_path))
    verdicts = [
        classify_item(idea_id(item.num), item.num, item.text, gitlog)
        for item in items
    ]
    ledger = build_ledger(doc=doc, repo=repo, items_total=len(items) + dropped,
                          dropped=dropped, verdicts=verdicts)

    if do_validate:
        truth = validatemod.hand_tags(items)
        ledger["validation"] = validatemod.score(truth, verdicts)

    print(_render(ledger, fmt))
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
    if "validation" in ledger:
        v = ledger["validation"]
        lines += ["", "## validation vs hand-tagged items", "",
                  f"n hand-tagged = {v['n_hand_tagged']}, covered by this run = "
                  f"{v['n_covered']}, accuracy = {v['accuracy']}"]
        if v["missing_from_run"]:
            lines.append(f"- missing from this run's parse: {v['missing_from_run']}")
        for status, pc in v["per_class"].items():
            lines.append(f"- **{status}**: precision={pc['precision']} recall={pc['recall']} "
                         f"(tp={pc['tp']} fp={pc['fp']} fn={pc['fn']})")
        if v["disagreements"]:
            lines.append(f"- disagreements: {v['disagreements']}")
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

    args = p.parse_args(argv)
    if args.cmd == "run":
        return run(args.repo, args.doc, args.fmt, args.validate)
    return 2


if __name__ == "__main__":
    sys.exit(main())
