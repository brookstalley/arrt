"""A minor is additive: everything a released version of this major accepted, this version accepts.

`player-contract.md` § Versioning says a new minor is additive and a released tag
is not moved, and until this file that was held by review alone. A Player pins a
tag; a server built from this checkout serves it. So each release's fixtures and
routes are kept here as they were at the tag (`released/<version>/`, copied once
when it was cut, `sha256.json` recording each file's hash), and held to HEAD:

- **every valid fixture of a release validates at HEAD**, the schema and the
  rules no schema states, so a document an older writer produces is still a
  document;
- **every invalid fixture of a release is still invalid at HEAD**, unless the
  loosening is recorded in `LOOSENED` with its reason. A minor that loosens a
  writer's obligation lets a new writer send what an older reader refuses
  (heartbeat minor 4 did, deliberately, deployed server first), so it is a
  decision, never a side effect;
- **no route and no fixture of a release is gone** within the major, and a
  route keeps its method and its path;
- **every answer of a release still holds at HEAD** (from 1.2.0, the first
  release with a `transport.json`): each route and case is still in the table,
  with the same status and body, unless HEAD's row carries a `corrected` record
  naming a later version and what the release answered;
- **every word of a release's vocabulary still holds** (from 1.2.0 too): a state,
  a word or a pairing field may be added, never removed or reworded;
- **each frozen file is the bytes it was**, so a release cannot be edited into
  agreement with HEAD.
"""

import copy
import hashlib
import json
import re
from importlib.metadata import version
from pathlib import Path

import pytest

import arrt_contract
from arrt_contract import fixtures, released, root, routes, semantic_errors, specification, transport, validator, vocabulary

RELEASES = released()
HEAD_VERSION = version("arrt-contract")
HEAD_MAJOR = int(HEAD_VERSION.split(".")[0])

#: Invalid fixtures of a release that HEAD accepts, each with the decision that
#: loosened its rule. Empty: no minor since the first frozen release has loosened one.
LOOSENED: dict[tuple[str, str], str] = {}


def _index(release: Path) -> list[dict]:
    return json.loads((release / "fixtures" / "index.json").read_text(encoding="utf-8"))["fixtures"]


def _document(release: Path, row: dict) -> dict:
    return json.loads((release / row["path"]).read_text(encoding="utf-8"))


def _errors_at_head(release: Path, row: dict) -> list[str]:
    document = _document(release, row)
    errors = [error.message for error in validator(row["schema"]).iter_errors(document)]
    if not errors:
        errors = semantic_errors(document, schema=row["schema"])
    return errors


def _rows(*, valid: bool) -> list[tuple[str, dict]]:
    return [(name, row) for name, release in RELEASES.items() for row in _index(release) if row["valid"] is valid]


def _id(case: tuple[str, dict]) -> str:
    return f"{case[0]}:{case[1]['path']}"


def test_the_releases_a_player_may_pin_are_here():
    """contract-v1.0.0 is what Arrt Player pins as this is written, and contract-v1.2.0 the latest tag."""
    assert {"1.0.0", "1.1.0", "1.2.0"} <= set(RELEASES)


# -- every release the specification lists is frozen once the package moves past it ---
#
# `player-contract.md` § Releases lists each tag. A copy forgotten when a release
# was cut is found only when something else reads the directory, so the
# specification is the list and `released()` the copies. The package's own version
# is not yet frozen (its tag is cut from this tree), so only a release below it
# must be here: the next minor's first commit turns the previous one's absence red.

_RELEASE_LINE = re.compile(r"- \*\*(\d+\.\d+\.\d+)\*\*")


def _listed_releases(specification_text: str) -> list[str]:
    """The versions § Releases lists: each top-level bullet opening with its version in bold, under that heading only."""
    lines = specification_text.splitlines()
    if "### Releases" not in lines:
        raise ValueError("no '### Releases' heading: reading none would pass every release as frozen")
    listed = []
    for line in lines[lines.index("### Releases") + 1 :]:
        if line.startswith("#"):
            break
        found = _RELEASE_LINE.match(line)
        if found:
            listed.append(found.group(1))
    return listed


