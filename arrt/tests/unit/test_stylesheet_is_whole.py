"""The stylesheet's rules are all closed.

A rule left open does not fail to load: the browser reads every rule after it
as nested inside it, so a whole screen's styling silently stops applying while
everything else looks right. Concatenating two appended blocks at a merge is
the way it happens, so the check is structural and names the line.
"""

import re

from arrt.http.pages import STATIC_DIR


def test_every_rule_in_the_stylesheet_is_closed():
    # Comments blanked to newlines, so line numbers still point at the file.
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), (STATIC_DIR / "app.css").read_text(), flags=re.DOTALL)
    open_blocks: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for character in line:
            if character == "{":
                # Only an at-rule (@media, @supports) may hold another rule; this
                # stylesheet uses no CSS nesting.
                assert all(
                    block.startswith("@") for block in open_blocks
                ), f"app.css line {number} opens a rule inside {open_blocks[-1]!r}, which was never closed"
                open_blocks.append(line.strip())
            elif character == "}":
                assert open_blocks, f"app.css line {number} closes a rule that was never opened"
                open_blocks.pop()
    assert not open_blocks, f"app.css ends with {open_blocks[-1]!r} still open"
