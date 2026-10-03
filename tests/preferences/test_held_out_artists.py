"""The procurement corpus's held-out artists stay out of what discovery is shown.

`procurement-corpus.md` § Part B lists artists a curator would predict the owner
likes, and measures discovery by whether it finds them *without being shown them*.
A held-out name that reaches the server's code — a prompt, a few-shot example, a
default, a tool description an MCP client reads — or that is already an artist in
the library, measures memory instead, and the run still looks like a success. So
the leak has to be caught statically: nothing about a discovery run reveals it.

**What this enforces, and what it does not.** It reads every text file under
`arrt/src` and the 2024 library seed (`all.json`). It cannot see the live
library on a deployment, which grows with every acceptance, nor anything a run
is told at runtime; an artist accepted into the library leaves the held-out list
by hand. Tests under `arrt/tests` are not scanned: a fixture does not reach a
model.

**Names come from the artifact's own tables**, so an artist added to the list is
checked without touching this file, and a table this cannot find fails by name
rather than checking nothing.
"""

import functools
import json
import pathlib
import re
import unicodedata

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
ARTIFACT = REPOSITORY_ROOT / ".prawduct" / "artifacts" / "procurement-corpus.md"
SERVER_SOURCE = REPOSITORY_ROOT / "arrt" / "src"
LIBRARY_SEED = REPOSITORY_ROOT / "all.json"

#: The tables whose first column is a held-out artist.
HELD_OUT_TABLES = ("### B1 — established", "### B2 — living, gallery-represented and emerging")

#: Surnames that are ordinary words or common names, checked only as part of the
#: full name: alone they would match code that has nothing to do with the artist
#: ("Pantone" is a colour system, "dory" a boat, "Jackson" a JSON library's name).
COMMON_SURNAMES = frozenset(
    {"smith", "roberts", "jackson", "holmes", "webster", "mitchell", "petersen", "hamilton", "dory", "pantone"}
)


def _table_names(heading: str, text: str) -> list[str]:
    start = text.find(heading)
    if start < 0:
        raise AssertionError(f"procurement-corpus.md has no {heading!r} section; the held-out list cannot be read")
    following = text.find("\n#", start + len(heading))
    section = text[start : following if following >= 0 else len(text)]
    names: list[str] = []
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not line.startswith("|") or not cells[0] or cells[0] == "Artist" or set(cells[0]) <= {"-", " "}:
            continue
        # "Vhils (Alexandre Farto)" is one artist under two names; both are held out.
        outer, _, inner = cells[0].partition("(")
        names.extend(part.strip() for part in (outer, inner.rstrip(")")) if part.strip())
    if not names:
        raise AssertionError(f"the {heading!r} table in procurement-corpus.md has no rows")
    return names


def held_out_names() -> list[str]:
    text = ARTIFACT.read_text(encoding="utf-8")
    return [name for heading in HELD_OUT_TABLES for name in _table_names(heading, text)]


def _folded(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


def _forms(name: str) -> list[str]:
    """The spellings a leak would take: the full name, and a distinctive surname alone."""
    forms = [name]
    surname = name.split()[-1]
    if surname != name and _folded(surname) not in COMMON_SURNAMES:
        forms.append(surname)
    return forms


def _pattern(form: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(_folded(form))}(?!\w)")


@functools.cache
def _server_texts() -> dict[str, str]:
    texts: dict[str, str] = {}
    for path in sorted(SERVER_SOURCE.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            texts[str(path.relative_to(REPOSITORY_ROOT))] = _folded(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
    return texts


@functools.cache
def _library_artists() -> frozenset[str]:
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"artist", "creator"} and isinstance(value, str):
                    found.add(_folded(value.split("(")[0].strip()))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(json.loads(LIBRARY_SEED.read_text(encoding="utf-8")))
    return frozenset(found)


def test_the_held_out_list_and_what_it_is_checked_against_exist():
    assert held_out_names(), "no held-out names were read"
    assert _server_texts(), f"nothing readable under {SERVER_SOURCE}"
    assert _library_artists(), f"no artists read from {LIBRARY_SEED}"


@pytest.mark.parametrize("name", held_out_names())
def test_no_held_out_artist_is_named_in_the_server(name: str):
    # A plain substring test first: the word-boundary pattern is the judge, but run
    # over every file for every name it costs seconds, and a miss needs no judge.
    leaks = [
        f"{path} ({form!r})"
        for form in _forms(name)
        for path, text in _server_texts().items()
        if _folded(form) in text and _pattern(form).search(text)
    ]
    assert not leaks, f"{name} is held out of discovery but the server names them: {', '.join(leaks)}"


@pytest.mark.parametrize("name", held_out_names())
def test_no_held_out_artist_is_already_in_the_library(name: str):
    assert (
        _folded(name) not in _library_artists()
    ), f"{name} has a work in the library seed, so discovery is shown them; they cannot be held out"