def _triple(spelling: str) -> tuple[int, ...]:
    return tuple(int(part) for part in spelling.split("."))


def _listed_below_and_not_frozen(specification_text: str, own: str, frozen: set[str]) -> list[str]:
    return [v for v in _listed_releases(specification_text) if _triple(v) < _triple(own) and v not in frozen]


def test_every_release_the_specification_lists_below_the_packages_version_has_a_frozen_copy():
    text = specification().read_text(encoding="utf-8")

    assert {"1.0.0", "1.1.0", "1.2.0"} <= set(_listed_releases(text)), "§ Releases was not read: the check would pass on nothing"
    unfrozen = _listed_below_and_not_frozen(text, HEAD_VERSION, set(RELEASES))
    assert unfrozen == [], f"§ Releases lists {unfrozen}, below {HEAD_VERSION}, with no copy in contract/released/"


def _listed_as_tagged(specification_text: str) -> list[str]:
    """The versions whose § Releases bullet opening says it is tagged (`contract-v<version>`), before any nested bullet.

    The pool and CI have no tags, so the specification is what says a release is
    cut: a bullet that says so is held to its copy even when the version is the
    package's own, which the check above leaves out until the next minor.
    """
    lines = specification_text.splitlines()
    if "### Releases" not in lines:
        raise ValueError("no '### Releases' heading: reading none would pass every release as frozen")
    openings: dict[str, list[str]] = {}
    current = ""
    in_opening = False
    for line in lines[lines.index("### Releases") + 1 :]:
        if line.startswith("#"):
            break
        found = _RELEASE_LINE.match(line)
        if found:
            current, in_opening = found.group(1), True
            openings[current] = [line]
        elif line.startswith("  -"):
            in_opening = False
        elif in_opening and line.strip():
            openings[current].append(line.strip())
        elif not line.strip():
            in_opening = False
    return [v for v, text in openings.items() if f"tagged `contract-v{v}`" in " ".join(text)]


def test_a_release_the_specification_says_is_tagged_has_a_frozen_copy_even_at_the_packages_own_version():
    text = specification().read_text(encoding="utf-8")

    tagged = _listed_as_tagged(text)
    assert HEAD_VERSION in tagged, f"§ Releases does not say {HEAD_VERSION} is tagged: the check would pass on nothing"
    uncopied = [v for v in tagged if v not in RELEASES]
    assert uncopied == [], f"§ Releases says {uncopied} is tagged and contract/released/ holds only {sorted(RELEASES)}"


@pytest.mark.parametrize(
    ("excerpt", "tagged"),
    [
        ("- **1.3.0** (wave 2b; tagged `contract-v1.3.0`, annotated, on\n  2026-11-25): a copy.\n  - nested\n", ["1.3.0"]),
        ("- **1.3.0** (wave 2b; tagged\n  `contract-v1.3.0`): wrapped.\n", ["1.3.0"]),
        ("- **1.3.0** (wave 2b): **not cut yet**.\n", []),
        ("- **1.3.0** (wave 2b): opening.\n  - a nested bullet says tagged `contract-v1.3.0`\n", []),
        ("- **1.3.0** (tagged `contract-v1.2.0`)\n", []),
        ("- **1.2.0** (tagged `contract-v1.2.0`)\n- **1.3.0** (tagged `contract-v1.3.0`)\n", ["1.2.0", "1.3.0"]),
    ],
)
def test_the_parser_of_tagged_releases_reads_the_bullets_opening_and_nothing_else(excerpt, tagged):
    assert _listed_as_tagged(f"### Releases\n\n{excerpt}") == tagged


