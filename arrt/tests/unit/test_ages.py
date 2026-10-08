"""The client's ages read exactly as the server's, and its staleness threshold holds.

Clients prints the server's sentence about a report ("It last reported 4
minutes ago."), and Walls composes its own line about the same report with
`core/dates.js`. #295's acceptance is that the two pages agree for one report, so
the client's words are run here against `observations.ago` over the ages where
they could part: every unit boundary, the halves Python rounds to even and
`Math.round` would not, and a report stamped in the future.

`core/outputs.js`'s `screenState` is driven here too, at the threshold and either
side of it, because the threshold is a comparison a browser test would reach
only at one age.

Shells out to `node` and skips without it, the bargain `test_route_parsing.py`
states.
"""

import json
import shutil
import subprocess

import pytest

from arrt.http.pages import STATIC_DIR
from arrt.observations import ago

AGES_MODULE = STATIC_DIR / "core" / "dates.js"
OUTPUTS_MODULE = STATIC_DIR / "core" / "outputs.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is not installed; this check is opportunistic",
)

#: Each unit's edges, the halves where the two roundings differ (2.5 minutes is
#: 150 seconds: Python says 2, `Math.round` 3), and the future.
AGES = [
    0,
    0.5,
    1,
    1.5,
    2.5,
    41.2,
    89.4,
    89.6,
    90,
    150,
    210,
    179.9,
    180,
    180.1,
    3599,
    5399,
    5400,
    9000,
    172799,
    172800,
    216000,
    302400,
    604800,
    -1,
    -150,
    -7200,
]


def run(driver: str) -> object:
    result = subprocess.run(  # noqa: S603 -- a fixed argv over repo files
        ["node", "--input-type=module", "--eval", driver],  # noqa: S607 -- whatever node is on PATH, skipped without one
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"the client module could not be run:\n{result.stderr}"
    return json.loads(result.stdout)


def test_every_age_reads_as_the_server_reads_it():
    said = run(f"""
        const module = await import({json.dumps(AGES_MODULE.as_uri())});
        process.stdout.write(JSON.stringify({json.dumps(AGES)}.map((age) => module.ago(age))));
        """)
    assert said == [ago(age) for age in AGES]


def test_a_half_rounds_to_even_as_python_does():
    """The case the port exists to get right, named so a regression says what it is."""
    said = run(f"""
        const module = await import({json.dumps(AGES_MODULE.as_uri())});
        process.stdout.write(JSON.stringify([module.ago(150), module.ago(210)]));
        """)
    assert said == ["2 minutes ago", "4 minutes ago"]


def screen_states(ages: list[float | None]) -> list[str]:
    """`screenState` for a report of each age listing hdmi-a-1 as connected."""
    return run(f"""
        const module = await import({json.dumps(OUTPUTS_MODULE.as_uri())});
        const ages = {json.dumps(ages)};
        const outputs = [{{ name: "hdmi-a-1", kind: "framebuffer", connected: true, screen: [1920, 1080] }}];
        process.stdout.write(JSON.stringify(ages.map((age) =>
            module.screenState({{ absent: false, problem: null, age_seconds: age, outputs }}, "hdmi-a-1"))));
        """)


def test_a_report_past_three_heartbeats_is_stale_and_one_at_the_threshold_is_not():
    assert screen_states([41.2, 180, 180.5, 3600]) == ["detected", "detected", "stale", "stale"]


def test_a_report_from_the_future_is_said_as_it_is_not_called_stale():
    assert screen_states([-600]) == ["detected"]


def test_a_stale_line_states_the_age_in_the_servers_words():
    line = run(f"""
        const module = await import({json.dumps(OUTPUTS_MODULE.as_uri())});
        const line = module.wallScreenLine("Hall Pi", "hdmi-a-1", module.STALE, {{ age_seconds: 432000 }});
        process.stdout.write(JSON.stringify(line));
        """)
    assert line == (
        f"Assigned to Hall Pi on hdmi-a-1. Hall Pi last reported {ago(432000)}, so whether a screen is there now is not known."
    )
    assert "Shown by" not in line
