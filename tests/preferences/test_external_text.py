"""No script in the curation client parses markup (`security-model.md` § Direction).

Titles, descriptions and labels come from museums, from Wikidata, which anyone can
edit, and from a model. The client builds every node with `el`, which sets text
through `textContent`, so a title carrying `<img src=x onerror=…>` arrives as
words. That holds only while nothing anywhere in the client hands a string to the
HTML parser, and this file is what notices the first line that does.

**Every script under `static/` is read**, found by walking the directory rather
than from a list, so a new screen is covered by existing, and every page there
is checked for script of its own. Comments are removed before the search,
because the client's own comments name `innerHTML` to forbid it.

**What this cannot see:** a sink reached indirectly, such as a property name
assembled from strings, and a sink on a line after a `//` or `/*` inside a string
literal, which the comment stripper takes for a comment. Neither is a mistake
anyone makes by accident, and the Critic reads for them.
"""

import pathlib
import re

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
STATIC = REPOSITORY_ROOT / "arrt" / "src" / "arrt" / "http" / "static"

#: Each way a script can turn a string into markup or code, as it is written at
#: the call site.
SINKS = {
    "innerHTML": re.compile(r"\binnerHTML\b"),
    "outerHTML": re.compile(r"\bouterHTML\b"),
    "insertAdjacentHTML": re.compile(r"\binsertAdjacentHTML\b"),
    "setHTMLUnsafe": re.compile(r"\bsetHTMLUnsafe\b"),
    "parseHTMLUnsafe": re.compile(r"\bparseHTMLUnsafe\b"),
    "document.write": re.compile(r"\bdocument\s*\.\s*write(?:ln)?\b"),
    "DOMParser.parseFromString": re.compile(r"\bparseFromString\b"),
    "createContextualFragment": re.compile(r"\bcreateContextualFragment\b"),
    "srcdoc": re.compile(r"\bsrcdoc\b"),
    "eval": re.compile(r"\beval\s*\("),
    "new Function": re.compile(r"\bnew\s+Function\s*\("),
    # A timer handed a string compiles it, as eval does; handed a function, it does not.
    "string timer": re.compile(r"\bset(?:Timeout|Interval)\s*\(\s*[\"'`]"),
}

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
#: A line comment starts at `//` preceded by the line's start or by whitespace.
#: The `:` in `https://` precedes it otherwise, so a URL in a string survives.
_LINE_COMMENT = re.compile(r"(^|\s)//.*$", re.MULTILINE)


def _code(source: str) -> str:
    return _LINE_COMMENT.sub(r"\1", _BLOCK_COMMENT.sub(" ", source))


def _scripts() -> list[pathlib.Path]:
    return sorted(path for pattern in ("*.js", "*.mjs") for path in STATIC.rglob(pattern))


def _pages() -> list[pathlib.Path]:
    return sorted(STATIC.rglob("*.html"))


def test_the_client_has_scripts_to_read():
    """A moved `static/` would leave the test below reading nothing and passing."""
    names = {path.relative_to(STATIC).as_posix() for path in _scripts()}
    assert "app.js" in names and "core/render.js" in names


@pytest.mark.parametrize("path", _scripts(), ids=lambda path: path.relative_to(STATIC).as_posix())
def test_no_client_script_parses_markup(path):
    code = _code(path.read_text(encoding="utf-8"))
    found = [name for name, sink in SINKS.items() if sink.search(code)]
    assert not found, (
        f"{path.relative_to(REPOSITORY_ROOT)} uses {', '.join(found)}. Outside text reaches the page as text "
        "(security-model.md § Direction): build the node with el() from core/render.js."
    )


#: An inline script with a body, or an `on…=` handler attribute: script a page
#: runs that no `.js` file holds, so the scan above would not read it.
_INLINE_SCRIPT = re.compile(r"<script\b(?![^>]*\bsrc=)[^>]*>\s*\S", re.IGNORECASE)
_HANDLER_ATTRIBUTE = re.compile(r"<[^>]*\son[a-z]+\s*=", re.IGNORECASE)


@pytest.mark.parametrize("path", _pages(), ids=lambda path: path.relative_to(STATIC).as_posix())
def test_no_page_carries_script_of_its_own(path):
    page = re.sub(r"<!--.*?-->", " ", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    assert not _INLINE_SCRIPT.search(page) and not _HANDLER_ATTRIBUTE.search(
        page
    ), f"{path.relative_to(REPOSITORY_ROOT)} carries inline script, which the sink scan does not read."


#: One line per sink that uses it and nothing else.
PLANTED = [
    ("innerHTML", "node.innerHTML = title;"),
    ("outerHTML", "node.outerHTML = `<b>${title}</b>`;"),
    ("insertAdjacentHTML", "list.insertAdjacentHTML('beforeend', row);"),
    ("setHTMLUnsafe", "node.setHTMLUnsafe(title);"),
    ("parseHTMLUnsafe", "Document.parseHTMLUnsafe(title);"),
    ("document.write", "document.write(title);"),
    ("DOMParser.parseFromString", "new DOMParser().parseFromString(title, 'text/html');"),
    ("createContextualFragment", "range.createContextualFragment(title);"),
    ("srcdoc", "frame.srcdoc = title;"),
    ("eval", "window.eval(answer);"),
    ("new Function", "const run = new Function(answer);"),
    ("string timer", "setTimeout('run()', 10);"),
]


@pytest.mark.parametrize(("name", "line"), PLANTED, ids=[name for name, _ in PLANTED])
def test_each_sink_is_recognised_in_code(name, line):
    """Each pattern is shown to fire on its own line, so a typo in one cannot pass as a clean client."""
    assert SINKS[name].search(_code(line))


def test_every_sink_has_a_planted_line():
    assert {name for name, _ in PLANTED} == set(SINKS)


def test_a_timer_handed_a_function_is_not_a_sink():
    assert not SINKS["string timer"].search("setTimeout(() => run(), 10);")


def test_inline_script_is_recognised():
    assert _INLINE_SCRIPT.search("<script>alert(1)</script>")
    assert _HANDLER_ATTRIBUTE.search('<img src="x" onerror="alert(1)">')
    assert not _INLINE_SCRIPT.search('<script type="module" src="/static/app.js"></script>')


def test_comments_and_urls_are_not_mistaken_for_code():
    source = (
        "/* TEXT IS SET WITH textContent, NEVER innerHTML. */\n"
        "// never eval( anything\n"
        'const link = "https://commons.wikimedia.org/x"; // not innerHTML\n'
        "node.textContent = title;\n"
    )
    code = _code(source)
    assert not any(sink.search(code) for sink in SINKS.values())
    assert "https://commons.wikimedia.org/x" in code
