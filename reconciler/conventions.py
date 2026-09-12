"""The fleet's convention set, published from one place.

The fleet plan's decision 4: every repo carries a `tests/test_fleet_conventions.py`
that checks its own wiring against the fleet's rules, and the rule set has ONE
home — this module. The reconciler publishes it (`reconciler conventions
--json`); consumers read it. A rule that lived in each repo's own test file
would drift one repo at a time, which is exactly how the incidents named in
`SOURCES` happened: each repo's release wiring was locally reasonable and
fleet-wide inconsistent.

This module is data and two renderers, nothing else. It reads no file and
runs no check — `tests/test_fleet_conventions.py` (here, and in every repo
that consumes this) is where a rule is held against a tree. Keeping the
check out of the package keeps the package stdlib-only and read-only, and
keeps this the same shape as `ledger.READING` / `benchmark.READING`: one
constant, imported, never retyped.

`SCHEMA` is versioned the way `fleet.SCHEMA_VERSION` is: bump only on a
field REMOVAL or MEANING change, never on an addition — a consumer pinned
to `/1` must keep reading a `/1` document that has grown a key.
"""
from __future__ import annotations

import json

SCHEMA = "willow-fleet-conventions/1"

#: Conventional-commit types release-please must NOT release on. These are
#: exactly the types that change nothing `pip install <package>` delivers.
HIDDEN_TYPES = ("chore", "ci", "docs", "test")

#: Every type that cuts a release on its own — every un-hidden type, not just
#: feat and fix. The two tuples partition the types a config may list.
RELEASE_CUTTING_TYPES = ("build", "deps", "feat", "fix", "perf", "refactor", "security")

#: Files a repo must carry once its release-please.yml arms auto-merge on the
#: release PR — the point at which a PR title can publish unattended.
REQUIRED_WHEN_RELEASE_PLEASE_ARMS_AUTOMERGE = (".github/workflows/pr-title.yml",)

#: Recorded-reasoning blocks that must sit inside release-please-config.json
#: beside the setting they explain.
REQUIRED_CONFIG_COMMENTS = ("$comment-hidden-rule", "$comment-what-cuts-a-release")

#: Files a repo must carry once it keeps a numbered idea pile — the join key
#: the reconciler trusts most has to be verified in CI, or a dangling one is
#: a permanent confident LANDED.
REQUIRED_WHEN_PILE_EXISTS = (".github/workflows/trailers.yml",)

#: CONTRIBUTING.md must name the command a contributor runs — the PR
#: template's Evidence line quotes it, and receipts need a command to quote.
CONTRIBUTING_MUST_NAME_TEST_COMMAND = True

#: The git trailer that joins a commit to the pile item it lands.
IDEA_ID_TRAILER = "Idea-Id"

#: One line per rule, naming the incident or decision it comes from. A rule
#: with no source is an opinion; these are the fleet's own history.
SOURCES = {
    "hidden_types": (
        "jeles v0.4.1: tagged and published to PyPI for a single `ci:` commit that "
        "changed a workflow file and nothing a user installs. docs/test/ci/chore "
        "change nothing `pip install` delivers, so they are hidden "
        "(release-please-config.json `$comment-hidden-rule`)."
    ),
    "release_cutting_types": (
        "willow-mcp 2.1.5: `fix(ci):` touched only tools/ and .github/, neither "
        "packaged, and still cut a release — every un-hidden type releases on its "
        "own, so the set is closed and named (`$comment-what-cuts-a-release`)."
    ),
    "required_when_release_please_arms_automerge": (
        "willow-mcp v2.1.1: a `fix(ci):` PR title over a commit already corrected to "
        "`ci:` cut a release, because merge commits carry the title and "
        "release-please.yml arms auto-merge; pr-title.yml is the guard "
        "(fleet plan Wave 2, G2-pr-title)."
    ),
    "required_config_comments": (
        "Fleet plan decision 4: the reasoning lives beside the setting it explains, "
        "in the config file itself, so a hidden set cannot be edited without "
        "reading why it is what it is."
    ),
    "required_when_pile_exists": (
        "willow-reconciler CONVENTION.md, 'A wrong id is worse than no id': rule 2a "
        "asserts LANDED from a trailer ahead of every other signal, so a repo with a "
        "numbered pile runs `reconciler verify` in CI (trailers.yml, willow-ideas-005)."
    ),
    "contributing_must_name_test_command": (
        "CONTRIBUTING.md 'Receipts, not claims': the PR template's Evidence line "
        "quotes the test command and its result; a CONTRIBUTING that does not name "
        "the command leaves nothing to quote."
    ),
    "idea_id_trailer": (
        "decision-2026-09-11-adopt-idea-id-trailers (CONVENTION.md): the durable, "
        "prospective join key between a pile item and the commit that landed it."
    ),
}


def conventions() -> dict:
    """The published document. Key order is the schema's; `SOURCES` carries
    one entry per rule key above it, which `tests/test_conventions.py`
    holds it to."""
    return {
        "schema": SCHEMA,
        "hidden_types": list(HIDDEN_TYPES),
        "release_cutting_types": list(RELEASE_CUTTING_TYPES),
        "required_when_release_please_arms_automerge":
            list(REQUIRED_WHEN_RELEASE_PLEASE_ARMS_AUTOMERGE),
        "required_config_comments": list(REQUIRED_CONFIG_COMMENTS),
        "required_when_pile_exists": list(REQUIRED_WHEN_PILE_EXISTS),
        "contributing_must_name_test_command": CONTRIBUTING_MUST_NAME_TEST_COMMAND,
        "idea_id_trailer": IDEA_ID_TRAILER,
        "sources": dict(SOURCES),
    }


def render_json(doc: dict) -> str:
    return json.dumps(doc, indent=2)


def render_markdown(doc: dict) -> str:
    """The same document for a reader: one rule per line, each followed by
    the incident or decision it comes from."""
    lines = ["# fleet conventions", "", f"- **schema**: `{doc['schema']}`", ""]
    for key, value in doc.items():
        if key in ("schema", "sources"):
            continue
        shown = ", ".join(f"`{v}`" for v in value) if isinstance(value, list) else f"`{value}`"
        lines.append(f"- **{key}**: {shown}")
        lines.append(f"  - source: {doc['sources'][key]}")
    return "\n".join(lines)
