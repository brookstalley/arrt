"""Every date the client shows is written by one formatter, `core/dates.js`.

`ux-review-2026-10.md` finding 20: To review and History showed
`2026-10-05T14:46:52.225416+00:00`, while Clients and Queue wrote dates for
people, each with its own copy of the formatting. One formatter is what makes
"a readable date and how long ago" the only way a moment reaches a screen, so
this refuses a date formatted anywhere else, and runs the formatter itself.
The browser half — no ISO timestamp on any screen outside a Details disclosure
— is `tests/browser/test_no_machine_dates.py`.

Shells out to `node` for the runs and skips them without it, the bargain
`test_route_parsing.py` states; the static check needs nothing.
"""

import json
import re
import shutil
import subprocess

import pytest

from arrt.http.pages import STATIC_DIR

DATES = STATIC_DIR / "core" / "dates.js"

#: The calls that turn an instant into words. `toLocaleString` on a number (a
#: file count) is not one, so the pattern asks for the date options or a Date.
FORMATTING = re.compile(r"Intl\.DateTimeFormat|toLocale(?:Date|Time)String|dateStyle|timeStyle|toISOString|new Date\(")


def _code(path):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)


def test_no_module_but_the_formatter_formats_a_date():
    elsewhere = sorted(
        f"{path.relative_to(STATIC_DIR)}: {match.group(0)}"
        for path in STATIC_DIR.rglob("*.js")
        if path != DATES
        for match in FORMATTING.finditer(_code(path))
    )
    assert elsewhere == [], f"format dates with core/dates.js (dated, stamp) instead: {elsewhere}"


def test_the_check_reads_the_formatter_it_exempts():
    """Falsifiable: the formatter itself matches, so the pattern is not one that matches nothing."""
    assert FORMATTING.search(_code(DATES))


def run(expression: str) -> object:
    if shutil.which("node") is None:
        pytest.skip("node is not installed; this check is opportunistic")
    driver = f"""
        const dates = await import({json.dumps(DATES.as_uri())});
        process.stdout.write(JSON.stringify({expression}));
    """
    result = subprocess.run(  # noqa: S603 -- a fixed argv over a repo file
        ["node", "--input-type=module", "--eval", driver],  # noqa: S607 -- whatever node is on PATH, skipped without one
        capture_output=True,
        text=True,
        check=False,
        env={"TZ": "UTC", "LANG": "en_GB.UTF-8", "PATH": __import__("os").environ["PATH"]},
    )
    assert result.returncode == 0, f"core/dates.js could not be run:\n{result.stderr}"
    return json.loads(result.stdout)


ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
INSTANT = "2026-10-05T14:46:52.225416+00:00"
THREE_DAYS_LATER = "Date.parse('2026-10-08T14:46:52Z')"


def test_a_moment_reads_as_a_date_and_how_long_ago():
    said = run(f"dates.dated({json.dumps(INSTANT)}, {THREE_DAYS_LATER})")

    assert not ISO.search(said)
    assert "2026" in said
    assert said.endswith("(3 days ago)")


def test_a_time_element_carries_the_instant_only_where_a_machine_reads_it():
    stamp = run(f"dates.stamp({json.dumps(INSTANT)}, {THREE_DAYS_LATER})")

    assert stamp["datetime"] == INSTANT
    assert not ISO.search(stamp["text"])
    assert stamp["text"].endswith("(3 days ago)")


@pytest.mark.parametrize("instant", [None, "not a date"])
def test_an_instant_that_will_not_parse_is_said_to_be_unknown_not_shown(instant):
    assert run(f"dates.dated({json.dumps(instant)})") == "an unknown time"