# Lines copied from `contract/player-contract.md` as it is at contract-v1.2.0, in its order:
# one line that opens a bullet but is no release, the heading, the release lines,
# the nested bullets that mention versions, and the next heading.
_COPIED = (
    "- **A release is copied into `contract/released/<version>/` when it is cut**:",
    "### Releases",
    "- **1.0.0** (2026-10-26): the first tag; heartbeat minor 4.",
    "- **1.1.0** (2026-11-13): heartbeat minor 5, `capabilities.media`.",
    "- **1.2.0** (audit wave 2, 2026-11-19): every change additive, nothing removed,",
    "  - `contract/released/1.0.0/` and `1.1.0/`, `released()`, and the check above.",
    "### What a Player does at 1.2.0",
)


def test_the_lines_the_parser_is_tested_on_are_the_specifications_own():
    lines = specification().read_text(encoding="utf-8").splitlines()

    assert [line for line in _COPIED if line.rstrip() not in [candidate.rstrip() for candidate in lines]] == []


def test_the_parser_reads_the_releases_lines_and_nothing_else():
    excerpt = "\n".join(
        (
            *_COPIED[:2],
            "",
            *_COPIED[2:6],
            "  - **9.9.9** is a nested bullet, not a release.",
            "",
            _COPIED[6],
            "",
            "- **1.3.0** is under another heading.",
        )
    )

    assert _listed_releases(excerpt) == ["1.0.0", "1.1.0", "1.2.0"]


def test_a_bullet_opening_a_paragraph_of_another_section_is_not_a_release():
    # Above the heading, so it is not read: the line is the package section's, copied.
    assert _listed_releases("\n".join((_COPIED[0], *_COPIED[1:2], *_COPIED[2:3]))) == ["1.0.0"]


@pytest.mark.parametrize(
    ("line", "listed"),
    [
        ("- **1.2.0** (2026-11-19): a release.", ["1.2.0"]),
        ("  - **1.2.0** (nested)", []),
        ("- 1.2.0 (not in bold)", []),
        ("- **1.2** (two numbers)", []),
        ("- **v1.2.0** (a tag)", []),
        (_COPIED[0], []),
        (_COPIED[5], []),
        ("The releases before 1.2.0 were copied from their tags when 1.2.0", []),
    ],
)
def test_a_line_is_a_release_only_when_it_is_a_top_level_bullet_opening_with_a_bold_version(line, listed):
    assert _listed_releases(f"### Releases\n\n{line}\n") == listed


def test_a_release_below_the_packages_version_with_no_copy_is_named():
    text = "\n".join(_COPIED[1:5])

    assert _listed_below_and_not_frozen(text, "1.3.0", {"1.0.0", "1.1.0"}) == ["1.2.0"]
    assert _listed_below_and_not_frozen(text, "1.3.0", {"1.0.0", "1.1.0", "1.2.0"}) == []
    # The package's own version is not below itself: its tag is cut from this tree.
    assert _listed_below_and_not_frozen(text, "1.2.0", {"1.0.0", "1.1.0"}) == []
    # Compared as numbers, not as spelled: 1.10.0 is above 1.9.0.
    assert _listed_below_and_not_frozen("### Releases\n\n- **1.9.0** (x)\n", "1.10.0", set()) == ["1.9.0"]
    assert _listed_below_and_not_frozen("### Releases\n\n- **1.10.0** (x)\n", "1.9.0", set()) == []


def test_a_specification_without_a_releases_section_is_refused_not_read_as_empty():
    with pytest.raises(ValueError, match="### Releases"):
        _listed_releases("# The Player Contract\n\n- **1.0.0** (a bullet)\n")


@pytest.mark.parametrize("name", sorted(RELEASES))
def test_a_release_kept_here_is_of_this_major(name):
    """A new major may break what a release of the old one accepted, so its frozen copies are retired by a decision then."""
    assert int(name.split(".")[0]) == HEAD_MAJOR, f"released/{name} is of another major: retire it deliberately"


@pytest.mark.parametrize("case", _rows(valid=True), ids=_id)
def test_every_valid_fixture_of_a_release_is_valid_at_head(case):
    name, row = case

    assert _errors_at_head(RELEASES[name], row) == [], f"contract-v{name} accepted {row['path']}"


