# Contributing

This repo (willow-memory/willow-reconciler) shares one working method with the
rest of the fleet, whether the contributor is a person or an agent.

## The method

- **One bite at a time.** A PR delivers one outcome.
- **Receipts, not claims.** The PR template asks for Evidence — check
  only what you actually ran, and state the result.
- **Verify in a clean environment.** If you touched dependencies, prove
  the suite in a clean environment before pushing.
- **Match the house style.** Read the surrounding code first — this is a
  stdlib-only, deterministic, read-only tool; keep it that way (no runtime
  dependencies, no model calls).

## Build and test

This package is stdlib-only; the only extra is `test` (pytest):

```sh
pip install -e ".[test]"
python -m pytest tests/ -q
```

Requires Python 3.10+. CI runs the suite on Linux across every Python minor
`pyproject.toml`'s classifiers declare (the matrix is derived from them, so
add a classifier to add a version), on Windows at the floor and ceiling of
that range, and runs `ruff check` and `ruff format --check` at the exact ruff
version pinned in `.github/workflows/tests.yml`. One aggregate `test` job
gates all of it and reads a skipped or cancelled leg as a failure. All of it
must be green before merge.

## The Idea-Id commit-trailer convention

This repo's own convention: a commit that lands an idea recorded in a fleet doc
carries an `Idea-Id: <corpus>-<docslug>-<num>` git trailer (add
`Idea-Status: partial` when a commit only partly lands it). It is the durable
join key the reconciler reads. Emit it when a commit lands an idea. See
[CONVENTION.md](CONVENTION.md) for the full rule and what counts as landing
evidence.

## Fleet conventions

`tests/test_fleet_conventions.py` holds this repo's release and CI wiring to
the fleet's convention set — which commit types release-please hides, which
workflows and config comments must exist, that this file names the test
command above. The rules are not restated there: `reconciler conventions
--json` publishes them from `reconciler/conventions.py`, their one home, and
the test reads that. To change a rule, change it there, with its source.

## Practical bits

- PRs use the closeout template (Bite / What was done / Evidence /
  Out of scope / Next bite).
- Security findings go through [SECURITY.md](SECURITY.md), not issues.

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and [SUPPORT.md](SUPPORT.md).
