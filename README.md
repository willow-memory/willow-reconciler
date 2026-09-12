# willow-reconciler

Deterministic idea-to-landing reconciler. It reads the fleet's own records — a
fleet doc (an "idea pile" like `willow-mcp/docs/ideas.md`) plus the target
repo's git history — and reports how much of what was proposed has actually
landed.

It answers one narrow question: of the numbered items in a fleet doc, how many
have **landed**, **partially landed**, or show **no evidence** of having
started. The answer comes from a fixed rule stack, never a model call.

- **stdlib-only** — no runtime dependencies (`pytest` is the only extra, for tests).
- **local-first** — reads a real git checkout on disk, resolved as a path you
  give it or a bare name found beside your own checkout; it never fetches or
  clones anything.
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

- `--repo` (required) — either a **path** to the repo directory (absolute, or
  relative to your current directory), used as-is, or a bare **name**,
  resolved in order (first hit, containing `.git`, wins): a sibling of your
  own checkout's root, a sibling of your current directory, or a sibling of
  willow-reconciler's own checkout (the fleet layout — `willow-mcp`,
  `corpus-lens`, `willow-reconciler` all under one parent — is recommended,
  not required; it is what still works from a source checkout with nothing
  else set up). This is what lets a `pip install`ed `reconciler` find a repo
  at all: run from inside (or beside) the checkout you mean to reconcile, or
  just pass its path.
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
- **benchmark** — splits recovered items by whether their trailer was written
  independently of the pile, so a self-fulfilling score cannot be quoted as
  recall.
- **emit** — resolve which item a commit is landing (by number or text) and
  render its trailer line. A doc-side convenience only: it never reaches
  `classify`, so a loose match costs an ambiguity error, never a false verdict.
- **verify** — resolve every `Idea-Id` trailer in the history against the doc
  and report the ones that name nothing, so a typo'd or stale join key fails
  loudly instead of asserting LANDED forever.
- **hooks** — the `prepare-commit-msg` / `commit-msg` shell hooks and their
  installer; the one place this tool writes outside its own repo.
- **cli** — `run`, `id`, `verify`, `install-hook`.

## What the numbers mean

`reconciler benchmark` answers the question the hold-out score cannot:

```sh
reconciler benchmark --repo willow-mcp --doc docs/ideas.md
```

A trailer written by the same commit that added the doc's own tag is
**self-witnessed** — the author had both facts in hand and wrote them
together, so recovering one from the other demonstrates the pipeline and
nothing about recall. A trailer written by a commit that never touched the
pile is **independent**: the key came from someone landing work, the tag from
someone curating, as two separate acts.

Only `independent_recovery_rate` may be quoted as a capability result. On this
repo today it is **0.0** against a raw recovery of 0.9 — every trailer here was
written alongside the tag it recovers. That is the expected shape for a
convention that has been demonstrated but not yet lived in, and the fix is
time, not code.

## The adversarial corpus

`tests/fixtures/` carries a small idea pile plus a scripted git history in
which every line is a trap one of this repo's audits actually reproduced — a
joke item naming a real tool, an idea cross-reference shaped like a PR number,
a conventional-commit subject ending `(#42)`, a trailer on a branch that was
never merged, a legend marker sitting in ordinary prose. `EXPECTED` in
`tests/fixtures/corpus.py` is the ground truth, hand-written from the traps'
intent rather than generated from the classifier, so it cannot drift into
agreeing with a regression.

Loosening the rule stack has to get past that file first. Both audits so far
found bugs a fixture like this would have caught before they shipped.

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
