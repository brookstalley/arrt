"""The image's test stage carries every file the server's tests read: held on every pull request.

`arrt/Dockerfile`'s `test` stage runs the server's suite inside the image the NAS runs, laid
out as the image lays it out: `arrt/` is `/app`, and only what a `COPY` brings in exists. On
the pool the same tests run in the whole checkout, so a test that reads a file the image does
not carry passes there and fails only in the image. That is the one class of defect the
image's build caught that nothing else did: four tests reading `.env.example`
from the repository root, and a test reading
`docs/source-plugins.md`. Each was found after the fact and fixed by a `COPY` added by hand.

The image is built on a pull request into `main` only (`image.yml`, by the
owner's ruling of 2026-11-20), so this file holds that guarantee before `develop` instead,
by reading both sides as data:

- **What the image carries:** every `COPY` of the `test` stage and the stages it is built
  on, each mapped back to the repository path it holds (`/app/<p>` is `arrt/<p>`, `/<p>` is
  `<p>`). A `COPY` that does not land where the tests look (its destination is not its
  source's place in the repository) is refused by name, as is any shape the reader does not
  parse (`ADD`, a continued or exec-form `COPY`, a bind mount).
- **What the tests read:** every path a module under `arrt/tests/` (less `arrt/tests/browser`,
  which the stage does not collect) or `arrt/tools/` (which those tests import) builds from
  its own location: `Path(__file__)` with `.parent`, `.parents[k]`, `/ "literal"` and
  `.joinpath(...)`, through names bound to such a path in the same module, worked out to a
  repository path. A module is scanned whether or not its tests are deselected in the image,
  because collection imports it and a module-level read runs then.
- A path that resolves must lie in what the image carries. A climb that does not resolve
  (`.parents` walked as a whole, a part that is not a literal, a directory read past) must be
  in `DECLARED`, saying what it reads; each path it names must be carried, and an entry that
  matches nothing is stale.

**What it cannot see**, stated so a green run is not read as more: a path built from a string
(`Path("../all.json")`, `"..".join`), from `os.path`, from another module's `__file__` (an
installed package's own files, which the image carries as the package), or from the working
directory (the pool runs from the repository root and the image from `/app`), except a
relative literal handed to `Path` or `open` that names a file in the repository, which is
refused; what a subprocess or a tool outside `arrt/` reads; and what `arrt/.dockerignore`
drops inside a copied directory. Those still meet the image at a pull request into `main`.
"""

from __future__ import annotations

import ast
import pathlib
import posixpath
import re
from collections.abc import Iterator
from functools import cache

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
DOCKERFILE = REPO / "arrt" / "Dockerfile"
#: Where the image puts `arrt/`, the build's context.
APP = "/app"
#: The stage the suite runs in.
TEST_STAGE = "test"
#: What is scanned, and what the test stage does not collect (`--ignore=tests/browser`).
SCANNED = ("arrt/tests", "arrt/tools")
NOT_COLLECTED = ("arrt/tests/browser",)

#: A part of a path that is not a literal.
ANY = "*"
#: A `..` inside a literal: a climb by string, never worked out.
UP = ".."


class Climb:
    """A climb that walks every ancestor (`.parents` with no index): it reads wherever it finds."""

    def __repr__(self) -> str:
        return "<every ancestor>"


EVERY_ANCESTOR = Climb()

#: Each climb the scan cannot work out to one path, by module and by the expression as
#: `ast.unparse` writes it, with the repository paths it reads and why it is written so.
DECLARED: dict[tuple[str, str], tuple[frozenset[str], str]] = {
    ("arrt/tests/unit/test_mat_corpus.py", "Path(__file__).resolve().parents"): (
        frozenset({"all.json"}),
        "walks up for the 2024 index so that moving the file does not silently read nothing",
    ),
    ("arrt/tools/mutation_sweep.py", "ROOT / mutation.file"): (
        frozenset(),
        "the file a mutation names, in the project the sweep is pointed at; run by hand, never by a test",
    ),
}


# -- what the image carries ------------------------------------------------------------------


def _stages(dockerfile: str) -> Iterator[tuple[str, str, list[str]]]:
    """(name, the stage it is built FROM, its lines) for each stage, in order."""
    name, parent, lines = "", "", []
    for line in dockerfile.splitlines():
        match = re.match(r"FROM\s+(\S+)(?:\s+AS\s+(\S+))?\s*$", line)
        if match:
            if name or lines:
                yield name, parent, lines
            parent, name, lines = match.group(1), match.group(2) or "", []
            continue
        lines.append(line)
    yield name, parent, lines


