"""The Player's repository keeps its source committed, its secrets out, and its deployment values in `.env`.

Carried from the repository-wide guards when Arrt Player moved into a
repository of its own, so each still holds here:

- **No source is silently excluded from version control.** An unanchored
  `.gitignore` rule once matched a package directory on a case-insensitive
  filesystem; the module existed on disk, imported, and passed every test, and
  was never committed. A fresh clone, or the Pi, would have lacked it.
- **No credential file is tracked.** The television's token was committed to a
  public repository once.
- **No deployment value is in source.** This repository is public, and a
  private address or a home path in a tool's docstring is published the moment
  it is pushed. The check knows the shapes of such values, not the values, so
  it publishes nothing of its own.
- **Every test module is in `tests/`**, where `testpaths` collects it; one
  anywhere else looks like a test and guards nothing.
"""

import os
import pathlib
import re
import subprocess

import pytest

PROJECT = pathlib.Path(__file__).resolve().parents[1]

#: The trees whose absence from a fresh clone would matter. `tools/` is here
#: because the operator runs it by hand at the set, and it holds the only code
#: that presses power on the television.
SOURCE_TREES = ("src", "tests", "tools")

#: Shapes no source line may carry, comments included: a private-range IPv4
#: address, and a path under a named person's home directory. Documentation
#: names such a path with a placeholder (`/home/<user>`), which this does not
#: match.
_PRIVATE_SHAPES = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
    r"|/(?:Users|home)/[A-Za-z][\w.-]*"
)

#: The deployment's published paths. Public (the deploy docs name them), so not a
#: leak; still forbidden in code, because the same code runs on a dev machine
#: where they do not exist. Comments may name them.
_DEPLOYMENT_PATHS = re.compile(r"/srv/art|/opt/samsung-frame-art-loader")


def _tracked() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"],  # noqa: S607 -- git from PATH, as every guard here runs it
        cwd=PROJECT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    tracked = [name for name in listed.split("\0") if name]
    # An anchor rather than a count: the entry point is tracked, or the listing is
    # not this project's and every check below would be vacuous.
    assert "src/arrt_player/__main__.py" in tracked, "git ls-files did not list this project; every check here would be vacuous"
    return tracked


def _ignored(paths: list[pathlib.Path]) -> list[str]:
    """The subset of `paths` git would exclude, whatever the index holds (`--no-index`)."""
    result = subprocess.run(
        ["git", "check-ignore", "--stdin", "--no-index"],  # noqa: S607 -- git from PATH, as every guard here runs it
        cwd=PROJECT,
        input="\n".join(str(path) for path in paths),
        capture_output=True,
        text=True,
        check=False,
    )
    # Exit 0 = some paths ignored, 1 = none ignored. Anything else is a real error.
    assert result.returncode in (0, 1), f"git check-ignore failed: {result.stderr}"
    return [line for line in result.stdout.splitlines() if line]


@pytest.mark.parametrize("tree", SOURCE_TREES)
def test_every_tree_the_scans_name_exists(tree):
    assert (PROJECT / tree).is_dir(), f"{tree} is not a directory, so the scans below pass over nothing there"


def test_no_source_or_package_directory_is_gitignored():
    candidates = [
        path
        for tree in SOURCE_TREES
        for path in (PROJECT / tree).rglob("*")
        if "__pycache__" not in path.parts and (path.suffix == ".py" or path.is_dir())
    ]

    assert candidates, "expected source files; has the layout moved?"
    assert _ignored(candidates) == [], "these would never be committed"


def test_no_credential_file_is_tracked():
    offenders = [name for name in _tracked() if pathlib.PurePosixPath(name).name in {"token_file", ".env"}]

    assert offenders == [], f"credential files must never be tracked: {offenders}"


def test_no_source_file_carries_a_deployment_value():
    modules = sorted((PROJECT / "src").rglob("*.py")) + sorted((PROJECT / "tools").rglob("*.py"))
    assert modules, "no source to check; has the layout moved?"
    offenders = [
        f"{path.relative_to(PROJECT)}:{number}"
        for path in modules
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if _PRIVATE_SHAPES.search(line) or (not line.strip().startswith("#") and _DEPLOYMENT_PATHS.search(line))
    ]

    assert offenders == [], "a deployment value, which belongs in .env:\n" + "\n".join(offenders)


@pytest.mark.parametrize(
    ("line", "leaks"),
    [
        ('HOST = "10.1.2.3"', True),
        ('HOST = "192.168.0.20"', True),
        ('HOST = "172.20.0.1"', True),
        ("# copied from /Users/someone/thing", True),
        ('HOST = "172.32.0.1"', False),
        ('HOST = "192.0.2.10"', False),
        ('HOST = "110.1.2.3"', False),
        ("# documented as /home/<user>/art", False),
    ],
)
def test_the_shape_check_knows_a_leak_from_a_lookalike(line, leaks):
    assert bool(_PRIVATE_SHAPES.search(line)) is leaks


def _this_machines_values() -> dict[str, str]:
    """The deployment values this checkout's `.env` holds, and this user's home.

    Read with `dotenv_values`, the parser the Player loads `.env` through, so an
    `export` prefix or an inline comment means here what it means there.
    Coordinates and the television's address are what a public repository must
    not carry; `$HOME` stands in for every path under it.
    """
    from dotenv import dotenv_values

    values = {}
    dotenv = PROJECT / ".env"
    if dotenv.is_file():
        declared = dotenv_values(dotenv)
        for key in ("TV_ADDRESS", "LATITUDE", "LONGITUDE"):
            value = (declared.get(key) or "").strip()
            if len(value) >= 4:
                values[key] = value
    home = os.environ.get("HOME", "")
    if len(home) > len("/home/"):
        values["HOME"] = home
    return values


def test_no_tracked_file_carries_this_machines_deployment_values():
    """Every tracked file, against the values this checkout uses; it names the key that leaked, never the value."""
    values = _this_machines_values()
    if not values:
        pytest.skip("no .env deployment values and no $HOME here, so there is nothing of this machine's to look for")
    offenders = []
    for name in _tracked():
        try:
            text = (PROJECT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue  # binary, or deleted in the working tree
        offenders.extend(f"{name}: this machine's {key}" for key, value in values.items() if value in text)

    assert offenders == [], "a tracked file carries this machine's deployment values:\n" + "\n".join(offenders)


def test_every_test_module_is_in_tests():
    misplaced = [
        name
        for name in _tracked()
        if pathlib.PurePosixPath(name).name.startswith("test_") and name.endswith(".py") and not name.startswith("tests/")
    ]

    assert misplaced == [], f"test modules outside tests/, which pytest never collects: {misplaced}"
