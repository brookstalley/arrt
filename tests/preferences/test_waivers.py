"""Every lint waiver says why, in one form, in every plane.

A per-line `noqa` is how this repository records a deliberate exception to a rule
it otherwise holds everywhere (the owner's 2026-10-05 ruling to select every rule
ruff has). A waiver without its reason is an exception nobody can audit: it reads
the same whether it was argued for or copied from the line above. The form is the
one the logging row in `project-preferences.md` specifies, `# noqa: CODES --
reason`, or a `noqa` paired with a prawduct pragma, which carries its own reason.

Comments are found with the tokenizer, so a docstring that mentions `# noqa` is
prose and not a waiver.
"""

import io
import pathlib
import re
import subprocess
import tokenize

_REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]

_REASONED = re.compile(r"# noqa: [A-Z]+[0-9]+(?:, [A-Z]+[0-9]+)*(?: -- \S|  # prawduct:allow \S+ -- \S)")


def _python_files() -> list[pathlib.Path]:
    names = subprocess.run(
        ["git", "ls-files", "-z", "*.py"], cwd=_REPOSITORY_ROOT, capture_output=True, check=True, text=True
    ).stdout.split("\0")
    files = [_REPOSITORY_ROOT / name for name in names if name]
    assert len(files) > 100, "git ls-files found almost no Python; the check would be vacuous"
    return files


def unreasoned_waivers(source: str) -> list[int]:
    """The line numbers of every `noqa` comment not in the reasoned form."""
    found = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT and "noqa" in token.string and not _REASONED.search(token.string):
            found.append(token.start[0])
    return found


def test_every_waiver_says_why():
    offenders = [
        f"{path.relative_to(_REPOSITORY_ROOT)}:{line}"
        for path in _python_files()
        for line in unreasoned_waivers(path.read_text(encoding="utf-8"))
    ]

    assert not offenders, "waivers without a reason (`# noqa: CODE -- why`):\n" + "\n".join(offenders)


def test_the_check_knows_a_reason_from_its_absence():
    assert unreasoned_waivers("x = 1  # noqa: E501\n") == [1]
    assert unreasoned_waivers("x = 1  # noqa: E501 - single dash\n") == [1]
    assert unreasoned_waivers("x = 1  # noqa\n") == [1]
    assert unreasoned_waivers("x = 1  # noqa: E501 -- the URL cannot wrap\n") == []
    assert unreasoned_waivers("x = 1  # noqa: BLE001, S110 -- both\n") == []
    assert (
        unreasoned_waivers(
            "try:\n    pass\nexcept Exception:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- why\n    pass\n"
        )
        == []
    )
    assert unreasoned_waivers('"""Mentions # noqa in prose."""\n') == []
