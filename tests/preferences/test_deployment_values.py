"""No tracked file carries a deployment value: an address, a home path, or this machine's own.

`project-preferences.md` forbids hardcoded deployment values, and this
repository is public, so a leaked address or coordinate is published the moment
it is pushed. These checks span every plane, which is why they live in the
root's governance suite rather than in either plane's own.
"""

import os
import pathlib
import re
import subprocess

import pytest
from repository import projects

#: Shapes no source line may carry, comments included: a private-range IPv4
#: address, and a path under a named person's home directory. These are what a
#: deployment value looks like when it leaks, whatever the deployment is, so the
#: check needs no knowledge of this repository's own machines and runs everywhere,
#: CI included. Documentation names such a path with a placeholder
#: (`/home/<user>`), which the pattern does not match.
_PRIVATE_SHAPES = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
    r"|/(?:Users|home)/[A-Za-z][\w.-]*"
)

#: The deployment's published paths. They are public (the deploy docs name
#: them), so they are not a leak; they are still forbidden in code, because the
#: same code runs on a dev Mac where they do not exist. Comments may name them.
_DEPLOYMENT_PATHS = re.compile(r"/srv/art|/opt/samsung-frame-art-loader")

_REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _source_modules():
    """Every module the norm covers, with a canary per plane.

    Anchored to this file rather than the working directory: a glob rooted at "."
    matches nothing when pytest runs from elsewhere, and a guard whose value is
    that it cannot be quietly satisfied must not have a green path through
    checking zero files. **`tools` as well as `src`**, because a tool's docstring
    is what an operator copies, which makes it where a real machine path is most
    tempting. **One canary per project**, because `rglob` over a missing directory
    is silent and a moved `src/` would otherwise drop out of the check unnoticed.
    """
    repository_root = _REPOSITORY_ROOT
    modules = sorted(repository_root.glob("*.py"))
    for project in projects():
        found = sorted((repository_root / project / "src").rglob("*.py"))
        assert found, f"expected source under {project}/src; has the layout moved?"
        modules.extend(found)
        modules.extend(sorted((repository_root / project / "tools").rglob("*.py")))
    return modules


def test_no_source_file_carries_a_deployment_value():
    """The norm, asserted mechanically, without publishing the deployment.

    This guard used to list the deployment's own address, home path and
    coordinates as literals, which put them in a public repository; it now
    names only their shapes, and the sibling below checks this machine's real
    values without writing them down.
    """
    offenders = []
    for path in _source_modules():
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            stripped = line.strip()
            where = f"{path.relative_to(_REPOSITORY_ROOT)}:{number}"
            if _PRIVATE_SHAPES.search(line):
                offenders.append(f"{where}: a private address or a named home directory")
            if not stripped.startswith("#") and _DEPLOYMENT_PATHS.search(line):
                offenders.append(f"{where}: {stripped}")
    assert not offenders, "deployment values must live in .env, not source:\n" + "\n".join(offenders)


@pytest.mark.parametrize(
    ("line", "leaks"),
    [
        ('HOST = "10.1.2.3"', True),
        ('HOST = "192.168.0.20"', True),
        ('HOST = "172.20.0.1"', True),
        ("# copied from /Users/someone/thing", True),
        ('ROOT = "/home/zz-no-such-user/art"', True),
        ('HOST = "172.32.0.1"', False),  # just outside 172.16/12
        ('HOST = "192.0.2.10"', False),  # RFC 5737 documentation range
        ('HOST = "110.1.2.3"', False),  # not 10/8: the address starts 110
        ('LISTEN = "0.0.0.0"', False),
        ("# documented as /home/<user>/art", False),
    ],
)
def test_the_shape_check_knows_a_leak_from_a_lookalike(line, leaks):
    """The pattern behind the source guard, held to cases either side of each edge."""
    assert bool(_PRIVATE_SHAPES.search(line)) is leaks


def _this_machines_values():
    """The deployment values this checkout's `.env` holds, and this user's home.

    Read with `dotenv_values`, the parser both planes load `.env` through, so
    an `export` prefix or an inline comment means here what it means there, and
    straight from the file rather than through either plane's settings, so nothing depends on
    what the harness has cleared. Coordinates and the address are what a published
    repository must not carry; `$HOME` stands in for every path under it, a dev
    `ART_ROOT` included, and is compared even where there is no `.env`. An
    `ART_ROOT` outside `$HOME` is the deployment's published path (`/srv/art`),
    which `_DEPLOYMENT_PATHS` holds to code alone.
    """
    from dotenv import dotenv_values

    values = {}
    dotenv = _REPOSITORY_ROOT / ".env"
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
    """Every tracked file, not only source, against the values this checkout uses.

    The shape check above cannot know whether a public-looking number is someone's
    coordinates; this one can, because it reads them from the `.env` that holds
    them. It reports which key leaked and where, never the value, so its own
    failure message cannot publish what it found. Where there is no `.env` (CI)
    there is nothing to compare against, and it says so rather than passing.
    """

    values = _this_machines_values()
    if not values:
        pytest.skip("no .env deployment values and no $HOME here, so there is nothing of this machine's to look for")
    repository_root = _REPOSITORY_ROOT
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repository_root, capture_output=True, check=True, text=True
    ).stdout.split("\0")
    assert len(tracked) > 100, "git ls-files returned almost nothing; the scan would be vacuous"
    offenders = []
    for name in filter(None, tracked):
        path = repository_root / name
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue  # binary, or deleted in the working tree
        offenders.extend(f"{name}: this machine's {key}" for key, value in values.items() if value in text)
    assert not offenders, "a tracked file carries this machine's deployment values:\n" + "\n".join(offenders)
