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


# -- every tracked text file, every shape ----------------------------------

#: The shapes a household's network leaves behind besides a private IPv4 address,
#: each by the kind a report names (never the value). Every one is a deployment
#: value in a public repository: a tailnet address (CGNAT, 100.64.0.0/10), an
#: address on a home's IPv6 prefix (unique-local fc00::/7, link-local fe80::/10),
#: a name only this house's resolver answers (`.lan`, `.local`), and the account
#: and machine an operator logs in as (`user@host`, a host with no domain).
#:
#: The lookarounds are what keep a lookalike out. An IPv4 is not part of a longer
#: dotted number. A host name is not followed by another label, so
#: `settings.local.json` is a file. `user@host` needs a bare word, an IPv4 or a
#: `.lan`/`.local` name after the `@`: `you@example.org` is a contact address, and
#: an `owner/repo@ref` (a workflow's `uses:`) and an image's `@sha256` digest are
#: references, because the user part may not follow a `/` or a word character.
_NEW_SHAPES: dict[str, re.Pattern[str]] = {
    "a CGNAT (tailnet) address": re.compile(r"(?<![\d.])100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}(?![\d]|\.\d)"),
    "an IPv6 unique-local or link-local address": re.compile(
        r"(?<![\w:])(?:f[cd][0-9a-fA-F]{2}|fe[89abAB][0-9a-fA-F])(?::[0-9a-fA-F]{0,4}){2,7}(?![\w:])"
    ),
    "a .lan or .local host name": re.compile(r"\b[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9-]+)*\.(?:lan|local)(?![\w-]|\.\w)"),
    "a user@host login": re.compile(
        r"(?<![\w@./+:-])[A-Za-z_][\w.-]*@(?!sha256\b)"
        r"(?:\d{1,3}(?:\.\d{1,3}){3}"
        r"|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:lan|local)"
        r"|[A-Za-z][A-Za-z0-9-]*)(?![\w-]|\.\w)"
    ),
}
_SHAPES: dict[str, re.Pattern[str]] = {
    "a private address or a named home directory": _PRIVATE_SHAPES,
    **_NEW_SHAPES,
}

#: Not deployment values whatever the shape says: Python's `threading.local`, and
#: the plugin identifier prawduct's own settings use.
_NOT_A_VALUE = frozenset({"threading.local", "prawduct@prawduct"})

#: Documented examples: a value a file names on purpose, as a fixture a security
#: check is tested with, a placeholder an error message shows, or an input this
#: guard is itself tested with. **Per file and per exact value**, never one of
#: them everywhere: the planted `100.101.1.2` has to be reported in any file that
#: is not listed here. A file that stops needing an entry fails
#: `test_every_named_exception_is_still_needed`, so the table only shrinks.
_EXAMPLES: dict[str, frozenset[str]] = {
    "arrt/src/arrt/config.py": frozenset({"arrt.lan"}),
    "arrt/tests/unit/test_config.py": frozenset({"arrt.lan"}),
    "arrt/tests/integration/test_browser_surface.py": frozenset({"nas.lan"}),
    "arrt/tests/integration/test_host_guard.py": frozenset({"10.0.0.1", "10.1.2.3", "10.9.9.9", "fe80::1"}),
    "arrt/tests/unit/test_acquisition_urls.py": frozenset(
        {"10.0.0.1", "10.0.0.5", "172.16.0.1", "192.168.1.1", "fc00::1", "fd00::1", "fe80::1", "nas.local", "printer.local"}
    ),
    "arrt/tests/unit/test_run_citations.py": frozenset({"10.0.0.5", "192.168.1.1", "fd00::1", "nas.local"}),
    "arrt/tests/unit/test_phase_one_engine.py": frozenset({"10.0.0.5"}),
    "arrt/tests/unit/test_met_source.py": frozenset({"10.0.0.1"}),
    "arrt/tests/unit/test_smk_source.py": frozenset({"10.0.0.1"}),
    "arrt/tests/unit/test_yale_source.py": frozenset({"10.0.0.1"}),
    "arrt/tests/unit/test_dispatch_faults.py": frozenset({"/Users/someone"}),
    # The build plan that asked for this guard quotes the planted values it is accepted by.
    ".prawduct/artifacts/build-plan-audit-wave-1.md": frozenset(
        {"100.101.1.2", "fd12::1", "nas.lan", "pi@frame.local", "user@host", "frame.local"}
    ),
}


#: Files the scan does not read. Only this one: it holds, as test inputs, every shape
#: the guard knows and every example `_EXAMPLES` excuses in the files that carry them,
#: so scanning it would need its own table to name the others' values. A real value
#: pasted here would pass, which is the price, and the file is small and has one job.
_NOT_SCANNED = frozenset({"tests/preferences/test_deployment_values.py"})


def shapes_found(path: str, line: str) -> list[str]:
    """The kind of each deployment shape on a line of `path` that no documented example excuses.

    Kinds, not values: a report built from this cannot publish what it found.
    """
    if path in _NOT_SCANNED:
        return []
    excused = _EXAMPLES.get(path, frozenset())
    kinds = []
    for kind, pattern in _SHAPES.items():
        for found in pattern.finditer(line):
            value = found.group(0)
            if value not in excused and value not in _NOT_A_VALUE:
                kinds.append(kind)
    return kinds


