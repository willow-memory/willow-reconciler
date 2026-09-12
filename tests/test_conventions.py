"""`reconciler conventions` — the verb and the document it publishes.

What the document *says* is held against this repo's own tree in
`tests/test_fleet_conventions.py`; this file holds the verb to the module:
the JSON on stdout is the module's data verbatim, the schema is the one
consumers pin, and every rule carries a source."""
from __future__ import annotations

import json

from reconciler.cli import cmd_conventions, main
from reconciler.conventions import SCHEMA, SOURCES, conventions, render_markdown

#: The schema's key order — a consumer pinned to `/1` reads exactly these.
EXPECTED_KEYS = [
    "schema",
    "hidden_types",
    "release_cutting_types",
    "required_when_release_please_arms_automerge",
    "required_config_comments",
    "required_when_pile_exists",
    "contributing_must_name_test_command",
    "idea_id_trailer",
    "sources",
]


def test_json_output_is_the_module_data_verbatim(capsys):
    rc = cmd_conventions(as_json=True)
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == conventions()


def test_the_document_has_the_schema_and_exactly_the_published_keys():
    doc = conventions()
    assert doc["schema"] == SCHEMA == "willow-fleet-conventions/1"
    assert list(doc) == EXPECTED_KEYS
    assert doc["hidden_types"] == ["chore", "ci", "docs", "test"]
    assert doc["release_cutting_types"] == [
        "build", "deps", "feat", "fix", "perf", "refactor", "security"]
    assert not set(doc["hidden_types"]) & set(doc["release_cutting_types"]), (
        "a type is hidden or it cuts a release; never both")
    assert doc["required_when_release_please_arms_automerge"] == [".github/workflows/pr-title.yml"]
    assert doc["required_config_comments"] == [
        "$comment-hidden-rule", "$comment-what-cuts-a-release"]
    assert doc["required_when_pile_exists"] == [".github/workflows/trailers.yml"]
    assert doc["contributing_must_name_test_command"] is True
    assert doc["idea_id_trailer"] == "Idea-Id"


def test_every_rule_names_its_source_and_no_source_is_orphaned():
    doc = conventions()
    rules = [k for k in doc if k not in ("schema", "sources")]
    assert sorted(doc["sources"]) == sorted(rules)
    for key, why in SOURCES.items():
        assert why.strip(), f"{key} has an empty source"


def test_markdown_names_every_rule_and_its_source(capsys):
    rc = cmd_conventions(as_json=False)
    assert rc == 0
    md = capsys.readouterr().out
    doc = conventions()
    for key in doc:
        if key == "sources":
            continue
        assert key in md
    for why in doc["sources"].values():
        assert why in md
    assert md.strip() == render_markdown(doc).strip()


def test_main_dispatches_the_verb_with_and_without_json(capsys):
    assert main(["conventions", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["schema"] == SCHEMA
    assert main(["conventions"]) == 0
    assert capsys.readouterr().out.startswith("# fleet conventions")
