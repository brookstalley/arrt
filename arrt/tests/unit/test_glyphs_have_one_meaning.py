"""Each glyph means one thing, and every screen takes it from one table.

A glyph is the signal on a badge that survives greyscale and a dimmed room,
so a reader learns it once. That only holds if ● on the Work page and ● on the
Queue mean the same thing. When each screen chose its own, ◇ meant "matted
small", "cool" and "you chose". `core/glyphs.js` names each glyph by its
meaning, so these checks keep the table one-to-one and keep every screen
going through it.
"""

import re

from arrt.http.pages import STATIC_DIR

GLYPHS_JS = STATIC_DIR / "core" / "glyphs.js"
APP_JS = STATIC_DIR / "app.js"
INDEX_HTML = STATIC_DIR / "index.html"

#: The status line's first paint, before any script runs, so it cannot import
#: the table and spells the glyph as a character reference. Held to the table
#: here instead.
INDEX_GLYPHS = {"waiting": "&#x25CC;"}

# The sidebar icons that are also badge glyphs, because each means the same
# thing in both places: Activity is where fetching happens, Wanted holds the
# wanted.
SHARED_WITH_THE_SIDEBAR = {"moving", "wanted"}

# Glyphs that are also ordinary punctuation: "?" is JavaScript's conditional
# and "—" is prose's dash, so a scan of the source cannot tell a badge from a
# sentence. They stay in the table, which is what keeps them unshared.
PUNCTUATION = {"unknown", "cannot"}


def _without_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", lambda match: "\n" * match.group().count("\n"), source, flags=re.DOTALL)
    return re.sub(r"(?<!:)//[^\n]*", "", source)


def _table() -> dict[str, str]:
    body = _without_comments(GLYPHS_JS.read_text())
    return dict(re.findall(r'^\s*(\w+): "([^"]+)",$', body, flags=re.MULTILINE))


def _sidebar_glyphs() -> set[str]:
    return set(re.findall(r'glyph: "([^"]+)"', _without_comments(APP_JS.read_text())))


def test_the_table_is_read():
    # The other checks pass vacuously on an empty table, so the parse is pinned.
    table = _table()
    assert {"good", "problem", "refused", "wanted"} <= table.keys()
    assert table["good"] == "●"


def test_no_two_meanings_share_a_glyph():
    table = _table()
    by_glyph: dict[str, list[str]] = {}
    for meaning, glyph in table.items():
        by_glyph.setdefault(glyph, []).append(meaning)
    shared = {glyph: meanings for glyph, meanings in by_glyph.items() if len(meanings) > 1}
    assert not shared, f"one glyph, several meanings: {shared}"


def test_the_sidebar_shares_a_glyph_only_where_it_means_the_same():
    table = _table()
    shared = {meaning for meaning, glyph in table.items() if glyph in _sidebar_glyphs()}
    assert shared == SHARED_WITH_THE_SIDEBAR


def test_no_screen_writes_a_glyph_of_its_own():
    table = _table()
    assert table.keys() >= PUNCTUATION
    glyphs = {glyph for meaning, glyph in table.items() if meaning not in PUNCTUATION}
    found = []
    for path in sorted(STATIC_DIR.rglob("*.js")):
        if path == GLYPHS_JS:
            continue
        source = _without_comments(path.read_text())
        if path == APP_JS:
            # The section icons are declared there, one per section.
            source = re.sub(r'glyph: "[^"]+"', "", source)
        found.extend(
            f"{path.relative_to(STATIC_DIR)}:{number} writes {character}"
            for number, line in enumerate(source.splitlines(), start=1)
            for character in set(line) & glyphs
        )
    assert not found, "a glyph is taken from core/glyphs.js by meaning:\n" + "\n".join(found)


def test_every_meaning_a_screen_names_is_in_the_table():
    table = _table()
    unknown = sorted(
        f"{path.relative_to(STATIC_DIR)} names GLYPHS.{meaning}"
        for path in STATIC_DIR.rglob("*.js")
        for meaning in set(re.findall(r"GLYPHS\.(\w+)", _without_comments(path.read_text())))
        if meaning not in table
    )
    assert not unknown, "a meaning core/glyphs.js lacks draws as 'undefined':\n" + "\n".join(unknown)


def test_the_page_shell_writes_no_glyph_of_its_own():
    table = _table()
    shell = INDEX_HTML.read_text()
    for meaning, reference in INDEX_GLYPHS.items():
        assert reference in shell
        assert chr(int(reference[3:-1], 16)) == table[meaning]
    glyphs = {glyph for meaning, glyph in table.items() if meaning not in PUNCTUATION}
    assert not set(shell) & glyphs, "index.html writes a glyph rather than its character reference"
