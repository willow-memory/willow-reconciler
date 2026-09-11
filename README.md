# willow-reconciler

Deterministic idea-to-landing reconciler. It reads the fleet's own records — a
fleet doc (an "idea pile" like `willow-mcp/docs/ideas.md`) plus the target
repo's git history — and reports how much of what was proposed has actually
landed.

It answers one narrow question: of the numbered items in a fleet doc, how many
have **landed**, **partially landed**, or show **no evidence** of having
started. The answer comes from a fixed rule stack, never a model call.

- **stdlib-only** — no runtime dependencies (`pytest` is the only extra, for tests).
- **local-first** — reads a checkout that is a sibling of this package on disk;
  it will not walk outside the fleet tree.
- **deterministic** — every verdict is a regex or exact/whole-word match against
  doc text and git evidence already in hand. No model, so the same inputs always
  produce the same ledger.
- **read-only** — it only ever runs `git log`; it never touches the target
  repo's worktree or refs.

## Install

```sh
pip install -e ".[test]"
```

Requires Python 3.10+.

## Usage

The reconcile verb is `run`:

```sh
reconciler run --repo willow-mcp --doc docs/ideas.md
```

Flags (see `reconciler/cli.py`):

- `--repo` (required) — a repo directory that is a **sibling** of
  willow-reconciler's own checkout (the fleet layout: `willow-mcp`,
  `corpus-lens`, `willow-reconciler` all live under one parent). Not an
  arbitrary filesystem path, so a typo cannot walk this read-only tool out of
  the fleet tree.
- `--doc` (required) — the doc path, relative to `--repo`'s root.
- `--format markdown|json` — output shape (default `markdown`).
- `--validate` — additionally score this run's verdicts against the doc's own
  hand-tagged (✅/🟡) items and report the echo check plus the hold-out score
  (the honest Slice-0 acceptance number).

Every failure is a clear `error:` line on stderr with a non-zero exit — no
tracebacks.

### Writing the join key

The reconciler is only as good as the `Idea-Id` trailers in the history it
reads (see [`CONVENTION.md`](CONVENTION.md)), so three verbs exist to make
writing one the easy path rather than a thing you must remember:

```sh
# the exact trailer line for an item, by number or by text
reconciler id --repo willow-mcp --doc docs/ideas.md --num 42
reconciler id --repo willow-mcp --doc docs/ideas.md --grep "cross-repo trailer"

# install hooks that add the trailer from the branch name and reject a
# malformed one at commit time
reconciler install-hook --repo willow-mcp

# check every trailer in the history resolves to a real item (a CI gate)
reconciler verify --repo willow-mcp --doc docs/ideas.md
```

`id` prints the trailer and nothing else on stdout, so it pipes straight into
a commit message; which item it resolved to goes to stderr. It refuses an
ambiguous `--grep` rather than guessing — writing the wrong id is worse than
writing none, because a dangling trailer still reads as the strongest evidence
the classifier has, and `verify` is what catches that. `install-hook` is the
only verb that writes anything outside this repo; `run` and `verify` still
only ever call `git log`.

## Modules

- **parse** — turn a doc's text into numbered `Item` records; near-miss lines
  are surfaced as a `dropped` count, never silently absorbed.
- **ids** — derive `willow-ideas-<zero-padded-num>` from a doc entry's own
  number; recomputable from the doc alone, no migration table.
- **gitevidence** — read-only `git log` evidence for the inferred tier (one
  subprocess per run); asserts LANDED only from an `Idea-Id` trailer or a PR
  number git shows was actually merged. Scoped to commits reachable from the
  checkout's HEAD, so a trailer on an abandoned branch is not a landing.
- **classify** — the deterministic rule stack: one `classify_item` call, one
  `Verdict` out (explicit legend tag → inferred git evidence → not_started).
- **ledger** — aggregate verdicts into a per-doc ledger with a `headline` / `n`
  / `reading` result-shape, keeping the explicit/inferred split visible.
- **validate** — Slice 0's acceptance test as a library function: the trivial
  echo check plus the real hold-out score.
- **emit** — resolve which item a commit is landing (by number or text) and
  render its trailer line. A doc-side convenience only: it never reaches
  `classify`, so a loose match costs an ambiguity error, never a false verdict.
- **verify** — resolve every `Idea-Id` trailer in the history against the doc
  and report the ones that name nothing, so a typo'd or stale join key fails
  loudly instead of asserting LANDED forever.
- **hooks** — the `prepare-commit-msg` / `commit-msg` shell hooks and their
  installer; the one place this tool writes outside its own repo.
- **cli** — `run`, `id`, `verify`, `install-hook`.

## Why prospective, not retroactive

Slice 0 measured, on a held-out split of the *current* corpus with legend tags
stripped, a landing-recovery of **0.0**: no durable join key was ever written,
so deterministic inference recovers nothing from the existing history, and a
model-based guess would violate the cheapest-capable rule. The reconciler's fix
cannot look backward — it starts writing the key now (the `Idea-Id` commit
trailer) and grows useful as trailers accumulate.

See [`CONVENTION.md`](CONVENTION.md) for the `Idea-Id` trailer convention and
what counts as landing evidence.

## Where this goes next

[`docs/ideas.md`](docs/ideas.md) is this repo's own idea pile, written in the
shape the reconciler reads — so it doubles as a dogfooding fixture:

```sh
reconciler run --repo willow-reconciler --doc docs/ideas.md
```
