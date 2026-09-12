"""Closed-vocabulary failure reporting for git's own stderr and for the
exceptions raised trying to invoke it.

THE LEAK THIS CLOSES. `GitLog.load` stores git's raw stderr and the raw text
of a caught `OSError`/`subprocess.SubprocessError` on `GitLog.error`, and that
field is spliced verbatim into a verdict's `reason` (`classify.py`) and into
`verify.py`'s headline — both of which are emitted, and this tool's ledger is
explicitly meant to be pasted into docs, issues and PRs. Git's stderr routinely
carries an absolute path this repo did not choose to reveal:

    fatal: cannot change to '/home/rudi/work/acme-corp/repo': Permission denied

— naming the operating user and a sibling repo's name in a published artifact.
This tool touches no remote and handles no credentials, so there is no
credential exposure here (unlike the sibling case this pattern was built for);
the exposure is local paths and directory layout landing somewhere shared.
Worth fixing because of *where it lands*, not because of severity.

THE RULE, ported from corpus-lens's `corpuslens/failure_classes.py` (Apache-2.0,
same license), which itself borrows redential-cli's `NetworkError` contract:
a failure in foreign code (here, the `git` binary and the OS calls used to
launch it) is reported as **one phrase from the closed list below, and nothing
else**. Reading the foreign text to classify it is fine; *interpolating* it is
what leaks. `classify()` takes the text and returns only a member of
`FAILURE_CLASSES` — there is no code path by which its input reaches its
output.

WHY A CLOSED LIST AND NOT A REDACTOR. A redactor has to enumerate what is
sensitive and is wrong the first time git prints a path in a shape nobody
predicted. A closed vocabulary inverts it: the only strings this function can
emit are the ones written here, so an unanticipated path or username cannot
escape by default. An unrecognized failure degrades to `UNKNOWN`, which says
less than an operator might want and cannot leak.

WHAT THIS COSTS, STATED PLAINLY. Debuggability. "permission denied accessing
the repository" is genuinely less useful than git's own sentence with its
exact path, and an operator debugging this will sometimes have to re-run
`git log` on the repo directly. That is the intended trade and it must not be
quietly undone by adding "... (detail: {stderr})" to a message here later.

The failure classes here are git-shaped, not psql/sqlite-shaped: this module
does not carry corpus-lens's database markers, which have no meaning for a
`git log` invocation.
"""

from __future__ import annotations

#: The closed vocabulary. A caller may emit these strings and no others.
FAILURE_CLASSES: frozenset[str] = frozenset(
    {
        "not a git repository",
        "the repository has no commits yet",
        "the git binary is missing",
        "permission denied accessing the repository",
        "the git command timed out",
        "unknown failure",
    }
)

UNKNOWN = "unknown failure"

#: (marker, class). Markers are matched case-insensitively against the foreign
#: text; the FIRST match wins, so more specific markers come first. Markers are
#: only ever compared against, never emitted.
#:
#: ORDERING TRAP (checked deliberately, see
#: tests/test_failure_classes.py::MarkerOrderingTests): git's OWN "git binary
#: is missing" signal, as raised by the stdlib when `subprocess.run` cannot
#: exec 'git' at all, reads `[Errno 2] No such file or directory: 'git'` — and
#: git ITSELF uses the exact same "No such file or directory" wording for an
#: unrelated fatal ("cannot change to '<path>': No such file or directory",
#: when the target directory vanishes between this tool's own `is_dir()` check
#: and the subprocess call). A bare "no such file or directory" marker would
#: misreport that race as "the git binary is missing" — a WRONG class, worse
#: than `unknown failure` because it misleads about what actually failed. So
#: the marker below requires the quoted `'git'` that only the interpreter's
#: own missing-executable message contains; the generic phrase alone is
#: deliberately absent from this table and falls through to `unknown failure`.
_MARKERS: tuple[tuple[str, str], ...] = (
    ("permission denied", "permission denied accessing the repository"),
    ("no such file or directory: 'git'", "the git binary is missing"),
    ("not a git repository", "not a git repository"),
    ("does not have any commits yet", "the repository has no commits yet"),
    ("timed out", "the git command timed out"),
)


def classify(foreign_text: str | None) -> str:
    """A member of `FAILURE_CLASSES` describing `foreign_text`.

    The input is read and never echoed: every return value is a literal from
    `_MARKERS`/`UNKNOWN` above, so no substring of the argument (an absolute
    path, a username, a sibling repo name) can reach the result. That property
    is the whole point of this function and is asserted directly in
    `tests/test_failure_classes.py`.
    """
    if not foreign_text:
        return UNKNOWN
    haystack = foreign_text.lower()
    for marker, klass in _MARKERS:
        if marker in haystack:
            return klass
    return UNKNOWN


def describe(operation: str, foreign_text: str | None) -> str:
    """A complete, safe one-line failure message.

    `operation` is a short phrase THIS REPO authors (e.g. "git log") — never
    a value read from the environment, a path, or git's own output.
    """
    return f"{operation} failed: {classify(foreign_text)}"


#: A SEPARATE vocabulary for reading a file, deliberately not folded into the
#: git table above. The git phrases are context-specific ("permission denied
#: accessing the repository"), and reusing them for a doc read would report a
#: correct class in the wrong words — the same misleading-but-confident failure
#: the ordering trap above exists to prevent. Two small honest vocabularies beat
#: one that has to be vague enough to cover both.
FILE_FAILURE_CLASSES: frozenset[str] = frozenset(
    {
        "no such file",
        "permission denied",
        "the path is a directory",
        "the file is not valid UTF-8",
        "unknown failure",
    }
)

_FILE_MARKERS: tuple[tuple[str, str], ...] = (
    ("is a directory", "the path is a directory"),
    ("permission denied", "permission denied"),
    ("no such file or directory", "no such file"),
    ("codec can't decode", "the file is not valid UTF-8"),
    ("invalid start byte", "the file is not valid UTF-8"),
)


def classify_file(foreign_text: str | None) -> str:
    """A member of `FILE_FAILURE_CLASSES` describing a file-read failure.

    Same contract as `classify`: the input is read and never echoed. An OSError's
    `str()` carries the RESOLVED absolute path (`[Errno 2] No such file or
    directory: '/home/<user>/<sibling>/README.md'`), which names the operating
    user and the fleet layout even though the caller only ever typed a sibling
    name — so the text is classified, never interpolated.
    """
    if not foreign_text:
        return UNKNOWN
    haystack = foreign_text.lower()
    for marker, klass in _FILE_MARKERS:
        if marker in haystack:
            return klass
    return UNKNOWN
