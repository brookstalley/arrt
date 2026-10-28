"""No source file is silently excluded from version control.

This exists because of a real near-miss: the stock Python `.gitignore` carries an
unanchored `MANIFEST` rule for the setuptools artifact, and on a case-insensitive
filesystem (macOS) that also matched `arrt/src/arrt/programming/manifest/` — the
feed builder, which publishes what every Player shows. The
package existed on disk, imports succeeded, and tests passed; it was simply never
committed. A fresh clone, or the Pi, would have had a missing module.

The failure mode is invisible by construction, so it gets a mechanical guard
rather than vigilance.
"""

import pathlib
import subprocess

import pytest
from repository import ROOT, projects

#: Every tree whose absence from a fresh clone would matter: each project's
#: `src` and `tests`, its `tools` where it has one, and the root's own `tests`.
#: A project's tests carry almost all of its coverage, and a tree the guard does
#: not walk is exactly the tree this guard was built for: the suite stays green
#: locally while the clone quietly loses it. The `tools/` trees are here because
#: an operator runs them by hand.
SOURCE_TREES = (
    "tests",
    *(
        f"{project}/{tree}"
        for project in projects()
        for tree in ("src", "tests", "tools")
        if tree != "tools" or (ROOT / project / "tools").is_dir()
    ),
)


@pytest.fixture(autouse=True)
def _at_the_repository_root(monkeypatch):
    """Every path and git call below is relative to the repository root, wherever pytest was started."""
    monkeypatch.chdir(ROOT)


def _ignored(paths: list[pathlib.Path]) -> list[str]:
    """Return the subset of `paths` that git would exclude."""
    if not paths:
        return []
    # `--no-index` is load-bearing. Without it git skips paths already in the
    # index, because ignore rules genuinely do not apply to tracked files — so
    # the check would pass for anything already committed and could never fail
    # on a bad rule once the damage was undone. We want the stronger invariant:
    # no ignore rule matches a source path, whatever the index currently holds.
    result = subprocess.run(
        ["git", "check-ignore", "--stdin", "--no-index"],
        input="\n".join(str(p) for p in paths),
        capture_output=True,
        text=True,
        check=False,
    )
    # Exit 0 = some paths ignored, 1 = none ignored. Anything else is a real error.
    assert result.returncode in (0, 1), f"git check-ignore failed: {result.stderr}"
    return [line for line in result.stdout.splitlines() if line]


@pytest.mark.parametrize("tree", SOURCE_TREES)
def test_every_tree_the_scan_names_exists(tree):
    """Each tree on its own, because the scans below skip a missing one.

    Their own check is that *something* was found, which a single misspelled or
    moved tree cannot fail while the others still hold files.
    """
    assert pathlib.Path(tree).is_dir(), f"{tree} is not a directory, so the scans below pass over nothing there"


def test_no_python_source_is_gitignored():
    candidates: list[pathlib.Path] = []
    for tree in SOURCE_TREES:
        root = pathlib.Path(tree)
        if root.exists():
            candidates.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)

    assert candidates, "expected to find source files; has the layout moved?"
    ignored = _ignored(candidates)
    assert not ignored, "these source files would never be committed:\n" + "\n".join(ignored)


def test_no_package_directory_is_gitignored():
    """Directories matter separately: an ignored dir hides files that look fine alone."""
    candidates: list[pathlib.Path] = []
    for tree in SOURCE_TREES:
        root = pathlib.Path(tree)
        if root.exists():
            candidates.extend(p for p in root.rglob("*") if p.is_dir() and p.name != "__pycache__")

    assert candidates, "expected to find package directories; has the layout moved?"
    ignored = _ignored(candidates)
    assert not ignored, "these package directories would never be committed:\n" + "\n".join(ignored)


def test_the_tv_token_is_not_tracked():
    """It was committed to a public repo once. Keep it from happening twice."""
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.splitlines()
    offenders = [p for p in tracked if pathlib.Path(p).name in {"token_file", ".env"}]
    assert not offenders, f"credential files must never be tracked: {offenders}"


#: The systemd unit for running the server outside its container, and the
#: restart policy it is supposed to have.
#: A clean exit from the server is somebody stopping it on purpose and it should
#: stay stopped; the walls go on rotating the feed they last pulled either way.
#: Arrt Player's unit is guarded in its own repository, where its own restart
#: policy (`always`) is pinned.
#:
#: A mapping, not one path, because the properties below are each unit's own and a
#: second unit joins them by being listed here.
LIVE_UNITS = {
    pathlib.Path("deploy/curation.service"): "on-failure",
}


def _directives_of(unit: pathlib.Path) -> dict[str, list[str]]:
    """Map each directive in `unit` to every value assigned to it."""
    directives: dict[str, list[str]] = {}
    for raw in unit.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        key, _, value = line.partition("=")
        directives.setdefault(key.strip(), []).append(value.strip())
    return directives


