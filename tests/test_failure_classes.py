"""Errors are an egress path too.

`GitLog.error` is spliced into a verdict's reason (classify.py) and into
verify.py's headline, both of which are emitted — a ledger this tool is
explicitly built to have pasted into docs, issues and PRs. A message built by
interpolating git's raw stderr, or a caught exception's raw text, can carry
whatever those happened to print — including an absolute path that names the
operating user and a sibling repo's name.

These tests hold the closed vocabulary to the one property that makes it
worth its cost: **no substring of the input can reach the output.**
"""
from __future__ import annotations

from reconciler.failure_classes import (
    FAILURE_CLASSES,
    FILE_FAILURE_CLASSES,
    UNKNOWN,
    classify,
    classify_file,
    describe,
)

# A representative git fatal message naming an absolute path that reveals the
# operating user and a sibling (client) repo's name.
LEAKY_GIT_STDERR = "fatal: cannot change to '/home/rudi/work/acme-corp/repo': Permission denied"
SECRETS_IN_IT = ("rudi", "acme-corp", "/home/")


# --- closed vocabulary ------------------------------------------------------

def test_every_classification_is_a_member_of_the_closed_list():
    samples = [
        LEAKY_GIT_STDERR,
        "fatal: not a git repository (or any of the parent directories): .git",
        "[Errno 2] No such file or directory: 'git'",
        "Command '['git', '-C', '/x', 'log']' timed out after 60 seconds",
        "fatal: your current branch 'main' does not have any commits yet",
        "something nobody has ever seen before",
        "",
        None,
    ]
    for s in samples:
        assert classify(s) in FAILURE_CLASSES, f"escaped the vocabulary: {s!r}"


def test_an_unrecognized_failure_degrades_to_unknown():
    assert classify("a brand new error nobody wrote a marker for") == UNKNOWN


def test_empty_and_none_are_unknown():
    assert classify("") == UNKNOWN
    assert classify(None) == UNKNOWN


# --- the load-bearing property: no input reaches the output ----------------
# If this section ever fails, the gate has been turned back into a redactor
# and the whole trade has been given away.

def test_the_path_leak_regression():
    out = describe("git log", LEAKY_GIT_STDERR)
    for secret in SECRETS_IN_IT:
        assert secret not in out
    assert out == "git log failed: permission denied accessing the repository"


def test_no_token_of_the_input_survives_classification():
    hostile = (
        "fatal: cannot change to '/home/sean-campbell/work/big-client-inc/repo': "
        "Permission denied (also mentions internal-project-codename and a "
        "SEAN-CAMPBELL-TOKEN-xxx-EXAMPLE-xxx)"
    )
    out = describe("git log", hostile)
    for token in ("sean-campbell", "big-client-inc", "internal-project-codename",
                  "SEAN-CAMPBELL-TOKEN", "/home/"):
        assert token not in out


def test_output_is_exactly_operation_plus_one_class():
    for sample in (LEAKY_GIT_STDERR, "not a git repository", "anything at all"):
        out = describe("git log", sample)
        assert out.startswith("git log failed: ")
        assert out[len("git log failed: "):] in FAILURE_CLASSES


# --- classification accuracy -------------------------------------------------
# Has to be right often enough to be worth the lost detail — otherwise every
# failure reads 'unknown failure' and operators stop reading.

def test_real_git_failures_classify():
    cases = [
        (LEAKY_GIT_STDERR, "permission denied accessing the repository"),
        ("fatal: not a git repository (or any of the parent directories): .git",
         "not a git repository"),
        ("[Errno 2] No such file or directory: 'git'", "the git binary is missing"),
        ("fatal: your current branch 'main' does not have any commits yet",
         "the repository has no commits yet"),
        ("Command '['git', '-C', '/x', 'log']' timed out after 60 seconds",
         "the git command timed out"),
    ]
    for stderr, expected in cases:
        assert classify(stderr) == expected, stderr


# --- marker ordering ---------------------------------------------------------
# `_MARKERS` is first-match-wins, and a broad marker ahead of a more specific
# one produces a WRONG class rather than merely `unknown failure` — worse,
# because a wrong class misleads rather than merely saying less.
#
# The trap here: the stdlib's own "the git binary is missing" message and
# git's UNRELATED "target directory vanished" fatal both contain the exact
# phrase "no such file or directory" (Python: `[Errno 2] No such file or
# directory: 'git'`; git: `fatal: cannot change to '<path>': No such file or
# directory`). A bare "no such file or directory" marker would misreport a
# vanished-directory race as "the git binary is missing".

def test_a_missing_directory_is_not_reported_as_a_missing_git_binary():
    # No quoted 'git' in this message — it must NOT match the
    # git-binary-missing marker, which requires that quoting.
    msg = "fatal: cannot change to '/some/repo': No such file or directory"
    assert classify(msg) == UNKNOWN


def test_the_stdlib_missing_executable_message_is_still_classified():
    assert classify("[Errno 2] No such file or directory: 'git'") == "the git binary is missing"


def test_permission_denied_is_unaffected_by_the_reorder():
    assert classify("fatal: cannot change to '/x': Permission denied") == \
        "permission denied accessing the repository"


# ── file-read vocabulary ─────────────────────────────────────────────────────
# `cli.py`'s `--doc` read echoed the OSError text, which carries the RESOLVED
# absolute path even though the caller only ever types a sibling name — so it
# named the operating user and the fleet layout. Same class as the git-stderr
# leak, different door.

def test_the_resolved_path_never_reaches_the_output():
    hostile = "[Errno 2] No such file or directory: '/home/sean-campbell/work/acme/README.md'"
    out = classify_file(hostile)
    for token in ("/home/", "sean-campbell", "acme", "Errno", "README.md"):
        assert token not in out
    assert out == "no such file"


def test_real_oserror_shapes_classify():
    cases = [
        ("[Errno 2] No such file or directory: '/x/y.md'", "no such file"),
        ("[Errno 13] Permission denied: '/x/y.md'", "permission denied"),
        ("[Errno 21] Is a directory: '/x'", "the path is a directory"),
        ("'utf-8' codec can't decode byte 0xff in position 0: invalid start byte",
         "the file is not valid UTF-8"),
        ("something nobody has a marker for", "unknown failure"),
        ("", "unknown failure"),
        (None, "unknown failure"),
    ]
    for text, expected in cases:
        assert classify_file(text) == expected, text
        assert classify_file(text) in FILE_FAILURE_CLASSES


def test_git_and_file_vocabularies_stay_separate():
    # a doc-read permission error must NOT be reported in the git vocabulary's
    # repository-specific wording
    text = "[Errno 13] Permission denied: '/x/y.md'"
    assert classify_file(text) == "permission denied"
    assert classify(text) == "permission denied accessing the repository"