def carried_paths(dockerfile: str, stage: str = TEST_STAGE) -> set[str]:
    """Every repository path the stage holds, where a test looks for it, read from its COPYs."""
    stages = {name: (parent, lines) for name, parent, lines in _stages(dockerfile)}
    assert stage in stages, f"arrt/Dockerfile has no stage {stage!r}"
    chain = []
    at: str | None = stage
    while at in stages:
        chain.append(at)
        at = stages[at][0]
    carried: set[str] = set()
    workdir = "/"
    for name in reversed(chain):
        for raw in stages[name][1]:
            line = raw.strip()
            # Shapes this reader does not parse are refused by name rather than skipped, so a
            # Dockerfile that grows one cannot carry, or drop, a file past the check.
            assert not line.startswith("ADD "), f"arrt/Dockerfile uses ADD, which this check does not read: {line}"
            assert not (line.startswith("COPY ") and line.endswith("\\")), f"a COPY continues onto the next line: {line}"
            assert "type=bind" not in line, f"a RUN binds a source this check does not read: {line}"
            assert not (line.startswith("COPY ") and raw != line), f"an indented COPY this check does not read: {line}"
            assert not line.startswith("COPY ["), f"an exec-form COPY this check does not read: {line}"
            if line.startswith("WORKDIR "):
                workdir = posixpath.join(workdir, line.split(None, 1)[1])
            if not line.startswith("COPY "):
                continue
            words = line.split()[1:]
            source = next((w.split("=", 1)[1] for w in words if w.startswith("--from=")), None)
            paths = [w for w in words if not w.startswith("--")]
            sources, dest = paths[:-1], paths[-1]
            if source is not None and source != "repo":
                continue  # another stage or image: a binary, never a repository file
            for path in sources:
                held = posixpath.normpath(posixpath.join(workdir, dest))
                if dest.endswith("/") or len(sources) > 1:
                    held = posixpath.join(held, posixpath.basename(path.rstrip("/")))
                repository = "" if source == "repo" else "arrt/"
                where = f"{repository}{path}".rstrip("/")
                if held.startswith(f"{APP}/"):
                    lands = "arrt/" + held.removeprefix(f"{APP}/")
                else:
                    lands = held.removeprefix("/")
                assert lands == where, (
                    f"`{line}` puts {where} at {held}, which is {lands} where the tests look: "
                    f"the image's layout must mirror the repository's (`{APP}` is `arrt/`, `/` its root)"
                )
                carried.add(where)
    return carried


def is_carried(parts: tuple[str, ...], carried: set[str]) -> bool:
    """Whether the path, worked out up to its first part that is not a literal, lies in what is carried.

    The repository's root and `arrt/` themselves exist in the image (as `/` and `/app`); a
    directory the image holds only part of is not carried, and must be declared.
    """
    if UP in parts:
        return False
    known = parts[: parts.index(ANY)] if ANY in parts else parts
    if parts in ((), ("arrt",)):
        return True
    if ANY in parts and known in ((), ("arrt",)):
        return False
    path = "/".join(known)
    return any(path == c or path.startswith(f"{c}/") for c in carried)


# -- what the tests read ---------------------------------------------------------------------


def _is_path_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == "Path") or (
        isinstance(func, ast.Attribute) and func.attr == "Path" and isinstance(func.value, ast.Name)
    )


