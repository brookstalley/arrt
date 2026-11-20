"""Every release the change log records has its catalogue in the migration chain, the release being cut included.

`arrt/tests/system/test_migration_chain.py` opens the catalogue each past
release left (`arrt/tests/fixtures/catalogues/`, SQL dumps made by that
release's own code, `arrt/tools/old_catalogue.py`) with today's code.
`releases.json` names, for each release, its dump, or the earlier release's
dump whose shape it shares. Nothing failed when a release shipped without one,
so the list grew by hand or not at all, and the
norm row promising "a catalogue every past release left opens" held only the
releases someone had remembered.

**The rule, and what it asserts between releases.** Every release the change
log records (a `release=vX.Y.Z` tag line) with a version at or below
`arrt/pyproject.toml`'s has a row in `releases.json`, and `RELEASES` lists
exactly those releases, oldest first, as the rows do. Between releases the
version is the last release's (0.11.0 while `develop` carries the shape
generation and `catalogue_opened` that 0.11.0 lacks), so the test holds the
rows of every release up to and including that one, each of which was cut
with its row, and says nothing of the shape `develop` has moved on to: that
shape belongs to no release yet. An ordinary pull request changes neither the
version nor a `release=` tag, so it is green. **A release cut moves both**: the
version becomes the new release's and the cut tags its entries with it, so the
new release is recorded at or below the version, and the test is red until its
row is there. That row is made by running `old_catalogue.py` in the release's
own commit, before its tag exists: the tool makes the newest release in
`RELEASES` from `HEAD` when git has no tag of that name yet, and writes its own
dump when its shape differs from the release before it (the next release's
will, by `catalogue_opened`).

**Why "at or below", where the rule was first written "below".** "Below" bites one release late: cutting 0.12.0 without its dump
would be green, and only 0.13.0's cut would be refused, after 0.12.0 had
shipped with no catalogue in the chain. Its cost: the release commit cannot be
pushed green until `old_catalogue.py` has run in it, with the earlier tags
present.

**What it reads, and what it cannot see.** The change log in all three homes
(`.prawduct/change-log.md`, `.prawduct/change-log-archive/`, and
`.prawduct/changes/`, whose fragments carry no `release` until the cut moves
them to the archive); `arrt/pyproject.toml`; `releases.json`; and `RELEASES`,
read from `old_catalogue.py`'s syntax tree, so this never imports `arrt`. It
cannot tell a row that claims a shared shape from one that has it: the dump is
made by old code from git, which no test runs. The tool decides that by
comparing schemas, so a row is only as right as the run that wrote it.
"""

import ast
import json
import pathlib
import re
import tomllib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHANGE_LOG = ROOT / ".prawduct" / "change-log.md"
CHANGE_LOG_HOMES = (CHANGE_LOG, ROOT / ".prawduct" / "change-log-archive", ROOT / ".prawduct" / "changes")
CURATION_PYPROJECT = ROOT / "arrt" / "pyproject.toml"
OLD_CATALOGUE = ROOT / "arrt" / "tools" / "old_catalogue.py"
CATALOGUES = ROOT / "arrt" / "tests" / "fixtures" / "catalogues"
RELEASES_JSON = CATALOGUES / "releases.json"

#: A tag line: the comment at the start of its line, as prawduct writes one under
#: an entry's heading. The change log's header documents the format with an
#: indented example (`release=v1.3.18`), which is no release of this product;
#: anchoring at the line's start is what leaves it out.
_TAG_LINE = re.compile(r"^<!--\s*prawduct:\s*(?P<body>.+?)\s*-->\s*$", re.MULTILINE)
_RELEASE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

Version = tuple[int, int, int]


def releases_recorded(text: str) -> set[str]:
    """Every `release=` a tag line in `text` names. A value that is not `vX.Y.Z` fails by name."""
    found: set[str] = set()
    for line in _TAG_LINE.finditer(text):
        for pair in line["body"].split("|"):
            key, _, value = pair.strip().partition("=")
            if key.strip() != "release":
                continue
            value = value.strip()
            assert _RELEASE.match(value), f"a change-log tag line names release={value!r}, which is not vX.Y.Z"
            found.add(value)
    return found


def version_of(tag: str) -> Version:
    matched = _RELEASE.match(tag)
    assert matched, f"{tag!r} is not a release tag vX.Y.Z"
    major, minor, patch = (int(part) for part in matched.groups())
    return major, minor, patch


def releases_owed(recorded: set[str], version: str) -> list[str]:
    """The releases the chain must hold: those recorded at or below `version`, oldest first."""
    ceiling = version_of(f"v{version}")
    return sorted((tag for tag in recorded if version_of(tag) <= ceiling), key=version_of)


def problems(recorded: set[str], version: str, rows: dict[str, str], listed: tuple[str, ...]) -> list[str]:
    """What is wrong with the chain's release list, each as a sentence naming what to do; empty when nothing is."""
    owed = releases_owed(recorded, version)
    said = [
        f"{tag} is a release (the change log records it, at or below {version}) with no row in releases.json: "
        f"with {tag} in RELEASES (arrt/tools/old_catalogue.py), run cd arrt && uv run python tools/old_catalogue.py"
        for tag in owed
        if tag not in rows
    ]
    if list(listed) != owed:
        said.append(f"RELEASES in arrt/tools/old_catalogue.py is {list(listed)}; the releases recorded are {owed}")
    if list(rows) != list(listed):
        said.append(f"releases.json's rows are {list(rows)}, where RELEASES is {list(listed)}: run old_catalogue.py")
    own = {tag for tag, name in rows.items() if name == f"{tag}.sql"}
    for tag, name in rows.items():
        if name == f"{tag}.sql":
            continue
        shared = name.removesuffix(".sql")
        if shared not in own or version_of(shared) >= version_of(tag):
            said.append(f"releases.json gives {tag} {name!r}, which is no earlier release's own dump")
    return said


