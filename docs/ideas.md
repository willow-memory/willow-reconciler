# willow-reconciler — idea pile

This repo's own idea pile, written in the same shape willow-reconciler reads:
top-level `N. ` items, optional legend tags, stable numbers.

It is also a dogfooding fixture. The tool can be pointed at this file:

```sh
reconciler run --repo willow-reconciler --doc docs/ideas.md --validate
```

Legend: ✅ shipped · 🟡 partial · (untagged) proposed

**Numbers are permanent join keys.** `reconciler/ids.py` derives
`willow-ideas-<num>` from the number written on the line, so a number is an
identity, not an ordinal. Never renumber; never write a markdown-auto-numbered
list (`1.` repeated) here — retire a number instead and leave the gap.

---

## A. Close the write-side loop

The tool's whole thesis is that `Idea-Id` trailers accumulate from today
forward (`CONVENTION.md`). Nothing in this repo currently helps anyone *emit*
one. Until that changes, the reconciler's inferred tier has no fuel and the
measured recovery stays at the Slice-0 0.0 forever. This section is the
highest-leverage work in the pile.

1. ✅ **shipped**: `reconciler id`. Print the exact trailer line for one item, ready to paste into a commit message. One function on top of `ids.idea_id`; removes the last excuse for not writing the trailer.
2. ✅ **shipped**: folded into `reconciler id --grep` rather than a second verb. Find the item you are actually landing by substring/word match against item text, then emit its trailer. Search is a doc-side convenience, not evidence, so it keeps the classifier's precision rules untouched.
3. ✅ **shipped**: `reconciler install-hook`. Writes a `prepare-commit-msg` git hook into the target repo that appends an `Idea-Id` trailer when the branch name or commit body names an item, and a `commit-msg` hook that rejects a malformed one. Opt-in, and the only part of this tool that ever writes outside its own repo, so it must be an explicit verb rather than a side effect.
4. ✅ **shipped**: `reconciler verify`. Resolve every `Idea-Id` trailer in history against the current doc and fail on any that names an item the doc does not contain. A typo'd or stale id is worse than no id: it is a false join key that the classifier will assert LANDED from.
5. 🟡 **partial**: `.github/workflows/trailers.yml` runs idea 4 on every PR; the PR comment naming which items the commits claim to land is still open. Turns the convention into something CI enforces rather than something a CONVENTION.md asks for politely.

## B. Evidence tiers that stay deterministic

The audit's lesson was that a bare mention is not evidence — only a signal that
resolves to something real. Each item here adds a *resolvable* signal, never a
looser match.

6. Release-aware landing: when a commit carrying a trailer is reachable from a release tag, report `landed (released in v0.2.0)` rather than a bare `landed`. `git log` already loads once; this is one extra read-only `git tag --contains`-shaped query.
7. Issue-linked evidence: a merged PR whose body says `Closes #N`, where item text names issue #N as an issue. Same disambiguation discipline as `PR_MENTION_RE` — the word must be there, the number alone is never enough.
8. Cross-repo trailer search. An idea filed in `willow-mcp/docs/ideas.md` frequently lands in a sibling repo, and `gitevidence` only ever reads the target repo, so that landing is invisible today. Load each fleet sibling's log once and search all of them for the id.
9. Optional doc-side explicit ids (`<!-- idea-id: willow-ideas-042 -->`) as an override for the derived number. Positional ids are cheap and migration-free, but they are only stable while the author keeps numbers stable by hand; an explicit id is the escape hatch for a doc that has already been renumbered.
10. `reconciler doctor --doc D` — flag the doc hygiene failures that silently destroy join keys: an all-`1.` markdown-autonumbered list (every item collapses to `willow-ideas-001`), duplicate numbers, and near-miss lines. `parse.py` already surfaces `dropped` and `ledger.py` already surfaces `duplicate_nums`; this gives them a verb and a non-zero exit.

## C. Time, trend, and the claim that needs proving

11. `--as-of <rev|date>` — rebuild the ledger from history as it stood at a past commit. Nearly free: the full log is already in memory, so this is a filter, not a second subprocess.
12. `reconciler trend` — the ledger at N points in time, so "grows useful as trailers accumulate" becomes a curve rather than an assertion. This is the repo's central claim and nothing currently measures it.
13. A committed `BENCHMARK.md` regenerated on release, recording the hold-out recovery rate per version. The honesty machinery in `validate.py` is excellent and currently produces a number nobody records.

## D. Scope past one doc, one repo

14. ✅ **shipped**: as `reconciler fleet --repo A --repo B ... --doc D` (repeatable `--repo`, not a `fleet.toml` + `--all` flag — fewer moving parts for the same need) producing one table across repos: items parsed, dropped, explicit/inferred landed and partial, none, plus each repo's `independent_recovery_rate`/`recovery_rate` and a `totals` row rated over the POOLED counts. Every invocation before this one was one doc in one repo.
15. Per-section ledgers. An idea pile with `## ` headings (this file included) has meaningful sub-piles; `parse.py` currently flattens the whole doc. Tracking the enclosing heading per item is a one-field change to `Item` and makes the ledger readable at the scale of a 123-item doc.

## E. Output and the loop back to the doc

16. `reconciler annotate --repo R --doc D` — propose legend tags back into the doc for items with a resolved trailer. Dry-run by default, printing a diff; `--write` gated behind a clean worktree. This closes idea → commit → doc, and it is the one feature that would let the explicit tier be *maintained* rather than hand-curated.
17. Exit-code semantics for gating (`--fail-on-dropped`, `--fail-on-duplicate-nums`), so doc hygiene can be a CI job rather than a thing someone reads.