class _Paths:
    """Works out the repository path each expression of one module builds from `__file__`."""

    def __init__(self, module: str, tree: ast.Module):
        self.file = tuple(module.split("/"))
        self.names: dict[str, object] = {}
        self.memo: dict[int, object] = {}
        for node in ast.walk(tree):
            target = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target = node.targets[0].id
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                target = node.target.id
            if target is None:
                continue
            value = self.of(node.value)
            if value is None:
                continue
            # A name bound twice to different paths is not worked out: the scan stops at it.
            self.names[target] = value if self.names.get(target, value) == value else EVERY_ANCESTOR

    def of(self, node: ast.AST) -> object:
        """A tuple of repository parts, `EVERY_ANCESTOR`, or None when the expression is no path from `__file__`."""
        key = id(node)
        if key not in self.memo:
            self.memo[key] = self._of(node)
        return self.memo[key]

    def _of(self, node: ast.AST) -> object:
        if isinstance(node, ast.Call) and _is_path_call(node):
            first = node.args[0] if len(node.args) == 1 else None
            return self.file if isinstance(first, ast.Name) and first.id == "__file__" else None
        if isinstance(node, ast.Name):
            return self.names.get(node.id)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            base = self.of(node.func.value)
            if not isinstance(base, tuple):
                return base if base is EVERY_ANCESTOR and node.func.attr in ("resolve", "absolute") else None
            if node.func.attr in ("resolve", "absolute"):
                return base
            if node.func.attr == "joinpath":
                return base + tuple(part for arg in node.args for part in _literal_parts(arg))
            return None
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            base = self.of(node.value)
            return base[:-1] if isinstance(base, tuple) else None
        if isinstance(node, ast.Attribute) and node.attr == "parents":
            return EVERY_ANCESTOR if isinstance(self.of(node.value), tuple) else None
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "parents":
            base = self.of(node.value.value)
            index = node.slice
            if isinstance(base, tuple) and isinstance(index, ast.Constant) and isinstance(index.value, int):
                return base[: -(index.value + 1)]
            return EVERY_ANCESTOR if isinstance(base, tuple) else None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            base = self.of(node.left)
            return base + _literal_parts(node.right) if isinstance(base, tuple) else None
        return None


