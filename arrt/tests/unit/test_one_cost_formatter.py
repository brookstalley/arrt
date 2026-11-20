"""Every dollar figure the client shows is written by one helper, `core/spend.js`, or is the server's own sentence.

Audit 2026-11-19 wave 2b, Chunk 62: Ask's reply, General's unattended allowance
and each Watch formatted a cost themselves (`$${watch.spent_usd}`), so a month
with a call whose cost is unknown read as a figure where the server said "at
least $0.42, and 2 calls whose cost is unknown" (`SpendTotal.words`, the one
writer of a cost). A screen now shows the server's `summary`, and a figure the
server sends bare (an estimate, a cap, what is left) goes through `dollars()`.
This refuses a dollar formatted in any module but that one: a `$` written
before an interpolated value, or joined to one with `+`.

Parametrised over every module under `static/`, read from the directory, so a
screen added later is read without anyone adding it here.
"""

import re

import pytest

from arrt.http.pages import STATIC_DIR

#: The one module that writes a dollar sign before a figure: `dollars()`, and
#: the words for a spending tier.
HELPER = STATIC_DIR / "core" / "spend.js"

#: A `$` written before a value the module fills in: `$${…}` in a template, or a
#: quoted "$" joined to something with `+`, on either side. A bare "$" as a
#: field's prefix glyph (`text: "$"`) joins nothing and is not one.
DOLLAR = re.compile(r"""\$\$\{|["'`]\$["'`]\s*\+|\+\s*["'`]\$["'`]""")

MODULES = sorted(STATIC_DIR.rglob("*.js"))


def _code(text: str) -> str:
    """The module without its comments, which may quote what they refuse."""
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.DOTALL)


def formatted_dollars(text: str) -> list[str]:
    """Each line of a module's code that formats a dollar figure itself."""
    return [line.strip() for line in _code(text).splitlines() if DOLLAR.search(line)]


@pytest.mark.parametrize("module", [m for m in MODULES if m != HELPER], ids=lambda m: str(m.relative_to(STATIC_DIR)))
def test_no_module_but_the_helper_formats_a_dollar(module):
    found = formatted_dollars(module.read_text(encoding="utf-8"))
    assert found == [], (
        f"{module.relative_to(STATIC_DIR)} formats a dollar figure itself: show the server's `summary` for a cost, "
        f"or say a bare figure through core/spend.js's dollars(): {found}"
    )


def test_the_modules_are_read_from_the_directory():
    """The parametrisation is not empty, and reaches the screens that once formatted a cost."""
    names = {str(module.relative_to(STATIC_DIR)) for module in MODULES}
    assert {"core/asking.js", "screens/general.js", "screens/watches.js", "screens/run.js", "core/spend.js"} <= names


def test_the_check_reads_the_helper_it_exempts():
    """Falsifiable: the helper itself formats dollars, so the pattern is not one that matches nothing."""
    assert formatted_dollars(HELPER.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "planted",
    [
        'el("dd", { text: `$${watch.spent_usd} spent of $${watch.effective_cap_usd}.` })',
        'const said = "$" + spent;',
        "const said = spent + '$';",
        "return `This reply cost $${metadata.cost_usd}`;",
    ],
)
def test_a_planted_dollar_is_found(planted):
    assert formatted_dollars(f"export function x() {{\n  {planted}\n}}\n") == [planted]


@pytest.mark.parametrize(
    "innocent",
    [
        'el("span", { "aria-hidden": "true", text: "$" })',
        "return `${dollars(watch.effective_cap_usd)} left`;",
        "// a comment quoting `$${spent}` is not code",
        "/* nor is `$${spent}` in a block comment */",
        "const pattern = /^[$]/;",
    ],
)
def test_what_is_not_a_formatted_dollar_is_not_found(innocent):
    assert formatted_dollars(innocent) == []