## F. Keeping the measurement honest

18. ✅ **shipped**: `tests/fixtures/` + `tests/test_corpus.py`. An in-repo adversarial fixture corpus — a small doc plus a synthetic git history containing exactly the traps the Opus audit found: joke items naming real tools, `former #103` cross-references, bare `#N` issue mentions. Any future loosening of the rule stack then has to pass them.
19. ✅ **shipped**: the behaviours now run everywhere against the fixture; the willow-mcp tests stay as a supplement that adds the one thing a fixture cannot fake, the real doc's real shape. Make the five real-corpus tests run. `tests/test_parse.py` and `tests/test_validation.py` skip whenever the `willow-mcp` sibling is absent — which is *always* on a CI runner, so CI has never once executed them. A committed fixture corpus (idea 18) makes them real; until then the matrix is green on tests that never ran.
20. 🟡 **partial**: `test_no_item_is_ever_falsely_landed` is the precision invariant and fails naming the offending item, but there is still no harness REPORTING rates over time. A precision/recall harness over the fixture corpus, reporting both over-claim and under-claim rates. The current acceptance number is recall-only; the audit's actual finding was a *precision* failure (~0/11), and nothing in the repo would catch that regression today.

## G. Hygiene

21. `ruff` + `mypy` in CI. The code is already typed and consistently styled; nothing enforces that it stays so.
22. Pluggable doc dialects. `parse.py` accepts exactly one shape (`N. ` at column 0); `- ` bullets and nested items are common in fleet docs and are currently invisible rather than dropped.
23. A `--repo-path` escape hatch, explicitly documented as unsafe, for reconciling a repo outside the fleet sibling layout. The sibling-only rule is a good default and a hard wall for anyone whose checkout is laid out differently.
24. ✅ **shipped**: `classify._TAG_ANCHOR`. Anchor the legend-tag regexes. Found by pointing this tool at this very file: `classify._SHIPPED_RE` matches a shipped-marker anywhere on the line, so item 16 — which merely *discussed* legend tags — was classified LANDED with `evidence_kind=explicit`. A tag is a tag only at a defined position (leading the item text, or trailing after a ` — ` separator); a marker inside prose is a mention, which the audit already established is not evidence. Same class of bug as the one the audit found in the inferred tier, still live in the explicit tier.
25. ✅ **shipped**: `reconciler benchmark`. A capability benchmark on ORGANICALLY accumulated trailers. The hold-out score is honest about its method but says nothing about real recall while every trailer it reads was written in the same commit as the doc tag it recovers — that measures plumbing, not capability. The number only becomes evidence once trailers arrive from commits that were not also editing the pile, so the benchmark has to record who wrote each trailer and when, relative to the tag.
26. Recover a landing signal for squash-merge repos. Rule 2b now requires a real merge commit (two or more parents), which is correct — a subject ending `(#N)` is the ordinary habit of naming an issue and produced a reproducible false LANDED — but it leaves repos that squash-merge with no PR-shaped evidence at all. Anything that replaces it has to resolve to something real: GitHub's merge metadata, or a `Merged-PR` trailer written at merge time, not another subject-shape guess.
27. Decide what `run` should do about evidence on unmerged branches. Evidence is now scoped to commits reachable from the checkout's HEAD, because `--all` let a trailer on an abandoned branch assert LANDED. That is the right default, but it also means an idea landing on a feature branch reads as `not_started` until merge. A `--ref` flag, or an explicitly-labelled `in_flight` verdict distinct from both, would report the real state rather than rounding it down.
28. ✅ **shipped**: `gitevidence.trailer_block`. Read trailers only from the trailer block. They were matched anywhere in a commit message, so a commit that DISCUSSED the convention was indistinguishable from one that CARRIED it — prose explaining `Idea-Status: partial`, or a revert quoting the original message, read as real evidence. Found when this repo's own commit-msg hook rejected a commit whose prose started a line that way. Mention-is-not-evidence, a third time, now in the evidence layer. git proper counts only the final paragraph, which would discard every trailer written so far, so the rule walks back over consecutive all-trailer-shaped paragraphs instead.
29. ✅ **shipped**: `--repo` resolves as a path, or a bare name beside the caller's own checkout, not just beside the installed package. `_fleet_root` (this package's own checkout) was the ONLY candidate a bare name could resolve against — from a `pip install`ed copy that directory is `site-packages`, which is never a real repo, so `reconciler run --repo willow-mcp ...` errored from every directory outside a source checkout of this repo, contradicting the README's own `pip install` instructions. Fixed by accepting `--repo` as a literal path (used as-is), and by trying, before the package-sibling fallback, a sibling of the caller's own enclosing git checkout and a sibling of the caller's cwd. `install-hook` follows the same rule.
30. ✅ **shipped**: `reconciler conventions [--json]`. The fleet plan's decision 4: every repo carries a `tests/test_fleet_conventions.py`, and the rule set it checks has ONE home — the reconciler publishes it, consumers read it. `reconciler/conventions.py` holds the data (hidden commit types, release-cutting types, the files required wherever `release-please.yml` arms auto-merge or a numbered pile exists, the config comments that must sit beside the hidden set, that CONTRIBUTING names the test command, the `Idea-Id` trailer) with one source line per rule naming the incident or decision it came from; the verb renders it as markdown or as a `willow-fleet-conventions/1` JSON document. This repo's own `tests/test_fleet_conventions.py` consumes it, every scan planted. Bumps the schema only on a field removal or meaning change, never an addition.