def _literal_parts(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        parts = []
        for part in node.value.split("/"):
            if part == "..":
                parts.append(UP)  # a string climb: not worked out, so declared
            elif part not in ("", "."):
                parts.append(part)
        return tuple(parts)
    return (ANY,)


@cache
def reads(module: str, source: str) -> list[tuple[object, str]]:
    """(the path, the expression) for every path the module builds from `__file__`, outermost only.

    Outermost: `GUIDE = Path(__file__).parents[3] / "docs" / "x.md"` is one read, of
    `docs/x.md`, not three. A cwd-relative literal naming a repository file is returned with
    the path `("<cwd>", literal)`.
    """
    tree = ast.parse(source)
    paths = _Paths(module, tree)
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    found: list[tuple[object, str]] = []
    for node in ast.walk(tree):
        # A bare name is recorded where it is bound, not at each use.
        if not isinstance(node, ast.expr) or isinstance(node, ast.Name):
            continue
        value = paths.of(node)
        if value is None:
            continue
        parent = parents.get(id(node))
        if isinstance(parent, ast.expr) and paths.of(parent) is not None:
            continue
        found.append((value, ast.unparse(node)))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if _is_path_call(node) or (isinstance(node.func, ast.Name) and node.func.id == "open"):
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and not first.value.startswith("/"):
                literal = first.value
                if literal and ((REPO / literal).exists() or (REPO / "arrt" / literal).exists()):
                    found.append((("<cwd>", literal), ast.unparse(node)))
    return found


def _modules() -> Iterator[tuple[str, str]]:
    for root in SCANNED:
        for path in sorted((REPO / root).rglob("*.py")):
            module = path.relative_to(REPO).as_posix()
            if any(module.startswith(f"{skip}/") for skip in NOT_COLLECTED):
                continue
            yield module, path.read_text(encoding="utf-8")


def problems(modules: list[tuple[str, str]], carried: set[str], declared=DECLARED) -> list[str]:
    """Every read the image would not satisfy, and every declaration that is wrong or stale, by name."""
    found: list[str] = []
    used: set[tuple[str, str]] = set()
    for module, source in modules:
        for value, expression in reads(module, source):
            if isinstance(value, tuple) and value[:1] == ("<cwd>",):
                if (module, expression) not in declared:
                    found.append(
                        f"{module}: `{expression}` reads {value[1]!r} from the working directory, which is the "
                        f"repository's root on the pool and {APP} in the image: build it from `__file__`"
                    )
                    continue
            elif isinstance(value, tuple) and is_carried(value, carried):
                continue
            elif isinstance(value, tuple) and ANY not in value and UP not in value and (module, expression) not in declared:
                found.append(
                    f"{module}: `{expression}` reads {'/'.join(value)}, which arrt/Dockerfile's test stage does not "
                    "carry: add a `COPY --from=repo` for it there (the image's layout mirrors the repository's)"
                )
                continue
            if (module, expression) not in declared:
                found.append(
                    f"{module}: `{expression}` climbs to {value!r}, which this check cannot work out to one "
                    "path: declare what it reads in DECLARED, with why it is written so"
                )
                continue
            used.add((module, expression))
            needed, _ = declared[(module, expression)]
            for path in sorted(needed):
                if not is_carried(tuple(path.split("/")), carried):
                    found.append(
                        f"{module}: `{expression}` is declared to read {path}, which arrt/Dockerfile's test stage does "
                        "not carry"
                    )
    for stale in sorted(set(declared) - used):
        found.append(f"DECLARED names {stale}, which no scanned module builds any more: remove it")
    return found


@cache
def _real_modules() -> list[tuple[str, str]]:
    modules = list(_modules())
    assert len(modules) > 100, f"only {len(modules)} modules scanned under {SCANNED}"
    return modules


def _dockerfile() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def test_every_file_the_servers_tests_read_is_in_the_images_test_stage():
    carried = carried_paths(_dockerfile())
    found = problems(_real_modules(), carried)
    assert not found, "\n".join(found)
    # The reader saw the stage: without its COPYs every read above would have been refused.
    assert {"arrt/src", "arrt/tests", "arrt/tools", "contract"} <= carried, sorted(carried)


def test_the_scan_finds_the_reads_that_climb_out_of_arrt():
    """The reads the image's COPYs exist for, found by the scan: if it stopped finding them it would pass on nothing."""
    climbs = {
        (module, "/".join(value))
        for module, source in _real_modules()
        for value, _ in reads(module, source)
        if isinstance(value, tuple) and value[:1] not in (("arrt",), ("<cwd>",)) and value
    }
    assert {
        ("arrt/tools/ux_walk.py", ".env.example"),
        ("arrt/tests/unit/test_source_plugins.py", "docs/source-plugins.md"),
        ("arrt/tests/unit/test_fields.py", "all.json"),
        ("arrt/tests/integration/test_seed_corpus.py", "all.json"),
    } <= climbs, sorted(climbs)


#: Each repository-root file the test stage copies, with the line that copies it.
_ROOT_COPIES = {
    ".env.example": "COPY --from=repo .env.example /.env.example",
    "docs/source-plugins.md": "COPY --from=repo docs/source-plugins.md /docs/source-plugins.md",
    "all.json": "COPY --from=repo all.json /all.json",
}


@pytest.mark.parametrize("path", sorted(_ROOT_COPIES))
def test_a_test_stage_without_a_root_file_the_tests_read_is_refused_naming_the_reader(path):
    """The real cases: each COPY that a test needed, removed from the real Dockerfile, and the real tests scanned."""
    dockerfile = _dockerfile()
    assert _ROOT_COPIES[path] in dockerfile.splitlines(), f"arrt/Dockerfile no longer has `{_ROOT_COPIES[path]}`"
    without = "\n".join(line for line in dockerfile.splitlines() if line != _ROOT_COPIES[path])
    found = problems(_real_modules(), carried_paths(without))
    assert any(path in problem for problem in found), found
    assert all(path in problem for problem in found), found


def test_a_read_of_a_file_the_image_does_not_carry_is_named():
    source = 'import pathlib\nREADME = pathlib.Path(__file__).resolve().parents[3] / "README.md"\n'
    found = problems([("arrt/tests/unit/test_x.py", source)], carried_paths(_dockerfile()), declared={})
    assert found == [
        "arrt/tests/unit/test_x.py: `pathlib.Path(__file__).resolve().parents[3] / 'README.md'` reads README.md, "
        "which arrt/Dockerfile's test stage does not carry: add a `COPY --from=repo` for it there (the image's layout "
        "mirrors the repository's)"
    ]


@pytest.mark.parametrize(
    "source,reads_",
    [
        ('from pathlib import Path\nX = Path(__file__).parent.parent.parent.parent / "all.json"\n', "all.json"),
        ('from pathlib import Path\nX = Path(__file__).resolve().parents[3].joinpath("docs", "a.md")\n', "docs/a.md"),
        ('from pathlib import Path\nHERE = Path(__file__).parent\nROOT = HERE.parents[2]\nX = ROOT / "a/b.txt"\n', "a/b.txt"),
        ('from pathlib import Path\nARRT = Path(__file__).parents[2]\ndef f():\n    return ARRT.parent / ".env"\n', ".env"),
    ],
    ids=["parent-chain", "joinpath", "through-names", "in-a-function"],
)
def test_each_shape_of_climb_is_worked_out(source, reads_):
    values = {"/".join(v) for v, _ in reads("arrt/tests/unit/test_x.py", source) if isinstance(v, tuple)}
    assert reads_ in values, values


@pytest.mark.parametrize(
    "source",
    [
        "from pathlib import Path\nX = next(p for p in Path(__file__).parents if p)\n",
        "from pathlib import Path\nX = Path(__file__).parents[3] / name\n",
        'from pathlib import Path\nX = Path(__file__).parent / "../../../all.json"\n',
        "from pathlib import Path\nX = Path(__file__).parents[3] / 'docs'\n",
    ],
    ids=["every-ancestor", "a-name-not-a-literal", "a-string-climb", "a-directory-held-in-part"],
)
def test_a_climb_the_scan_cannot_work_out_must_be_declared(source):
    found = problems([("arrt/tests/unit/test_x.py", source)], carried_paths(_dockerfile()), declared={})
    assert len(found) == 1 and ("declare what it reads" in found[0] or "does not carry" in found[0]), found


def test_a_declaration_that_matches_nothing_or_reads_what_is_not_carried_is_refused():
    stale = {("arrt/tests/unit/test_gone.py", "Path(__file__).parents"): (frozenset({"all.json"}), "gone")}
    assert problems([], carried_paths(_dockerfile()), declared=stale) == [
        "DECLARED names ('arrt/tests/unit/test_gone.py', 'Path(__file__).parents'), which no scanned module builds any "
        "more: remove it"
    ]
    source = "from pathlib import Path\nX = next(p for p in Path(__file__).parents if p)\n"
    needs = {("arrt/tests/unit/test_x.py", "Path(__file__).parents"): (frozenset({"README.md"}), "x")}
    found = problems([("arrt/tests/unit/test_x.py", source)], carried_paths(_dockerfile()), declared=needs)
    assert found == [
        "arrt/tests/unit/test_x.py: `Path(__file__).parents` is declared to read README.md, which arrt/Dockerfile's "
        "test stage does not carry"
    ]


def test_a_read_from_the_working_directory_is_refused():
    source = 'import json\nfrom pathlib import Path\nINDEX = json.loads(Path("all.json").read_text())\n'
    found = problems([("arrt/tests/unit/test_x.py", source)], carried_paths(_dockerfile()), declared={})
    assert len(found) == 1 and "from the working directory" in found[0] and "'all.json'" in found[0], found


@pytest.mark.parametrize(
    "line,refusal",
    [
        ("COPY --from=repo all.json /data/all.json", r"puts all\.json at /data/all\.json"),
        ("COPY tests /tests", r"puts arrt/tests at /tests"),
        ("ADD src ./src", "uses ADD"),
        ("COPY pyproject.toml \\", "continues"),
        ('COPY ["a", "./"]', "exec-form"),
        ("RUN --mount=type=bind,source=x,target=/x true", "binds a source"),
    ],
    ids=["root-file-elsewhere", "arrt-dir-elsewhere", "add", "continued", "exec-form", "bind"],
)
def test_a_copy_that_does_not_land_where_the_tests_look_or_cannot_be_read_is_refused(line, refusal):
    dockerfile = f"FROM debian AS base\nWORKDIR /app\nFROM base AS test\n{line}\n"
    with pytest.raises(AssertionError, match=refusal):
        carried_paths(dockerfile)


def test_the_stage_carries_what_it_and_the_stages_beneath_it_copy_and_nothing_after_it():
    dockerfile = "\n".join(
        [
            "FROM uv:1 AS uv",
            "FROM debian AS base",
            "COPY --from=uv /uv /uvx /usr/local/bin/",
            "WORKDIR /app",
            "COPY pyproject.toml uv.lock ./",
            "FROM base AS test",
            "COPY --from=repo contract /contract",
            "COPY tests ./tests",
            "FROM base AS app",
            "COPY --from=repo all.json /all.json",
        ]
    )
    assert carried_paths(dockerfile) == {"arrt/pyproject.toml", "arrt/uv.lock", "contract", "arrt/tests"}