@pytest.mark.parametrize("case", _rows(valid=False), ids=_id)
def test_every_invalid_fixture_of_a_release_is_still_refused_at_head_unless_its_loosening_is_recorded(case):
    name, row = case
    refused = _errors_at_head(RELEASES[name], row) != []

    assert refused is ((name, row["path"]) not in LOOSENED), f"contract-v{name} refused {row['path']}"


@pytest.mark.parametrize("name", sorted(RELEASES))
def test_no_route_of_a_release_is_gone_or_moved(name):
    then = json.loads((RELEASES[name] / "routes.json").read_text(encoding="utf-8"))["routes"]
    now = routes()

    assert set(then) - set(now) == set(), f"routes contract-v{name} named and HEAD does not"
    for route, spelling in then.items():
        assert now[route] == spelling, f"{route} moved since contract-v{name}"


@pytest.mark.parametrize("name", sorted(RELEASES))
def test_no_fixture_of_a_release_is_gone_or_changed_its_verdict(name):
    head = {row["path"]: row for row in fixtures()}

    for row in _index(RELEASES[name]):
        assert row["path"] in head, f"{row['path']} was in contract-v{name} and is gone"
        assert head[row["path"]]["schema"] == row["schema"], row["path"]
        assert head[row["path"]]["valid"] is row["valid"], row["path"]


