"""C4-tests-yml-reconciler — the CI floor's shape, held rather than trusted.

`.github/workflows/tests.yml` is the fleet CI floor (fleet plan decision 5).
Nothing runs it locally, so its promises are checked here by reading it:

* the Python matrix is DERIVED from pyproject's classifiers — the `versions`
  job's script, run here on a planted pyproject, yields exactly the
  classifier minors, and the Linux and Windows legs take their matrix from
  that job's outputs rather than from a list typed into the YAML;
* ruff is pinned to an exact version, and both `ruff check` and
  `ruff format --check` run;
* the aggregate `test` job `needs:` every other job, runs `if: always()`,
  and rejects any result that is not `success` — so a skipped or cancelled
  leg fails it, said in those words.

Every helper is a regex over the workflow text (stdlib has no YAML parser
and this repo adds no dependency for its tests), and every one is planted:
shown, in this same file, to report a workflow built to violate it. The
meta-scan (`tests/test_scans_fire.py`) requires exactly that.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/tests.yml"
PYPROJECT = "pyproject.toml"

#: The job ids the floor requires, and the one that gates them.
DERIVE_JOB = "versions"
LINUX_JOB = "test-matrix"
WINDOWS_JOB = "test-windows"
LINT_JOB = "lint"
GATE_JOB = "test"

_CLASSIFIER_MINOR = re.compile(r'"Programming Language :: Python :: 3\.(\d+)"')
_JOB_HEADER = re.compile(r"^  ([A-Za-z0-9_-]+):[ \t]*$", re.MULTILINE)
_HEREDOC = re.compile(r"python - <<'PY'\n(.*?)\n\s*PY\s*$", re.DOTALL | re.MULTILINE)
#: Every `pip install ruff<spec>` in the lint job; the spec is what follows
#: the name, empty for a bare `pip install ruff`.
_RUFF_INSTALL = re.compile(r"pip install ruff(\S*)")
_EXACT_PIN = re.compile(r"^==(\d+\.\d+\.\d+)$")
_NEEDS = re.compile(r"^\s+needs:\s*\[([^\]]*)\]", re.MULTILINE)
_IF_ALWAYS = re.compile(r"^\s+if:\s*always\(\)\s*$", re.MULTILINE)
_REJECTS_NON_SUCCESS = re.compile(r"""!=\s*["']success["']""")
_DERIVED_MATRIX = re.compile(
    r"python-version:\s*\$\{\{\s*fromJSON\(needs\."
    + DERIVE_JOB
    + r"\.outputs\.(\w+)\)\s*\}\}"
)


def _classifier_minors(pyproject_text: str) -> list[str]:
    """`["3.10", "3.11", ...]` from pyproject's classifiers, in version order."""
    return [
        f"3.{m}"
        for m in sorted({int(m) for m in _CLASSIFIER_MINOR.findall(pyproject_text)})
    ]


def _jobs(workflow_text: str) -> list[str]:
    """Every job id under `jobs:`, in file order."""
    _, _, tail = workflow_text.partition("\njobs:\n")
    return _JOB_HEADER.findall(tail)


def _job_block(workflow_text: str, job: str) -> str:
    """The text of one job, from its header to the next job's."""
    _, _, tail = workflow_text.partition("\njobs:\n")
    m = re.search(rf"^  {re.escape(job)}:[ \t]*$", tail, re.MULTILINE)
    assert m, f"no job `{job}` in {WORKFLOW}"
    rest = tail[m.end() :]
    nxt = _JOB_HEADER.search(rest)
    return rest[: nxt.start()] if nxt else rest


def _derivation_script(workflow_text: str) -> str:
    """The `versions` job's embedded Python, dedented, ready to run."""
    m = _HEREDOC.search(_job_block(workflow_text, DERIVE_JOB))
    assert m, (
        f"job `{DERIVE_JOB}` must derive the matrix in a `python - <<'PY'` heredoc"
    )
    return textwrap.dedent(m.group(1))


def _derive_versions(workflow_text: str, pyproject_text: str, workdir: Path) -> dict:
    """Run the workflow's own derivation script against `pyproject_text` the
    way the runner would, and return what it wrote to GITHUB_OUTPUT as a
    dict — or `{"error": <stderr>}` when it refused."""
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / PYPROJECT).write_text(pyproject_text, encoding="utf-8")
    output = workdir / "github_output"
    output.write_text("", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-c", _derivation_script(workflow_text)],
        cwd=workdir,
        env={**os.environ, "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()}
    lines = output.read_text(encoding="utf-8").splitlines()
    return {k: json.loads(v) for k, v in (ln.split("=", 1) for ln in lines if ln)}


def _matrix_source(workflow_text: str, job: str) -> str | None:
    """Which `versions` output a job's matrix is taken from, or None when the
    job types its own list."""
    m = _DERIVED_MATRIX.search(_job_block(workflow_text, job))
    return m.group(1) if m else None


def _ruff_pin(workflow_text: str) -> str | None:
    """The exact ruff version the lint job installs, or None if it is not
    pinned to one (`ruff`, `ruff>=`, `ruff~=` all read as unpinned)."""
    specs = _RUFF_INSTALL.findall(_job_block(workflow_text, LINT_JOB))
    pins = [_EXACT_PIN.match(spec) for spec in specs]
    if specs and all(pins):
        return pins[0].group(1)
    return None


def _lint_runs_both_checks(workflow_text: str) -> bool:
    block = _job_block(workflow_text, LINT_JOB)
    return "ruff check" in block and "ruff format --check" in block


def _gate_offenders(workflow_text: str) -> list[str]:
    """Everything wrong with the aggregate gate, in words. Empty when it
    `needs:` every other job, runs `if: always()`, and rejects any result
    that is not `success`."""
    jobs = _jobs(workflow_text)
    if GATE_JOB not in jobs:
        return [f"no `{GATE_JOB}` job"]
    block = _job_block(workflow_text, GATE_JOB)
    offenders = []
    m = _NEEDS.search(block)
    needed = {n.strip() for n in m.group(1).split(",") if n.strip()} if m else set()
    missing = [j for j in jobs if j != GATE_JOB and j not in needed]
    if missing:
        offenders.append(f"`{GATE_JOB}` does not need: {missing}")
    if not _IF_ALWAYS.search(block):
        offenders.append(f"`{GATE_JOB}` lacks `if: always()`, so a failed leg skips it")
    if not _REJECTS_NON_SUCCESS.search(block):
        offenders.append(
            f"`{GATE_JOB}` does not reject `!= success` — a skipped or cancelled leg "
            "would pass it"
        )
    return offenders


# ── the real workflow ───────────────────────────────────────────────────────


def _real() -> tuple[str, str]:
    return (
        (REPO_ROOT / WORKFLOW).read_text(encoding="utf-8"),
        (REPO_ROOT / PYPROJECT).read_text(encoding="utf-8"),
    )


def test_the_floor_has_every_leg():
    workflow, _ = _real()
    assert set(_jobs(workflow)) == {
        DERIVE_JOB,
        LINUX_JOB,
        WINDOWS_JOB,
        LINT_JOB,
        GATE_JOB,
    }


def test_the_matrix_is_the_classifiers(tmp_path):
    """The derivation script, run on the real pyproject, yields exactly the
    classifier minors; and both test legs take their matrix from it."""
    workflow, pyproject = _real()
    minors = _classifier_minors(pyproject)
    assert len(minors) >= 2, "the floor needs a floor and a ceiling to name"
    derived = _derive_versions(workflow, pyproject, tmp_path / "real")
    assert derived["versions"] == minors
    assert derived["floor_ceiling"] == [minors[0], minors[-1]]
    assert _matrix_source(workflow, LINUX_JOB) == "versions"
    assert _matrix_source(workflow, WINDOWS_JOB) == "floor_ceiling"


def test_ruff_is_pinned_to_an_exact_version_and_both_checks_run():
    workflow, _ = _real()
    assert _ruff_pin(workflow) is not None
    assert _lint_runs_both_checks(workflow)


def test_the_gate_needs_every_leg_and_rejects_anything_but_success():
    workflow, _ = _real()
    assert _gate_offenders(workflow) == []


# ── the plants ──────────────────────────────────────────────────────────────


def _planted_workflow(
    *, gate: str, lint_install: str = "pip install ruff==1.2.3"
) -> str:
    """A tests.yml with the real shape and a substitutable gate and pin."""
    return (
        textwrap.dedent(
            f"""\
        name: Tests
        on:
          push:
            branches: [main]
        jobs:
          versions:
            runs-on: ubuntu-latest
            steps:
              - run: |
                  python - <<'PY'
                  import json, os, re, sys
                  text = open("pyproject.toml", encoding="utf-8").read()
                  minors = sorted({{int(m) for m in re.findall(r'"Programming Language :: Python :: 3\\.(\\d+)"', text)}})
                  if not minors:
                      sys.exit("no classifiers")
                  versions = [f"3.{{m}}" for m in minors]
                  with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
                      out.write(f"versions={{json.dumps(versions)}}\\n")
                      out.write(f"floor_ceiling={{json.dumps([versions[0], versions[-1]])}}\\n")
                  PY
          test-matrix:
            needs: [versions]
            strategy:
              matrix:
                python-version: ${{{{ fromJSON(needs.versions.outputs.versions) }}}}
          test-windows:
            needs: [versions]
            strategy:
              matrix:
                python-version: ["3.10", "3.14"]
          lint:
            steps:
              - run: {lint_install}
              - run: ruff check .
              - run: ruff format --check .
        """
        )
        + gate
    )


GOOD_GATE = """\
  test:
    needs: [versions, test-matrix, test-windows, lint]
    if: always()
    steps:
      - run: |
          python - <<'PY'
          import json, os, sys
          bad = {j: i["result"] for j, i in json.loads(os.environ["NEEDS"]).items()
                 if i["result"] != "success"}
          sys.exit(1 if bad else 0)
          PY
"""


def test_the_derivation_catches_a_planted_pyproject_with_other_classifiers(tmp_path):
    """Planted: a pyproject whose classifiers say 3.9 and 3.13 — the script
    must report those, and nothing else, so a version added or dropped in
    pyproject changes the matrix by itself. And one with no classifiers at
    all must be refused, not silently tested on nothing."""
    workflow = _planted_workflow(gate=GOOD_GATE)
    other = (
        'classifiers = [\n  "Programming Language :: Python :: 3.13",\n'
        '  "Programming Language :: Python :: 3.9",\n]\n'
    )
    derived = _derive_versions(workflow, other, tmp_path / "other")
    assert derived == {"versions": ["3.9", "3.13"], "floor_ceiling": ["3.9", "3.13"]}
    assert _classifier_minors(other) == ["3.9", "3.13"]
    refused = _derive_versions(
        workflow,
        'classifiers = ["Programming Language :: Python :: 3"]\n',
        tmp_path / "none",
    )
    assert "error" in refused


def test_the_matrix_source_check_fires_on_a_planted_literal_matrix():
    """Planted: a Windows leg that types its own `["3.10", "3.14"]` instead
    of reading the derived floor and ceiling — the drift the derivation
    exists to prevent, reported as no source at all."""
    workflow = _planted_workflow(gate=GOOD_GATE)
    assert _matrix_source(workflow, LINUX_JOB) == "versions"
    assert _matrix_source(workflow, WINDOWS_JOB) is None


def test_the_pin_check_catches_a_planted_unpinned_ruff():
    """Planted: `pip install ruff` and `pip install ruff>=0.16` — both read
    as unpinned; only an exact `==` counts."""
    assert _ruff_pin(_planted_workflow(gate=GOOD_GATE)) == "1.2.3"
    assert (
        _ruff_pin(_planted_workflow(gate=GOOD_GATE, lint_install="pip install ruff"))
        is None
    )
    assert (
        _ruff_pin(
            _planted_workflow(gate=GOOD_GATE, lint_install="pip install ruff>=0.16")
        )
        is None
    )
    assert _lint_runs_both_checks(_planted_workflow(gate=GOOD_GATE))


def test_the_gate_check_fires_on_a_planted_gate_that_accepts_a_skipped_leg():
    """Planted three ways. A gate that only looks for `failure` passes a
    skipped or cancelled leg; a gate missing `if: always()` is itself skipped
    when a leg fails, which GitHub reads as satisfied; a gate that forgets a
    leg in `needs:` never sees that leg at all."""
    assert _gate_offenders(_planted_workflow(gate=GOOD_GATE)) == []

    failure_only = GOOD_GATE.replace(
        'i["result"] != "success"', 'i["result"] == "failure"'
    )
    assert any(
        "skipped or cancelled" in o
        for o in _gate_offenders(_planted_workflow(gate=failure_only))
    )

    no_always = GOOD_GATE.replace("    if: always()\n", "")
    assert any(
        "always()" in o for o in _gate_offenders(_planted_workflow(gate=no_always))
    )

    forgets_lint = GOOD_GATE.replace("test-windows, lint]", "test-windows]")
    assert any(
        "['lint']" in o for o in _gate_offenders(_planted_workflow(gate=forgets_lint))
    )

    no_gate = _planted_workflow(gate="")
    assert _gate_offenders(no_gate) == [f"no `{GATE_JOB}` job"]
    assert _jobs(no_gate) == [DERIVE_JOB, LINUX_JOB, WINDOWS_JOB, LINT_JOB]
