# Adversarial fixture corpus — idea pile

NOT a real idea pile. Every line here is a trap drawn from a finding one of
this repo's audits actually reproduced, plus the control cases that must keep
working. `tests/fixtures/corpus.py` builds the git history that pairs with it.

The point is that loosening the rule stack has to get past this file first.
Both audits so far found bugs that a fixture like this would have caught
before they shipped.

Legend: ✅ shipped · 🟡 partial · (untagged) proposed

1. a plainly landed idea — ✅ **shipped**: lives in `real.py`.
2. a half-landed idea — 🟡 **partial**: the primitive exists, the wiring does not.
3. THE CHAOS CANON: `whoami` develops doubt and refuses to answer. (Trap: the history contains a real commit touching whoami. A joke item naming a real tool is not a landing — this was ~0/11 precision before the first audit removed token matching.)
4. rework the ledger shape, folds in former #103, now retired. (Trap: #103 really was merged here as a pull request. An idea-number cross-reference uses the same `#N` shape a PR reference does and must never be conflated with one.)
5. waiting on PR #42 to land before this can start. (Trap: an ordinary commit ends its subject `(#42)`. That is the conventional-commit habit of naming an issue, not GitHub's squash-merge record — it asserted LANDED before the second audit.)
6. delivered in PR #77, which really did merge. (Control: a real merge commit, two parents, GitHub's own subject.)
7. landed via a trailer on merged history. (Control for rule 2a.)
8. half-landed via a trailer that says so. (Control: Idea-Status partial is data-driven, never hardcoded.)
9. a trailer for this exists ONLY on an abandoned branch. (Trap: `git log --all` read work that was deliberately never merged as a landing.)
10. This discusses tag history — ✅ marks were abused before, so audit them. (Trap: an ordinary sentence containing an em-dash and a marker is prose, not a legend tag.)
11. propose ✅/🟡 legend tags back into the doc. (Trap: a marker mid-prose is a mention. This is the exact item that scored LANDED against the reconciler's own pile.)
12. ✅ a leading marker needs no keyword — it is unambiguous on its own.
13.retired, and this line is deliberately malformed so it lands in `dropped`
14. tagged AND trailered — ✅ **shipped**: so the hold-out has something real to recover.
11. a duplicate item number, surfaced and never silently resolved.