def _change_log_text() -> str:
    paths = [CHANGE_LOG]
    for home in CHANGE_LOG_HOMES[1:]:
        paths += sorted(home.glob("*.md"))
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def _version() -> str:
    return tomllib.loads(CURATION_PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


def _releases_listed() -> tuple[str, ...]:
    tree = ast.parse(OLD_CATALOGUE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "RELEASES":
            assert node.value is not None
            return tuple(ast.literal_eval(node.value))
    raise AssertionError("arrt/tools/old_catalogue.py has no RELEASES")


def _rows() -> dict[str, str]:
    return json.loads(RELEASES_JSON.read_text(encoding="utf-8"))


# -- the parser, on the change log's own lines ---------------------------------------

#: Lines copied from the change log as it stands (2026-11-19), one per tag-line
#: shape it carries, and what each records. The last is the header's indented
#: example of the format, `.prawduct/change-log.md` line 33.
_OBSERVED = {
    "<!-- prawduct: scope=arr-navigation | release=v0.1.0 -->": {"v0.1.0"},
    "<!-- prawduct: type=feature | scope=player-media-capability | release=v0.11.0 -->": {"v0.11.0"},
    "<!-- prawduct: type=fix | scope=ask-spend | closes=brookstalley/arrt#337 | release=v0.10.0 -->": {"v0.10.0"},
    "<!-- prawduct: chunks=01,02,06 | status=shipped | scope=v1-build -->": set(),
    "         <!-- prawduct: release=v1.3.18 | scope=v1.4 -->": set(),
}


@pytest.mark.parametrize("line", _OBSERVED)
def test_the_parser_reads_the_change_log_s_own_tag_lines(line):
    assert releases_recorded(line) == _OBSERVED[line]


def test_every_observed_line_is_in_the_change_log():
    """So the samples above are the log's lines, not lines written from its format: each is found verbatim."""
    text = _change_log_text()
    missing = [line for line in _OBSERVED if line not in text.splitlines()]
    assert missing == []


def test_a_tag_line_naming_no_version_fails_by_name():
    with pytest.raises(AssertionError, match="release='unreleased'"):
        releases_recorded("<!-- prawduct: scope=x | release=unreleased -->")


def test_the_change_log_records_the_release_the_version_names():
    """Vacuity first: a parser that found nothing would owe nothing, and pass."""
    recorded = releases_recorded(_change_log_text())
    assert "v0.1.0" in recorded
    assert f"v{_version()}" in recorded, f"the change log records no release=v{_version()}, the version arrt/pyproject.toml names"


# -- the rule, between releases and at a cut ----------------------------------------

_RECORDED_NOW = {"v0.1.0", "v0.2.0", "v0.3.0"}
_LISTED_NOW = ("v0.1.0", "v0.2.0", "v0.3.0")
_ROWS_NOW = {"v0.1.0": "v0.1.0.sql", "v0.2.0": "v0.1.0.sql", "v0.3.0": "v0.3.0.sql"}


def test_between_releases_the_rows_up_to_the_version_are_enough():
    """The version is the last release's, its row is there, and develop's moved shape owes nothing yet."""
    assert problems(_RECORDED_NOW, "0.3.0", _ROWS_NOW, _LISTED_NOW) == []


def test_a_release_cut_without_its_row_is_refused_naming_it():
    """The cut moves the version and tags the entries; the release it cuts is owed at once, not at the next one."""
    said = problems(_RECORDED_NOW | {"v0.4.0"}, "0.4.0", _ROWS_NOW, _LISTED_NOW)
    assert said[0].startswith("v0.4.0 is a release (the change log records it, at or below 0.4.0) with no row")
    assert any(line.startswith("RELEASES in arrt/tools/old_catalogue.py is") for line in said)


def test_a_release_cut_with_its_row_passes():
    rows = {**_ROWS_NOW, "v0.4.0": "v0.4.0.sql"}
    assert problems(_RECORDED_NOW | {"v0.4.0"}, "0.4.0", rows, (*_LISTED_NOW, "v0.4.0")) == []


def test_a_row_must_name_an_earlier_release_s_own_dump():
    rows = {**_ROWS_NOW, "v0.2.0": "v0.3.0.sql"}
    assert problems(_RECORDED_NOW, "0.3.0", rows, _LISTED_NOW) == [
        "releases.json gives v0.2.0 'v0.3.0.sql', which is no earlier release's own dump"
    ]


# -- this repository ----------------------------------------------------------------


def test_every_release_the_change_log_records_has_its_catalogue_in_the_chain():
    said = problems(releases_recorded(_change_log_text()), _version(), _rows(), _releases_listed())
    assert said == [], "\n".join(said)


def test_every_dump_a_row_names_is_on_disk():
    absent = sorted({name for name in _rows().values() if not (CATALOGUES / name).is_file()})
    assert absent == [], f"releases.json names dumps that are not in {CATALOGUES.relative_to(ROOT)}: {absent}"