@pytest.mark.parametrize("unit", sorted(LIVE_UNITS), ids=lambda p: p.stem)
def test_a_live_unit_declares_its_environment_file(unit: pathlib.Path):
    """A unit that runs declares its environment file, un-prefixed.

    The server's settings refuse to start without their deployment values, and an
    `EnvironmentFile=` the unit does not declare — or declares with a `-` prefix,
    making it optional — turns a missing file into an import-time crash nobody
    connects back to a file that was never placed.
    """
    values = _directives_of(unit).get("EnvironmentFile", [])
    assert values, f"{unit.name} must declare EnvironmentFile=; the server requires deployment values at import"
    assert not any(v.startswith("-") for v in values), f"{unit.name}: EnvironmentFile= must not be optional: {values}"


@pytest.mark.parametrize("unit", sorted(LIVE_UNITS), ids=lambda p: p.stem)
def test_a_live_unit_cannot_silently_stop_retrying(unit: pathlib.Path):
    """The stock rate limit turns a reproducible fault into a unit that gave up.

    Five starts in ten seconds is exhausted in about half a second by a fault that
    reproduces on every start, leaving `failed` permanently after five log lines.
    That is the failure the product's requirement about unattended faults being
    visible exists to prevent.
    """
    directives = _directives_of(unit)
    assert directives.get("Restart") == [LIVE_UNITS[unit]], f"{unit.name}: restart policy is deliberate — see LIVE_UNITS for why"
    assert directives.get("StartLimitIntervalSec") == [
        "0"
    ], f"{unit.name}: start rate limiting must be disabled, or a crash loop ends in a silent permanent `failed`"
    restart_sec = directives.get("RestartSec", [])
    assert restart_sec, f"{unit.name}: RestartSec= must be set; the 100ms default is what exhausts the allowance"
    assert int(restart_sec[0]) >= 5, f"{unit.name}: RestartSec= must leave a real gap, got {restart_sec[0]}"


def test_the_curation_unit_treats_a_clean_stop_as_success():
    """`Restart=on-failure` plus a SIGTERM that reads as failure is a restart loop.

    The curation plane hands its shutdown to uvicorn, which exits **143** on
    SIGTERM. Under `on-failure` — which is this unit's policy, pinned above — that
    is a failure, so `systemctl stop` left the unit `failed` and restarted it:
    stopping the service was what started it again. Both forms are required and
    they are different events: `143` is a process that *exited* with that status,
    `SIGTERM` one that died of the signal unhandled, which is what a shutdown
    hanging past the stop timeout produces.

    **Pinned because the line is invisible when it works.** Its whole effect is
    the absence of a spurious `failed`, so a revision that dropped it would look
    correct in every place anybody reads — and the fault it reintroduces appears
    only on a real stop against a real machine.

    A unit under `Restart=always` would not need it: there, the exit status does
    not decide whether it comes back.
    """
    unit = pathlib.Path("deploy/curation.service")
    assert LIVE_UNITS[unit] == "on-failure", "this test's premise is the on-failure policy pinned above"

    values = _directives_of(unit).get("SuccessExitStatus", [])
    assert values, "SuccessExitStatus= must be set, or uvicorn's 143 on SIGTERM reads as a failed stop"
    declared = set(values[0].split())
    assert {"143", "SIGTERM"} <= declared, f"both forms are required and mean different events, got {sorted(declared)}"


@pytest.mark.parametrize("unit", sorted(LIVE_UNITS), ids=lambda p: p.stem)
def test_a_live_unit_names_no_path_under_a_home_directory(unit: pathlib.Path):
    """The cutover moved both trees off `/home`, and this is what keeps them off.

    A `--system` account with `nologin` may have no home at all, and the one here
    has a `0750` state directory it cannot serve files from. Every `/home/...`
    path these units carried named a directory that did not exist on the rebuilt
    card — the failure was total and the diagnosis was not obvious, because
    systemd reports it as a unit that will not start rather than as a path that is
    wrong. Asserted over values rather than the whole line so the explanatory
    comments, which legitimately discuss the retired paths, do not trip it.
    """
    offenders = [f"{key}={value}" for key, values in _directives_of(unit).items() for value in values if "/home/" in value]
    assert not offenders, f"{unit.name} must name no path under a home directory: {offenders}"


@pytest.mark.parametrize("unit", sorted(LIVE_UNITS), ids=lambda p: p.stem)
def test_a_live_unit_names_its_interpreter_absolutely(unit: pathlib.Path):
    """`/usr/bin/env uv` resolves against a PATH the service account does not have.

    systemd's PATH carries no per-user directory, and the account these units run
    as has no login and no home to install one under, so `env uv` finds nothing.
    The alternative fix — an `Environment=PATH=` line — is how the recovered 2024
    unit came to carry pyenv shims and a stray editor directory that happened to be
    in somebody's shell. An absolute path fails where it is written instead.
    """
    exec_starts = _directives_of(unit).get("ExecStart", [])
    assert exec_starts, f"{unit.name} must declare ExecStart="
    for value in exec_starts:
        assert value.startswith("/"), f"{unit.name}: ExecStart= must be absolute, got {value!r}"
        assert not value.startswith("/usr/bin/env "), f"{unit.name}: ExecStart= must not resolve through env: {value!r}"
