"""The screens' words for a wall's and a Player's states are the contract's, every one and no other.

`static/core/states.js` quotes `contract/vocabulary.json`'s `display_states`
and `player_states`: each state's word, and whether it is a setup step (a step
not yet taken, which no screen colours or counts as a fault). The browser cannot
read the package, so the quote is held to it here, in both directions: a word
that differs, a state the package has and `states.js` lacks, and a state
`states.js` has and the package does not, each fail by name. The server's own
enums (`ScreenState`, `PlayerState`) and the label schema's states are held to
the same keys, so all four name one set of states.

Until audit wave 2b (chunk 31) this read `STATE_WORDS` in `screens/walls.js`,
whose implicit guarantee was that every state the server can send has a word on
Walls and that a state with no word reads as "Not known". Both are kept: the
first is the key equality below, the second is `states.js`'s fallback, read
here, and the browser test of a state from a later minor
(`test_walls_lead_with_the_work.py`, `dimmed`).
"""

import re

from arrt_contract import schema as contract_schema
from arrt_contract import vocabulary

from arrt.http.pages import STATIC_DIR
from arrt.programming.display_state import ScreenState
from arrt.programming.player_state import PlayerState

#: The files the server serves, wherever the package is laid out: in the
#: repository and in the image, where the project sits at `/app`.
STATES = STATIC_DIR / "core" / "states.js"
GLYPHS = STATIC_DIR / "core" / "glyphs.js"
WALLS = STATIC_DIR / "screens" / "walls.js"

ENTRY = re.compile(r'^\s*(\w+): \{ word: "([^"]*)", setup: (true|false), glyph: "(\w+)" \},$')


def _table(name: str) -> dict[str, tuple[str, bool, str]]:
    """`states.js`'s table `name`, as {state: (word, setup, glyph)}; every line in it must be an entry."""
    source = STATES.read_text(encoding="utf-8")
    found = re.search(rf"export const {name} = Object\.freeze\(\{{\n(.*?)\n\}}\);", source, flags=re.DOTALL)
    assert found, f"{name} is not where this test reads it"
    table = {}
    for line in found.group(1).splitlines():
        entry = ENTRY.match(line)
        assert entry, f"a line of {name} this test cannot read, so it would check nothing of it: {line!r}"
        key, word, setup, glyph = entry.groups()
        assert key not in table, f"{key} is in {name} twice"
        table[key] = (word, setup == "true", glyph)
    assert table, f"{name} read as empty, so this checks nothing"
    return table


def _quoted(name: str) -> dict[str, tuple[str, bool]]:
    return {key: (word, setup) for key, (word, setup, _glyph) in _table(name).items()}


def _package(part: str) -> dict[str, tuple[str, bool]]:
    return {key: (entry["word"], entry["setup"]) for key, entry in vocabulary()[part].items()}


def _differences(quoted: dict, package: dict) -> list[str]:
    said = [f"{key} is in the package and not in states.js" for key in package.keys() - quoted.keys()]
    said += [f"{key} is in states.js and not in the package" for key in quoted.keys() - package.keys()]
    said += [
        f"{key}: states.js says {quoted[key]}, the package {package[key]}"
        for key in quoted.keys() & package.keys()
        if quoted[key] != package[key]
    ]
    return sorted(said)


def test_every_display_state_s_word_and_setup_flag_is_the_package_s():
    assert _differences(_quoted("DISPLAY_STATES"), _package("display_states")) == []


def test_every_player_state_s_word_and_setup_flag_is_the_package_s():
    assert _differences(_quoted("PLAYER_STATES"), _package("player_states")) == []


def test_the_server_s_states_are_the_package_s_and_the_label_schema_s():
    """The keys the server sends are the keys the screens word: one set, four places."""
    display = set(vocabulary()["display_states"])
    label = contract_schema("schemas/label.v1.schema.json")["properties"]["display_state"]["properties"]["state"]["enum"]

    assert {state.value for state in ScreenState} == display
    assert set(label) == display
    assert {state.value for state in PlayerState} == set(vocabulary()["player_states"])


def test_each_state_is_drawn_with_a_glyph_the_glyph_table_has():
    """A glyph is named by meaning (`core/glyphs.js`); a name the table lacks draws `undefined`."""
    meanings = set(re.findall(r"^\s*(\w+): \"", GLYPHS.read_text(encoding="utf-8"), flags=re.MULTILINE))
    assert meanings, "the glyph table read as empty"
    for name in ("DISPLAY_STATES", "PLAYER_STATES"):
        for key, (_word, _setup, glyph) in _table(name).items():
            assert glyph in meanings, f"{name}.{key} names the glyph {glyph!r}, which core/glyphs.js does not have"


def test_a_state_with_no_word_is_said_as_unreachable_s_word():
    """The package's rule for a reader (`_about`): never another state's word, never blank."""
    source = STATES.read_text(encoding="utf-8")
    fallback = re.search(r'^const NOT_KNOWN = "(\w+)";$', source, flags=re.MULTILINE)

    assert fallback, "states.js names no fallback state"
    assert fallback.group(1) == "unreachable"
    assert vocabulary()["display_states"]["unreachable"]["word"] == "Not known"


def test_the_walls_lead_sentences_are_for_states_the_contract_has():
    """`LEAD_SENTENCES` says more than a badge's word for some states; a key the contract lacks is a stale one."""
    source = WALLS.read_text(encoding="utf-8")
    table = re.search(r"const LEAD_SENTENCES = \{(.*?)\};", source, flags=re.DOTALL)
    assert table, "LEAD_SENTENCES is not where this test reads it"
    keys = set(re.findall(r"^\s*(\w+):", table.group(1), flags=re.MULTILINE))

    assert keys, "the table read as empty, so this checks nothing"
    assert keys <= set(vocabulary()["display_states"])


def test_no_other_client_file_writes_a_state_s_word():
    """`states.js` is the one quote: a second table of the words (Walls' `BADGES` was one) drifts from it.

    A word as a whole string literal, `"Not reporting"`, anywhere else in the
    client is that table coming back. Words that are ordinary English on their
    own ("Showing", "Reporting") are left out, since they are said in prose;
    every state whose word is two or more words is checked, in code (a comment
    may quote one). One use is another vocabulary's and is named: a source
    plugin in a state Settings › Sources cannot name is "Not known" too
    (`core/providers.js`'s `PLUGIN_STATE_WORDS`), which is not a display state.
    """
    other_vocabularies = {("core/providers.js", "Not known")}
    words = {entry["word"] for part in ("display_states", "player_states") for entry in vocabulary()[part].values()}
    phrases = {word for word in words if " " in word}
    assert phrases, "no word of two words, so this checks nothing"
    found = []
    for path in sorted(STATIC_DIR.rglob("*.js")):
        if path == STATES:
            continue
        name = str(path.relative_to(STATIC_DIR))
        code = "\n".join(
            line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith(("*", "/*", "//"))
        )
        found += [
            f"{name}: {phrase!r}" for phrase in phrases if f'"{phrase}"' in code and (name, phrase) not in other_vocabularies
        ]
    assert found == []
    # The one exception is still there, so it is not a stale allowance.
    assert all(f'"{phrase}"' in (STATIC_DIR / name).read_text(encoding="utf-8") for name, phrase in other_vocabularies)
