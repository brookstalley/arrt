"""No control in the client navigates by a button.

`information-architecture.md` § Direction: navigation is a link, an act is a
button. A link is built with `link()` (`core/router.js`), which gives it an
`href` and still routes a plain click through `go`. So the shape this refuses
is `go(` bound straight to a click — `onclick: () => go(…)`, or a row's `open`
handler that a button calls — which is what every list in the client was
built from before the norm, and what a new screen copies from an old one.

Read from the files, as `test_client_vocabulary.py` reads them, because the
client is not a Python module and nothing else would notice.

What stays a `go(` call, and why the pattern does not match it:

- after a write, an act that lands somewhere: Ask starts a search and opens it
  (`go` inside a `guard(async () => { … })` block, not the click's expression);
- a form's submit: the top-bar search and *Find a topic*;
- a filter or a View, Sort or Theme toggle on the page showing: `goWithParams`,
  a change to this page's state rather than a different page;
- the top-bar search's suggestions, which are `role="option"` rows in a
  combobox — the ARIA pattern for that widget, whose rows are chosen with the
  arrow keys and Enter and cannot be links.
"""

import re

import pytest

from arrt.http.pages import STATIC_DIR

#: Every module but the router, which is where `link` itself calls `go`.
CLIENT_PATHS = sorted(path for path in STATIC_DIR.rglob("*.js") if path.relative_to(STATIC_DIR).as_posix() != "core/router.js")

#: A click handler, or a row's `open` (a key or a variable), whose arrow body is an expression
#: calling `go(` — directly, or in a conditional choosing between two.
CLICK_BOUND = re.compile(r"\b(?:onclick|open)\s*[:=]\s*\([^)]*\)\s*=>\s*\(?[^{};\n]*?\bgo\(")

#: A click listener whose arrow body is `go(…)`.
LISTENER_BOUND = re.compile(r'addEventListener\(\s*"click"\s*,\s*\([^)]*\)\s*=>\s*\(?\s*go\(')


def offences(source: str) -> list[str]:
    found = []
    for pattern in (CLICK_BOUND, LISTENER_BOUND):
        for match in pattern.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            found.append(f"line {line}: {match.group(0).strip()}")
    return found


def test_the_modules_were_gathered():
    names = {path.relative_to(STATIC_DIR).as_posix() for path in CLIENT_PATHS}
    assert "app.js" in names
    assert any(name.startswith("screens/") for name in names)


@pytest.mark.parametrize("path", CLIENT_PATHS, ids=lambda path: path.relative_to(STATIC_DIR).as_posix())
def test_no_control_navigates_by_a_button(path):
    found = offences(path.read_text(encoding="utf-8"))
    assert not found, (
        f"{path.relative_to(STATIC_DIR)} navigates on a click without a link; build it with link() "
        f"from core/router.js (information-architecture.md § Direction): {found}"
    )


@pytest.mark.parametrize(
    "shape",
    [
        'el("button", { type: "button", text: work.title, onclick: () => go("work", work.artwork_id) })',
        'onclick: () => (run.kind === "get" ? go("run", run.run_id) : go("review", run.run_id)),',
        'open: () => go("artist", artist.artist_id),',
        'const open = () => go("artist", artist.artist_id);',
        'node.addEventListener("click", () => go("health"));',
    ],
)
def test_it_catches_each_shape_the_client_was_built_from(shape):
    assert offences(shape), shape


@pytest.mark.parametrize(
    "shape",
    [
        'link({ view: "work", id: work.artwork_id }, { text: work.title })',
        'onclick: () => guard(async () => {\n  const run = await api("/api/runs");\n  go("run", run.run_id);\n})',
        'onclick: () => goWithParams({ filters: "" }),',
        'option("suggestion-ask", `Ask about “${query}”`, () => go("discover", null, { term: query }))',
    ],
)
def test_it_leaves_acts_and_links_alone(shape):
    assert not offences(shape), shape
