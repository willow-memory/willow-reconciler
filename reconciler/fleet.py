"""The `fleet` verb: reconcile the same idea-pile shape across many repos and
pool the result into one table — one row per repo, plus a `totals` row.

This module never reclassifies or re-derives a number of its own: each row is
built from the exact same functions `run` and `benchmark` already use
(`parse_doc` / `classify_item` / `build_ledger` / `benchmark.benchmark`), so a
fleet-wide bug can never diverge from a single-repo one. The two caveat
sentences (`ledger.READING`, `benchmark.READING`) are imported, not retyped,
for the same reason — see those modules' docstrings for why they are pulled
out as module-level constants.

A repo whose doc cannot be read (missing file, wrong path, an unnumbered
doc with no `N. ` items) is reported as a row with `doc_status: "missing"`,
never raised as an exception — one bad repo in a ten-repo fleet must not hide
the other nine's numbers. `cli.py` resolves `--repo` (path or bare name, see
its module docstring) before calling in here, so a repo this module is asked
to read has already been confirmed to exist; only the DOC read can fail.

`SCHEMA_VERSION` starts this envelope's own numbering at 1 — `run --format
json` has never carried one, so there is no existing number to inherit; bump
it, corpus-lens-style (see its README), only on a field REMOVAL or MEANING
change, never on an addition.
"""

from __future__ import annotations

from pathlib import Path

from .benchmark import READING as BENCHMARK_READING
from .benchmark import benchmark as run_benchmark
from .classify import EXPLICIT, INFERRED, LANDED, NOT_STARTED, PARTIAL, classify_item
from .failure_classes import classify_file
from .gitevidence import GitLog
from .ids import idea_id
from .ledger import READING as LEDGER_READING
from .ledger import build_ledger
from .parse import parse_doc

SCHEMA_VERSION = 1

#: Every row this module can ever produce carries one of these.
DOC_OK = "ok"
DOC_MISSING = "missing"

#: Numeric fields present on every `doc_status == DOC_OK` row — the shared
#: order for both the markdown table's columns and `totals`' keys.
COUNT_FIELDS = (
    "items_parsed",
    "dropped",
    "explicit_landed",
    "explicit_partial",
    "inferred_landed",
    "inferred_partial",
    "none",
)


def reconcile_one(repo_label: str, repo_path: Path, doc: str) -> dict:
    """One repo's fleet row. Never raises: a doc that can't be read or
    doesn't parse becomes a `doc_status: "missing"` row rather than aborting
    the whole fleet run (see module docstring)."""
    doc_path = repo_path / doc
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError as e:
        return {
            "repo": repo_label,
            "doc": doc,
            "doc_status": DOC_MISSING,
            "doc_error": classify_file(str(e)),
        }

    items, dropped = parse_doc(text)
    if not items:
        return {
            "repo": repo_label,
            "doc": doc,
            "doc_status": DOC_MISSING,
            "doc_error": "no numbered items found (wrong file, or a doc with "
            "no top-level `N. ` list items)",
        }

    gitlog = GitLog.load(str(repo_path))
    verdicts = [classify_item(idea_id(i.num), i.num, i.text, gitlog) for i in items]
    ledger = build_ledger(
        doc=doc,
        repo=repo_label,
        items_total=len(items) + dropped,
        dropped=dropped,
        verdicts=verdicts,
    )
    bench = run_benchmark(items, gitlog, str(repo_path), doc)

    bsk = ledger["counts_by_status_and_kind"]
    return {
        "repo": repo_label,
        "doc": doc,
        "doc_status": DOC_OK,
        "items_parsed": ledger["items_parsed"],
        "dropped": ledger["dropped"],
        "explicit_landed": bsk.get(f"{LANDED}/{EXPLICIT}", 0),
        "explicit_partial": bsk.get(f"{PARTIAL}/{EXPLICIT}", 0),
        "inferred_landed": bsk.get(f"{LANDED}/{INFERRED}", 0),
        "inferred_partial": bsk.get(f"{PARTIAL}/{INFERRED}", 0),
        "none": ledger["counts_by_status"].get(NOT_STARTED, 0),
        "n_hand_tagged": bench["n_hand_tagged"],
        "n_recovered": bench["n_recovered"],
        "n_recovered_independent": bench["n_recovered_independent"],
        "recovery_rate": bench["recovery_rate"],
        "independent_recovery_rate": bench["independent_recovery_rate"],
    }


def _totals(rows: list[dict]) -> dict:
    """Sums over every `doc_status == "ok"` row, plus a rate computed over
    the POOLED counts (never an average of per-repo rates — a repo with 2
    hand-tagged items and a repo with 200 must not weigh the same)."""
    ok_rows = [r for r in rows if r["doc_status"] == DOC_OK]
    totals: dict = {field: sum(r[field] for r in ok_rows) for field in COUNT_FIELDS}
    n_hand_tagged = sum(r["n_hand_tagged"] for r in ok_rows)
    n_recovered = sum(r["n_recovered"] for r in ok_rows)
    n_recovered_independent = sum(r["n_recovered_independent"] for r in ok_rows)
    totals.update(
        {
            "repos_ok": len(ok_rows),
            "repos_doc_missing": len(rows) - len(ok_rows),
            "n_hand_tagged": n_hand_tagged,
            "n_recovered": n_recovered,
            "n_recovered_independent": n_recovered_independent,
            "pooled_recovery_rate": (n_recovered / n_hand_tagged)
            if n_hand_tagged
            else None,
            "pooled_independent_recovery_rate": (
                n_recovered_independent / n_hand_tagged
            )
            if n_hand_tagged
            else None,
        }
    )
    return totals


def build_fleet(repos: list[tuple[str, Path]], doc: str) -> dict:
    """`repos` is (label, resolved_path) pairs — already resolved by
    `cli.py`'s `--repo` handling, one entry per `--repo` given on the command
    line, in the order given. Returns the JSON envelope shape directly;
    `cli.py`'s markdown renderer reads the same dict."""
    rows = [reconcile_one(label, path, doc) for label, path in repos]
    return {
        "schema_version": SCHEMA_VERSION,
        "doc": doc,
        "reading": [LEDGER_READING, BENCHMARK_READING],
        "rows": rows,
        "totals": _totals(rows),
    }
