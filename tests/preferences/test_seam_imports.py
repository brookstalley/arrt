"""Programming reaches the Library only through its facade, and the Library never reaches Programming.

`architecture.md` § Direction, the Library/Programming seam, rule 1. The reason is
the one the plane-isolation guard gives for its own rule: **a crossing looks
exactly like success.** Arrt runs both halves in one process, so a
Programming module that imports a catalogue service works perfectly, in
development and in every test, and the cost arrives only on the day Programming
is deployed on its own and has to be rewritten. A green suite is what the
violation looks like, so the guard is static.

**Imports are followed transitively through this repository's files**, including
the shared modules both sides may use. The crossing this guard found on its first
run was one hop long: a museum client imported the configuration module for a
byte cap, and the configuration module imported the manifest. Neither import
looked like a crossing on its own line.

**The facade is where the walk stops, and only the facade.** Programming may
import `arrt.library.facade`, and what the facade imports is the Library's own
business. The Library's package `__init__` is walked rather than exempted, because
importing the facade runs it: an import added there would reach Programming's
process without appearing in any Programming file.

**What this cannot see**, stated so nobody reads more into a green run: which
names a module uses from the shared kernel. `persistence.records` holds both
sides' record types until rule 3 gives Programming its own store, so a
Programming module could use `Artwork` from there and pass. Programming's store
protocol, which hands it only its own tables, is what stands in the way of that
until then.
"""

import pathlib
from collections.abc import Iterable

import pytest
from import_graph import imported_names, package_of, resolve

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SOURCE_ROOT = REPOSITORY_ROOT / "arrt" / "src"

LIBRARY = "arrt.library"
PROGRAMMING = "arrt.programming"
FACADE = "arrt.library.facade"


def test_both_sides_have_modules_to_check():
    """The guard's vacuity check: a walk over nothing passes."""
    assert _modules_under(SOURCE_ROOT, PROGRAMMING), f"no {PROGRAMMING} modules under {SOURCE_ROOT}"
    assert _modules_under(SOURCE_ROOT, LIBRARY), f"no {LIBRARY} modules under {SOURCE_ROOT}"
    assert _file_of(FACADE, SOURCE_ROOT) is not None, f"{FACADE} does not exist, so Programming has no way in"


def test_programming_reaches_the_facade_through_the_walk():
    """The walk has to see the one crossing that is allowed, or it proves nothing about the others.

    A resolver that failed to follow `from arrt.library.facade import …` would
    report Programming clean for the wrong reason, exactly as it would if the
    subject had moved.
    """
    reached = _reach(_modules_under(SOURCE_ROOT, PROGRAMMING), SOURCE_ROOT, stop_at={FACADE})

    assert FACADE in reached


def test_programming_imports_no_library_module_but_the_facade():
    offences = _programming_offences(SOURCE_ROOT)

    assert offences == [], "\n".join(offences)


def test_the_library_imports_no_programming_module():
    offences = _library_offences(SOURCE_ROOT)

    assert offences == [], "\n".join(offences)


class TestTheGuardCanFail:
    """Planted crossings, one per way a crossing actually arrives."""

    def test_it_catches_programming_importing_a_library_service(self, tmp_path: pathlib.Path):
        root = _tree(tmp_path, {"programming/walls.py": "from arrt.library.catalogue import Service\n"})

        assert _crossings(_programming_offences(root)) == ["arrt.library.catalogue"]

    def test_it_catches_programming_reaching_the_library_one_helper_away(self, tmp_path: pathlib.Path):
        root = _tree(
            tmp_path,
            {
                "shared.py": "from arrt.library.catalogue import Service\n",
                "programming/walls.py": "from arrt import shared\n",
            },
        )

        offences = _programming_offences(root)

        assert _crossings(offences) == ["arrt.library.catalogue"]
        assert "shared.py" in offences[0], "the offence did not name the file that actually crosses"

    def test_it_does_not_object_to_what_the_facade_imports(self, tmp_path: pathlib.Path):
        root = _tree(tmp_path, {"programming/walls.py": "from arrt.library.facade import playable\n"})

        assert _programming_offences(root) == []

    def test_it_catches_an_import_riding_in_on_the_library_package(self, tmp_path: pathlib.Path):
        """Importing the facade runs the package `__init__`, so that file is walked too."""
        root = _tree(
            tmp_path,
            {
                "library/__init__.py": "from arrt.library import catalogue\n",
                "programming/walls.py": "from arrt.library.facade import playable\n",
            },
        )

        assert _crossings(_programming_offences(root)) == ["arrt.library.catalogue"]

    def test_it_catches_a_relative_crossing(self, tmp_path: pathlib.Path):
        root = _tree(tmp_path, {"programming/walls.py": "from ..library import catalogue\n"})

        assert _crossings(_programming_offences(root)) == ["arrt.library.catalogue"]

    def test_it_catches_the_library_importing_programming(self, tmp_path: pathlib.Path):
        root = _tree(tmp_path, {"library/catalogue.py": "from arrt.programming.display import DisplayService\n"})

        assert _crossings(_library_offences(root)) == ["arrt.programming.display"]

    def test_it_catches_the_library_reaching_programming_through_a_shared_module(self, tmp_path: pathlib.Path):
        """The shape of the crossing this guard found on its first run."""
        root = _tree(
            tmp_path,
            {
                "config.py": "from arrt.programming.manifest import TEMPLATE\n",
                "library/artic.py": "from arrt.config import CAP\n",
            },
        )

        assert _crossings(_library_offences(root)) == ["arrt.programming.manifest"]

    def test_the_facade_itself_may_not_reach_programming(self, tmp_path: pathlib.Path):
        """The walk stops at the facade for Programming, not for the Library's own check."""
        root = _tree(tmp_path, {"library/facade.py": "from arrt.programming import display\n"})

        assert _crossings(_library_offences(root)) == ["arrt.programming.display"]