@pytest.mark.parametrize("name", sorted(RELEASES))
def test_each_frozen_file_is_the_bytes_it_was_when_it_was_copied(name):
    release = RELEASES[name]
    recorded = json.loads((release / "sha256.json").read_text(encoding="utf-8"))
    on_disk = {
        str(path.relative_to(release)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(release.rglob("*"))
        if path.is_file() and path.name != "sha256.json"
    }

    assert recorded["version"] == name
    assert recorded["tag"] == f"contract-v{name}"
    assert on_disk == recorded["files"]


# -- every answer and every word of a release still holds at HEAD ------------------
#
# 1.2.0 introduced `transport.json` and `vocabulary.json`, so a copy holds them from
# 1.2.0 on and 1.0.0's and 1.1.0's have neither. A Player's server double answers
# from the table and its settings page quotes the words, so a changed answer or a
# reworded word changes what a pinned Player meets, exactly as a fixture does.
#
# **Which answers were corrected is HEAD's table's to say**, in each changed row's
# `corrected` (`in`, `was`, `why`): it travels in the package, and a Player's double
# reads it. This file reads the corrections from there and nowhere else;
# `CORRECTED` in `test_transport.py` is a second statement of the same list, held
# equal to the table's by `test_the_rows_that_say_they_were_corrected_are_the_corrections_this_file_lists`.
# A record excuses a change only when it names a version after the release and
# says the release's own answer was what it was, so it cannot excuse any edit.
#
# What is held is what a reader acts on: a case's status and body, a document's
# schema, the error body's keys, the conditional routes; a state's word, who
# reports it and whether it is a setup step; a pairing field's name. The prose
# (`means`, `player`, `description`, `_about`) may be clarified without a record,
# which is the cost: a `means` rewritten to say something else is held by review.

TABLES_FROM = (1, 2, 0)
TABLES = ("transport.json", "vocabulary.json")


def _frozen(name: str, file: str) -> dict:
    return json.loads((RELEASES[name] / file).read_text(encoding="utf-8"))


def _with_tables() -> list[str]:
    return [name for name in sorted(RELEASES, key=_triple) if _triple(name) >= TABLES_FROM]


def _answer(row: dict) -> tuple[int, str]:
    return row["status"], row["body"]


def _case_changed(name: str, at: str, row: dict, now_row: dict | None) -> list[str]:
    """How one case of release `name` (`row`) fails at HEAD (`now_row`), if it does."""
    if now_row is None:
        return [f"{at}: gone from the table"]
    then_answer, now_answer = _answer(row), _answer(now_row)
    if then_answer == now_answer:
        return []
    record = now_row.get("corrected")
    changed = f"{at}: {then_answer} at {name}, {now_answer} at HEAD"
    if record is None:
        return [f"{changed}, and no corrected record"]
    if _triple(record["in"]) <= _triple(name):
        return [f"{changed}, and its corrected record names {record['in']}, not a version after {name}"]
    if _answer(record["was"]) != then_answer:
        return [f"{changed}, and its corrected record says it was {_answer(record['was'])}"]
    return []


def _route_changed(name: str, route: str, was: dict, now: dict | None) -> list[str]:
    """How one route of release `name` fails at HEAD: gone, a document's schema changed, or one of its cases."""
    if now is None:
        return [f"{route}: gone from the table"]
    broken = [
        f"{route}: {key} was {was.get(key)} and is {now.get(key)}"
        for key in ("schema", "request_schema")
        if was.get(key) != now.get(key)
    ]
    cases = {row["case"]: row for row in now["answers"]}
    for row in was["answers"]:
        broken += _case_changed(name, f"{route}/{row['case']}", row, cases.get(row["case"]))
    return broken


def _answers_changed(name: str, then: dict, now: dict) -> list[str]:
    """Each way HEAD's table `now` breaks release `name`'s table `then`, one line each, naming the route and case."""
    broken = [
        f"error_body no longer requires {key!r}"
        for key in sorted(set(then["error_body"]["required"]) - set(now["error_body"]["required"]))
    ]
    broken += [
        f"{route}: no longer answers a conditional GET"
        for route in sorted(set(then["conditional_get"]["routes"]) - set(now["conditional_get"]["routes"]))
    ]
    for route, was in then["routes"].items():
        broken += _route_changed(name, route, was, now["routes"].get(route))
    return broken


#: A vocabulary entry's prose, which may be clarified; every other field is held.
_PROSE = {"means"}


def _entry_changed(at: str, was: object, now: object) -> list[str]:
    """How one entry of a release's vocabulary fails at HEAD: a pairing field's name, or any field of a state but its prose."""
    if not isinstance(was, dict) or not isinstance(now, dict):
        return [] if now == was else [f"{at}: {was!r} is now {now!r}"]
    return [
        f"{at}.{field}: {was[field]!r} is now {now.get(field)!r}"
        for field in sorted(set(was) - _PROSE)
        if now.get(field) != was[field]
    ]


def _words_changed(then: dict, now: dict) -> list[str]:
    """Each way HEAD's vocabulary `now` breaks a release's `then`: a section, state or field gone, or a word changed."""
    broken = []
    for section, entries in then.items():
        if section.startswith("_"):
            continue
        if section not in now:
            broken.append(f"{section}: gone")
            continue
        for key, was in entries.items():
            at = f"{section}.{key}"
            broken += _entry_changed(at, was, now[section][key]) if key in now[section] else [f"{at}: gone"]
    return broken


@pytest.mark.parametrize("name", sorted(RELEASES))
def test_a_release_holds_its_table_and_vocabulary_from_1_2_0_on(name):
    """1.2.0 introduced both files: a copy from then on without them would hold nothing to the release's answers."""
    held = {file for file in TABLES if (RELEASES[name] / file).is_file()}

    assert held == (set(TABLES) if _triple(name) >= TABLES_FROM else set()), name


def test_a_release_with_the_tables_is_here_to_hold_head_to():
    """Parametrised over none, the two checks below would pass by checking nothing."""
    assert "1.2.0" in _with_tables()


@pytest.mark.parametrize("name", _with_tables())
def test_every_answer_of_a_release_still_holds_at_head_unless_its_correction_is_recorded(name):
    assert _answers_changed(name, _frozen(name, "transport.json"), transport()) == []


@pytest.mark.parametrize("name", _with_tables())
def test_every_word_of_a_releases_vocabulary_still_holds_at_head(name):
    assert _words_changed(_frozen(name, "vocabulary.json"), vocabulary()) == []


# The cases each check must tell apart, on 1.2.0's own files and HEAD's, so that a
# check reading nothing, or reading the record without its version, is seen.


def _now_table() -> dict:
    return copy.deepcopy(transport())


def _row(table: dict, route: str, case: str) -> dict:
    return next(row for row in table["routes"][route]["answers"] if row["case"] == case)


def test_the_one_correction_passes_because_it_is_recorded():
    """The wall heartbeat's 422 in the framework's body at 1.2.0, 400 in the error shape at 1.3.0."""
    then = _frozen("1.2.0", "transport.json")
    assert _answer(_row(then, "heartbeat", "not_an_object")) == (422, "framework")
    now = _now_table()
    del _row(now, "heartbeat", "not_an_object")["corrected"]

    assert _answers_changed("1.2.0", then, transport()) == []
    assert _answers_changed("1.2.0", then, now) == [
        "heartbeat/not_an_object: (422, 'framework') at 1.2.0, (400, 'error') at HEAD, and no corrected record"
    ]


def test_a_changed_answer_with_no_record_is_named_and_a_record_excuses_it():
    then = _frozen("1.2.0", "transport.json")
    now = _now_table()
    _row(now, "label", "captions_no_wall")["status"] = 410

    assert _answers_changed("1.2.0", then, now) == [
        "label/captions_no_wall: (404, 'error') at 1.2.0, (410, 'error') at HEAD, and no corrected record"
    ]
    _row(now, "label", "captions_no_wall")["corrected"] = {"in": "1.3.0", "was": {"status": 404, "body": "error"}, "why": "x"}
    assert _answers_changed("1.2.0", then, now) == []


@pytest.mark.parametrize(
    ("record", "says"),
    [
        ({"in": "1.2.0", "was": {"status": 404, "body": "error"}}, "names 1.2.0, not a version after 1.2.0"),
        ({"in": "1.1.0", "was": {"status": 404, "body": "error"}}, "names 1.1.0, not a version after 1.2.0"),
        ({"in": "1.3.0", "was": {"status": 400, "body": "error"}}, "says it was (400, 'error')"),
        ({"in": "1.3.0", "was": {"status": 404, "body": "framework"}}, "says it was (404, 'framework')"),
    ],
)
def test_a_record_that_does_not_describe_the_release_excuses_nothing(record, says):
    then = _frozen("1.2.0", "transport.json")
    now = _now_table()
    _row(now, "label", "captions_no_wall")["body"] = "none"
    _row(now, "label", "captions_no_wall")["corrected"] = record

    assert _answers_changed("1.2.0", then, now) == [
        f"label/captions_no_wall: (404, 'error') at 1.2.0, (404, 'none') at HEAD, and its corrected record {says}"
    ]


def test_a_case_or_a_route_gone_is_named():
    then = _frozen("1.2.0", "transport.json")
    now = _now_table()
    now["routes"]["label"]["answers"] = [row for row in now["routes"]["label"]["answers"] if row["case"] != "captions_no_wall"]
    del now["routes"]["media"]

    assert _answers_changed("1.2.0", then, now) == ["media: gone from the table", "label/captions_no_wall: gone from the table"]


def test_a_documents_schema_the_error_body_and_a_conditional_route_are_held():
    then = _frozen("1.2.0", "transport.json")
    now = _now_table()
    now["routes"]["client"]["schema"] = "schemas/client.v2.schema.json"
    del now["routes"]["heartbeat"]["request_schema"]
    now["error_body"]["required"] = ["message"]
    now["conditional_get"]["routes"].remove("label")

    assert _answers_changed("1.2.0", then, now) == [
        "error_body no longer requires 'error'",
        "label: no longer answers a conditional GET",
        "client: schema was schemas/client.v1.schema.json and is schemas/client.v2.schema.json",
        "heartbeat: request_schema was schemas/heartbeat.v1.schema.json and is None",
    ]


def test_an_answer_or_case_added_since_the_release_breaks_nothing():
    then = _frozen("1.2.0", "transport.json")
    now = _now_table()
    now["routes"]["label"]["answers"].append({"case": "new", "status": 409, "body": "error", "means": "m", "player": "p"})
    _row(now, "label", "captions_no_wall")["means"] = "Reworded prose."

    assert _answers_changed("1.2.0", then, now) == []


def _now_words() -> dict:
    return copy.deepcopy(vocabulary())


def test_a_word_reworded_or_a_state_gone_is_named():
    then = _frozen("1.2.0", "vocabulary.json")
    now = _now_words()
    now["display_states"]["showing_art"]["word"] = "On"
    now["display_states"]["unassigned"]["setup"] = False
    del now["display_states"]["silent"]
    now["pairing"]["server_address"] = "Server URL"

    assert _words_changed(then, now) == [
        "display_states.showing_art.word: 'Showing' is now 'On'",
        "display_states.unassigned.setup: True is now False",
        "display_states.silent: gone",
        "pairing.server_address: 'Server address' is now 'Server URL'",
    ]


def test_a_state_a_field_or_a_section_added_breaks_nothing_and_prose_may_be_clarified():
    then = _frozen("1.2.0", "vocabulary.json")
    now = _now_words()
    now["display_states"]["dimmed"] = {"word": "Dimmed", "reported_by": "controller", "setup": False, "means": "m"}
    now["display_states"]["showing_art"]["means"] = "Clarified."
    now["pairing"]["name"] = "Name"
    now["new_section"] = {}

    assert "player_states" not in then, "1.3.0 added player_states: HEAD's is the added section this case relies on"
    assert _words_changed(then, now) == []


def test_a_section_gone_is_named():
    now = _now_words()
    del now["pairing"]

    assert _words_changed(_frozen("1.2.0", "vocabulary.json"), now) == ["pairing: gone"]


def test_a_release_is_read_from_the_packages_own_data():
    """Through `released()`, under `root()`, so a wheel carries the same copies a checkout does."""
    for release in RELEASES.values():
        assert release.parent == root() / "released"
        assert (release / "fixtures" / "index.json").is_file()
        assert (release / "routes.json").is_file()


# -- the order `released()` returns them in ----------------------------------------
#
# Oldest first, by version. Sorted by name, `1.10.0` came before `1.2.0`, so
# anything taking the last entry as the latest, or walking them oldest first, would
# have been wrong from the day a tenth minor was frozen. These point `released()` at
# a directory of their own through `root()`, which it reads.


def _frozen_under(tmp_path: Path, *names: str) -> Path:
    for name in names:
        (tmp_path / "released" / name).mkdir(parents=True)
    return tmp_path


def test_releases_are_oldest_first_by_version_not_by_spelling(tmp_path, monkeypatch):
    # Spelled-out order would be 1.10.0, 1.2.0, 1.9.0; created in no order at all.
    monkeypatch.setattr(arrt_contract, "root", lambda: _frozen_under(tmp_path, "1.2.0", "1.10.0", "1.9.0"))

    frozen = released()

    assert list(frozen) == ["1.2.0", "1.9.0", "1.10.0"]
    assert all(path.name == name for name, path in frozen.items())


def test_a_patch_and_a_major_order_as_numbers_too(tmp_path, monkeypatch):
    monkeypatch.setattr(arrt_contract, "root", lambda: _frozen_under(tmp_path, "2.0.0", "1.0.10", "1.0.9", "10.0.0", "1.0.0"))

    assert list(released()) == ["1.0.0", "1.0.9", "1.0.10", "2.0.0", "10.0.0"]


def test_a_file_among_the_releases_is_not_one(tmp_path, monkeypatch):
    monkeypatch.setattr(arrt_contract, "root", lambda: tmp_path)
    _frozen_under(tmp_path, "1.1.0")
    (tmp_path / "released" / "README.txt").write_text("not a release", encoding="utf-8")

    assert list(released()) == ["1.1.0"]


@pytest.mark.parametrize("stray", ["latest", "1.2", "1.2.0-rc1", "v1.2.0", "01.2.0", "1.2.x", "__pycache__"])
def test_a_directory_that_is_not_a_version_is_refused_by_name(tmp_path, monkeypatch, stray):
    monkeypatch.setattr(arrt_contract, "root", lambda: _frozen_under(tmp_path, "1.1.0", stray))

    with pytest.raises(ValueError, match=f"{stray}.*not named for a version"):
        released()