def offences_in(files: dict[str, str]) -> list[str]:
    """`path:line: kind`, one per shape found in `{path: text}`."""
    return [
        f"{path}:{number}: {kind}"
        for path, text in sorted(files.items())
        for number, line in enumerate(text.splitlines(), start=1)
        for kind in shapes_found(path, line)
    ]


def _tracked_text_files() -> dict[str, str]:
    """Every tracked file that reads as UTF-8, by path: documents, `.prawduct/`, configuration, tests and code.

    The working tree only, never history: what is already published is the
    owner's to deal with, and a guard that read history would fail on it forever.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=_REPOSITORY_ROOT, capture_output=True, check=True, text=True
    ).stdout.split("\0")
    files = {}
    for name in filter(None, tracked):
        try:
            files[name] = (_REPOSITORY_ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue  # binary, or deleted in the working tree
    return files


def test_the_scan_reads_documents_and_the_prawduct_tree_as_well_as_code():
    """The vacuity check, and the scope F19 found missing: a scan of source alone passes over every document."""
    files = _tracked_text_files()

    assert len(files) > 100, "the file listing returned almost nothing; the scan would be vacuous"
    assert any(name.endswith(".md") and not name.startswith(".prawduct/") for name in files), "no tracked document"
    assert any(name.startswith(".prawduct/artifacts/") for name in files), "no .prawduct artifact"
    assert any(name.startswith(".github/workflows/") for name in files), "no workflow"
    assert any(name.endswith(".py") for name in files), "no code"
    assert _NOT_SCANNED <= set(files), "a file named in _NOT_SCANNED is not tracked; remove it"


def test_no_tracked_text_file_carries_a_deployment_shape():
    """Every shape, in every tracked text file, with the documented examples excused by name.

    Reports the file, the line and the kind, never the value.
    """
    offences = offences_in(_tracked_text_files())

    assert not offences, "a tracked file carries a deployment value (kind only; the value is not printed):\n" + "\n".join(
        offences
    )


def test_every_named_exception_is_still_needed():
    """An example nobody still carries is a hole for the next real value to hide in, so it goes."""
    files = _tracked_text_files()
    stale = []
    for path, values in sorted(_EXAMPLES.items()):
        assert path in files, f"{path} is named in _EXAMPLES and is not tracked"
        carried = {
            found.group(0)
            for pattern in _SHAPES.values()
            for line in files[path].splitlines()
            for found in pattern.finditer(line)
        }
        stale += [f"{path}: {value}" for value in sorted(values - carried)]
    assert not stale, "examples no longer carried; remove them from _EXAMPLES:\n" + "\n".join(stale)


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("tailnet peer at 100.101.1.2 answers", "a CGNAT (tailnet) address"),
        ("the lower edge 100.64.0.1", "a CGNAT (tailnet) address"),
        ("the upper edge 100.127.255.254", "a CGNAT (tailnet) address"),
        ("LISTEN=fd12::1", "an IPv6 unique-local or link-local address"),
        ("[fd12:3456:789a::1]:8770", "an IPv6 unique-local or link-local address"),
        ("link-local fe80::1 on eth0", "an IPv6 unique-local or link-local address"),
        ("curl http://nas.lan:8770/healthz", "a .lan or .local host name"),
        ("open pi@frame.local, then", "a .lan or .local host name"),
        ("ssh pi@nas", "a user@host login"),
        ("scp x pi@10.4.5.6:/srv", "a user@host login"),
    ],
)
def test_each_new_shape_is_reported_in_a_document(line, kind):
    """One planted value per shape the guard learned, planted in prose where none was scanned before."""
    assert any(kind in offence for offence in offences_in({"docs/notes.md": line}))
    assert offences_in({".prawduct/artifacts/spec.md": line}), "a .prawduct artifact is not scanned"


@pytest.mark.parametrize(
    "line",
    [
        "100.63.255.255 is just below CGNAT",
        "100.128.0.1 is just above it",
        "1100.101.1.2 is not an address",
        "100.101.1.2.3 is a version",
        "fe7f::1 is below link-local",
        "fe80 is a prefix with no address",
        "2001:db8::1 is the documentation range",
        "see .claude/settings.local.json",
        "the .local suffix is refused",
        "contact you@example.org",
        "uses: actions/checkout@v4",
        "FROM debian:bookworm-slim@sha256:0123abcd",
        "plugin prawduct@prawduct",
        "threading.local()",
        "git+ssh://git@github.com/owner/repo",
        "@pytest.fixture",
        "host localhost and example.com",
    ],
)
def test_the_new_shapes_know_a_lookalike(line):
    assert offences_in({"docs/notes.md": line}) == []


def test_an_excused_example_is_excused_only_in_its_own_file():
    line = "the host is arrt.lan here"

    assert offences_in({"arrt/src/arrt/config.py": line}) == []
    assert offences_in({"arrt/src/arrt/elsewhere.py": line}), "an excuse for one file held in another"
    assert offences_in({"arrt/src/arrt/config.py": "the host is other.lan here"}), "an excuse for one value held for another"


def test_the_report_names_the_file_and_line_and_never_the_value():
    report = offences_in({"docs/notes.md": "first\nreach it at pi@frame.local"})

    assert report == ["docs/notes.md:2: a .lan or .local host name", "docs/notes.md:2: a user@host login"]