# -- the audit ------------------------------------------------------------


def _programming_offences(root: pathlib.Path) -> list[str]:
    return _offences(
        _modules_under(root, PROGRAMMING),
        root,
        forbidden=lambda name: _within(name, LIBRARY) and name != LIBRARY,
        stop_at={FACADE},
        subject="a Library module other than the facade",
    )


def _library_offences(root: pathlib.Path) -> list[str]:
    return _offences(
        _modules_under(root, LIBRARY),
        root,
        forbidden=lambda name: _within(name, PROGRAMMING),
        stop_at=set(),
        subject="a Programming module",
    )


def _offences(entry, root, *, forbidden, stop_at, subject) -> list[str]:
    """One line per module that crosses, naming the chain of files that gets there.

    Breadth-first over module names, so a cycle between two modules terminates.
    A module is judged by the name it is reached under, which is its file's
    dotted path: that is what makes "the facade" one module and not a prefix.
    """
    crossings: dict[str, set[str]] = {}
    seen: set[str] = set()
    queue: list[tuple[str, tuple[str, ...]]] = [(name, (name,)) for name in entry]
    while queue:
        name, chain = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        path = _file_of(name, root)
        if path is None:
            continue
        for reached in _local_imports(path, root):
            if reached in stop_at:
                continue
            if forbidden(reached):
                route = " -> ".join(_display(module, root) for module in chain)
                crossings.setdefault(route, set()).add(reached)
                continue
            if reached not in seen:
                queue.append((reached, (*chain, reached)))
    # One line per module actually named. `from a.b.c import x` also loads `a.b`,
    # and reporting the package beside its module says the same crossing twice.
    return sorted(
        f"{route} imports {name}, which is {subject}"
        for route, names in crossings.items()
        for name in names
        if not any(other.startswith(f"{name}.") for other in names)
    )


def _reach(entry: Iterable[str], root: pathlib.Path, *, stop_at: set[str]) -> set[str]:
    """Every module name the walk arrives at, the stop points included."""
    reached: set[str] = set()
    queue = list(entry)
    while queue:
        name = queue.pop(0)
        if name in reached:
            continue
        reached.add(name)
        path = _file_of(name, root)
        if path is None or name in stop_at:
            continue
        queue.extend(_local_imports(path, root))
    return reached


def _local_imports(path: pathlib.Path, root: pathlib.Path) -> set[str]:
    """The repo-local modules this file loads, parent packages included.

    `from a.b.c import x` runs `a/__init__.py` and `a/b/__init__.py` before
    `a/b/c.py`, so each is reported. A name that resolves to no file here is
    third-party and not followed.
    """
    reached: set[str] = set()
    for name in imported_names(path):
        parts = name.split(".")
        for end in range(1, len(parts) + 1):
            candidate = ".".join(parts[:end])
            if resolve(candidate, (root,)) is not None:
                reached.add(candidate)
    return reached


def _modules_under(root: pathlib.Path, package: str) -> list[str]:
    directory = root.joinpath(*package.split("."))
    return sorted(_module_name(path) for path in directory.rglob("*.py"))


def _module_name(path: pathlib.Path) -> str:
    parts = package_of(path)
    return ".".join(parts[:-1]) if parts[-1] == "__init__" else ".".join(parts)


def _file_of(name: str, root: pathlib.Path) -> pathlib.Path | None:
    return resolve(name, (root,))


def _within(name: str, package: str) -> bool:
    return name == package or name.startswith(f"{package}.")


def _display(name: str, root: pathlib.Path) -> str:
    path = _file_of(name, root)
    if path is None:
        return name
    try:
        return str(path.relative_to(REPOSITORY_ROOT))
    except ValueError:
        return str(path.relative_to(root))


def _crossings(offences: list[str]) -> list[str]:
    """The forbidden module each offence names, for assertions that do not pin the sentence."""
    return sorted({offence.split(" imports ", 1)[1].split(",", 1)[0] for offence in offences})


def _tree(tmp_path: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    """A miniature `arrt` package: every directory a package, every named file planted.

    The facade and both package roots always exist, so each case plants only the
    crossing it is about.
    """
    package = tmp_path / "arrt"
    defaults = {
        "__init__.py": "",
        "library/__init__.py": "",
        "library/facade.py": "from arrt.library import catalogue\n",
        "library/catalogue.py": "",
        "programming/__init__.py": "",
        "programming/display.py": "",
        "programming/manifest.py": "",
    }
    for relative, source in {**defaults, **files}.items():
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def _guard_is_pointed_at_something_real():
    """Fails the whole module if the packages move, rather than passing over nothing."""
    assert (SOURCE_ROOT / "arrt").is_dir(), f"{SOURCE_ROOT} has no arrt package; this guard has lost its subject"
