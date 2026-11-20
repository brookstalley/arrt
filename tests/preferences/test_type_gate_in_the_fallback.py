"""The type gate holds in the environment CI's fallback builds, not only on the pool.

The fault this guards (seen 2026-11-20): the type check reads
`tests/system` with `mypy_path = ["tests", "tools"]`, so mypy
follows the system tests into `arrt/tools/ux_walk.py`, which imports `playwright.sync_api`
under `TYPE_CHECKING`. The pool's `[setup]` syncs arrt's `browser` group, where Playwright
is installed; the fallback's `FALLBACK_SETUP` (`.github/scripts/pool_or_fallback.py`) syncs
`dev` only, by the owner's ruling of 2026-11-20 (nothing on GitHub's runner runs
Playwright). So the type gate was green on the pool and red in the fallback, which is
the one place nobody was looking.

**What this test reads, and nothing is a copy.** The groups come from `FALLBACK_SETUP` itself
(loaded from the script, parsed from its `uv sync` commands), so a change to the fallback's
setup changes what is checked. The packages a group installs come from each project's
`uv.lock`: the project's own `dependencies` and the group's `dev-dependencies`, then every
package those need, transitively. The modules mypy follows come from each project's
`[tool.mypy]`: the configured `files`, then, by reading their source, every import that
resolves to a file under `src/`, `mypy_path` or the project root, transitively.

**What it sees that a scan of runtime imports misses.** Every `import` statement in a followed
module, wherever it sits: under `if TYPE_CHECKING:`, inside a function, in a `try`. mypy
resolves all of them, and an `import-not-found` for any is an error.

**Where the walk stops.** It follows first-party files only: an import that resolves to no file
of the project is a third-party (or standard-library) name, checked against the environment and
not entered, because mypy does not report errors inside an installed package. It does not follow
what it cannot read statically: `importlib.import_module("x")`, `__import__`, an import built in
a string. `.pyi` stubs next to a source file are not read. A namespace package without an
`__init__.py` resolves as first-party by its directory.

**What it cannot map, and what it does then.** An import name is not always a distribution name
(`yaml` is `pyyaml`). The lockfile lists distributions, not the modules they install, so the
mapping is this file's `DISTRIBUTION_OF` table for the names that differ, and an import's own
name (case and `-`/`_` folded) otherwise. An import neither the table nor its own name maps to
an installed distribution is reported as missing, naming itself and this table: the failure is
loud and its fix is a line here or in the allowance, never silent. The other side of it, which
the test cannot see: a distribution that is installed but ships no `py.typed` fails mypy as
`import-untyped`, not `import-not-found`; that is mypy's own error, which the type gate itself
reports in both environments. Environment markers in the lock (`sys_platform == ...`) are
ignored, so a dependency that exists only on another platform counts as installed: the check
under-reports there, never over-reports. `--extra` flags in a sync command are refused by name.

The test reads `.github/scripts/pool_or_fallback.py`, `arrt/pyproject.toml`, `arrt/uv.lock`,
`contract/pyproject.toml`, `contract/uv.lock`, and the source of the followed modules. It is a
root test, so the server image's test stage (which carries only some repository-root files) does
not run it.
"""

import ast
import fnmatch
import importlib.util
import pathlib
import re
import sys
import tomllib
from collections.abc import Iterator, Mapping, Sequence

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "pool_or_fallback.py"

#: The distribution that provides an import name, where the two differ beyond case and `-` for `_`.
#: Only names the followed modules use need be here; one that is missing is reported, not skipped.
DISTRIBUTION_OF = {
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "PIL": "pillow",
    # One top-level package, `threetears`, split across the `3tears-*` distributions: checked as the core `3tears`
    # that every one of them needs, so a missing `3tears-models` alone is not seen.
    "threetears": "3tears",
}


def _normal(name: str) -> str:
    """The form PEP 503 compares distribution names in."""
    return re.sub(r"[-_.]+", "-", name).lower()


def load_fallback_setup() -> Mapping[str, Sequence[Sequence[str]]]:
    """`FALLBACK_SETUP`, from the script itself."""
    spec = importlib.util.spec_from_file_location("pool_or_fallback_for_the_type_gate", SCRIPT)
    assert spec and spec.loader, f"cannot load {SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass in the script looks its module up by name
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module.FALLBACK_SETUP


def _pyproject(project: str) -> dict:
    return tomllib.loads((ROOT / project / "pyproject.toml").read_text(encoding="utf-8"))


def _default_groups(project: str) -> list[str]:
    return list(_pyproject(project).get("tool", {}).get("uv", {}).get("default-groups", ["dev"]))


def _all_groups(project: str) -> list[str]:
    return list(_pyproject(project).get("dependency-groups", {}))


class UnreadableSyncCommand(ValueError):
    """A `uv sync` flag this test does not know the meaning of, which would let it check the wrong environment."""


def groups_synced(setup: Mapping[str, Sequence[Sequence[str]]], default_groups=_default_groups, all_groups=_all_groups):
    """`{project: (groups installed, installs the project's own dependencies)}` for every `uv sync` in `setup`.

    A project synced twice (two suites, two commands) gets the union. A flag it cannot read is
    refused by name: guessing the environment is how this test would pass on the wrong one.
    """
    found: dict[str, tuple[set[str], bool]] = {}
    for commands in setup.values():
        for command in commands:
            if list(command[:2]) != ["uv", "sync"]:
                continue
            project, groups, only, no_default, no_dev, every = ".", [], [], False, False, False
            args = list(command[2:])
            while args:
                arg = args.pop(0)
                if arg == "--frozen":
                    continue
                elif arg == "--project":
                    project = args.pop(0)
                elif arg == "--group":
                    groups.append(args.pop(0))
                elif arg == "--only-group":
                    only.append(args.pop(0))
                elif arg == "--no-dev":
                    no_dev = True
                elif arg == "--no-default-groups":
                    no_default = True
                elif arg == "--all-groups":
                    every = True
                else:
                    raise UnreadableSyncCommand(
                        f"{' '.join(command)!r}: this test does not know `{arg}`; teach it in `groups_synced` "
                        "before it can say which packages the fallback installs"
                    )
            if every:
                wanted = set(all_groups(project))
            elif only:
                wanted = set(only)
            else:
                wanted = set(groups) | (set() if no_default else set(default_groups(project)))
                if no_dev:
                    wanted.discard("dev")
            has_project = not only
            before_groups, before_project = found.get(project, (set(), False))
            found[project] = (before_groups | wanted, before_project or has_project)
    return found


def installed_distributions(lock: dict, project_name: str, groups: set[str], with_project: bool = True) -> set[str]:
    """Every distribution `uv sync --group <groups>` installs, from the lock: what the project and groups name, transitively."""
    packages = {_normal(p["name"]): p for p in lock["package"]}
    root = packages[_normal(project_name)]
    wanted = [d["name"] for d in root.get("dependencies", [])] if with_project else []
    for group in sorted(groups):
        wanted += [d["name"] for d in root.get("dev-dependencies", {}).get(group, [])]
    seen: set[str] = set()
    while wanted:
        name = _normal(wanted.pop())
        if name in seen:
            continue
        seen.add(name)
        wanted += [d["name"] for d in packages[name].get("dependencies", [])]
    return seen


def _candidate_dirs(project: pathlib.Path, config: dict) -> list[pathlib.Path]:
    """Where mypy looks for a first-party module: the project root, `src/`, each `mypy_path` entry, and the base of each
    configured directory (mypy's crawl root: the first directory upward that holds no `__init__.py`)."""
    bases = []
    for entry in config.get("files", []):
        base = (project / entry).resolve()
        if base.is_dir():
            while (base / "__init__.py").is_file():
                base = base.parent
            bases.append(base)
    return [project, project / "src", *(project / p for p in config.get("mypy_path", [])), *bases]


def _resolve(dotted: str, dirs: Sequence[pathlib.Path]) -> pathlib.Path | None:
    parts = dotted.split(".")
    for directory in dirs:
        base = directory.joinpath(*parts)
        if base.with_suffix(".py").is_file():
            return base.with_suffix(".py")
        if (base / "__init__.py").is_file():
            return base / "__init__.py"
    return None


def _is_first_party(top: str, dirs: Sequence[pathlib.Path]) -> bool:
    return any((d / top).is_dir() or (d / f"{top}.py").is_file() for d in dirs)


def _files_of(project: pathlib.Path, config: dict) -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for entry in config.get("files", []):
        path = project / entry
        found += sorted(path.rglob("*.py")) if path.is_dir() else [path]
    return found


def _imports(path: pathlib.Path) -> Iterator[tuple[str, int, bool, int, bool]]:
    """`(name, line, under TYPE_CHECKING, relative level, is a member)` for every import in `path`, wherever it sits.

    A member is `sub` in `from pkg import sub`: it may be a submodule file to follow, and is never reported on its own.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and re.search(r"\bTYPE_CHECKING\b", ast.unparse(node.test)):
            guarded.update(id(child) for part in node.body for child in ast.walk(part))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno, id(node) in guarded, 0, False
        elif isinstance(node, ast.ImportFrom):
            yield node.module or "", node.lineno, id(node) in guarded, node.level, False
            for alias in node.names:
                yield f"{node.module or ''}.{alias.name}".strip("."), node.lineno, id(node) in guarded, node.level, True


def followed_imports(project: pathlib.Path, config: dict):
    """Walk from `files`: `[(path, imported dotted name, line, guarded)]` for every import of every followed module.

    A relative import and an import that resolves to a file under the project are followed (and
    not reported); the rest are returned for the caller to check against the environment.
    """
    dirs = _candidate_dirs(project, config)
    pending = _files_of(project, config)
    seen: set[pathlib.Path] = set()
    outside = []
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        for name, line, guarded, level, member in _imports(path):
            if level:
                base = path.parent
                for _ in range(level - 1):
                    base = base.parent
                target = _resolve(name, [base]) if name else base / "__init__.py"
                if target and target.is_file() and target not in seen:
                    pending.append(target)
                continue
            top = name.split(".")[0]
            if top in sys.stdlib_module_names:
                continue
            if _is_first_party(top, dirs):
                target = _resolve(name, dirs)
                if target and target not in seen:
                    pending.append(target)
                continue
            if not member:
                outside.append((path, name, line, guarded))
    return outside


def _module_name(path: pathlib.Path, project: pathlib.Path) -> str:
    """The name a path has in the type gate's own messages: `tools.ux_walk`, `tests.system.conftest`, `arrt.http.app`."""
    relative = path.relative_to(project).with_suffix("")
    parts = list(relative.parts)
    if parts[0] == "src":
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _listed(module: str, patterns: Sequence[str]) -> bool:
    return any(module == p or (p.endswith(".*") and (module == p[:-2] or fnmatch.fnmatch(module, p))) for p in patterns)


def allowance_of(config: dict) -> list[str]:
    """The modules `ignore_missing_imports` lets be missing, from every override that sets it."""
    return [
        module
        for override in config.get("overrides", [])
        if override.get("ignore_missing_imports")
        for module in ([override["module"]] if isinstance(override["module"], str) else override["module"])
    ]


def fallback_gaps(
    project_name: str,
    project: pathlib.Path,
    config: dict,
    lock: dict,
    groups: set[str],
    with_project: bool,
    allowance: Sequence[str],
) -> list[str]:
    """One line per third-party import the type check follows that the environment of `groups` would not have.

    Empty is the pass. Each line names the module that imports it, the file and line, whether the import
    is guarded by `TYPE_CHECKING` alone, and what to do.
    """
    installed = installed_distributions(lock, project_name, groups, with_project)
    gaps = []
    for path, name, line, guarded in sorted(followed_imports(project, config), key=lambda f: (str(f[0]), f[2], f[1])):
        top = name.split(".")[0]
        if _normal(DISTRIBUTION_OF.get(top, top)) in installed or _listed(name, allowance):
            continue
        where = "under TYPE_CHECKING only" if guarded else "at runtime"
        gaps.append(
            f"{_module_name(path, project)} ({path.relative_to(project)}:{line}) imports {name} {where}, but the environment "
            f"`uv sync` builds from groups {sorted(groups)} for {project_name} installs no distribution for `{top}`. "
            f"mypy would stop there with import-not-found. Install it in those groups, change what the fallback syncs, "
            f"or name it in `ignore_missing_imports` in {project.name}/pyproject.toml (and in DISTRIBUTION_OF here if its "
            f"distribution is named differently from its import)."
        )
    return gaps


def _lock(project: str) -> dict:
    return tomllib.loads((ROOT / project / "uv.lock").read_text(encoding="utf-8"))


def gaps_of_project(project: str, setup, allowance_override: Sequence[str] | None = None) -> list[str]:
    synced = groups_synced(setup)
    assert (
        project in synced
    ), f"the fallback's setup (`FALLBACK_SETUP`) syncs no environment for {project}/, so its type check has none"
    groups, with_project = synced[project]
    config = _pyproject(project)["tool"]["mypy"]
    allowance = allowance_of(config) if allowance_override is None else allowance_override
    name = _pyproject(project)["project"]["name"]
    return fallback_gaps(name, ROOT / project, config, _lock(project), groups, with_project, allowance)


# --------------------------------------------------------------------------------------------------
# The gate itself


@pytest.mark.parametrize("project", ["arrt", "contract"])
def test_every_import_the_type_check_follows_is_installed_in_the_fallbacks_environment(project):
    gaps = gaps_of_project(project, load_fallback_setup())
    assert not gaps, "\n".join(["the type check would fail in CI's fallback environment:", *gaps])


def test_the_fallback_syncs_the_groups_the_gate_reads_from_its_own_setup():
    """What the gate reads is `FALLBACK_SETUP`: today dev for each project, never the pool's `browser` group."""
    synced = groups_synced(load_fallback_setup())
    assert synced["arrt"][0] == {"dev"} and synced["contract"][0] == {"dev"}, synced


# --------------------------------------------------------------------------------------------------
# Each check shown able to fail


def test_playwright_taken_out_of_the_allowance_is_red_naming_the_module_and_the_import():
    """The fault itself: `tools/ux_walk.py` imports `playwright.sync_api` under TYPE_CHECKING."""
    config = _pyproject("arrt")["tool"]["mypy"]
    without = [m for m in allowance_of(config) if not m.startswith("playwright")]
    assert without != allowance_of(config), "the allowance no longer names playwright, so this proves nothing: update the test"

    gaps = gaps_of_project("arrt", load_fallback_setup(), without)

    assert any(
        g.startswith("tools.ux_walk (tools/ux_walk.py:") and "imports playwright.sync_api under TYPE_CHECKING only" in g
        for g in gaps
    ), gaps


def test_the_fallback_syncing_the_browser_group_follows_and_the_same_import_passes():
    """The check follows `FALLBACK_SETUP`: add `--group browser` there and Playwright is installed, so no allowance is needed."""
    config = _pyproject("arrt")["tool"]["mypy"]
    without = [m for m in allowance_of(config) if not m.startswith("playwright")]
    changed = {"governance": (["uv", "sync", "--frozen", "--project", "arrt", "--group", "dev", "--group", "browser"],)}
    changed["governance"] += (["uv", "sync", "--frozen", "--project", "contract", "--group", "dev"],)

    assert gaps_of_project("arrt", changed, without) == []
    assert gaps_of_project("arrt", load_fallback_setup(), without), "the real setup must still lack Playwright"


def _tree(tmp_path: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    files = {"src/proj/__init__.py": "", **files}
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def _lock_of(**dists: list[str]) -> dict:
    """A lock with a project `proj` whose `dev` group needs `dev`, and each named distribution needing the listed ones."""
    packages = [
        {
            "name": "proj",
            "dependencies": [{"name": d} for d in dists.get("runtime", [])],
            "dev-dependencies": {"dev": [{"name": d} for d in dists.get("dev", [])], "browser": [{"name": "pw"}]},
        },
        {"name": "pw", "dependencies": [{"name": "playwright"}]},
        {"name": "playwright"},
    ]
    packages += [{"name": d} for d in set(dists.get("runtime", []) + dists.get("dev", []))]
    packages += [
        {"name": name, "dependencies": [{"name": n} for n in needs]} for name, needs in dists.items() if name.startswith("dep-")
    ]
    return {"package": packages}


CONFIG = {"files": ["src/proj", "tests/system"], "mypy_path": ["tests", "tools"]}


def _gaps(tmp_path, files, *, groups=("dev",), allowance=(), lock=None):
    project = _tree(tmp_path, files)
    lock = lock or _lock_of(runtime=["yaml-lib"], dev=["pytest"])
    return fallback_gaps("proj", project, CONFIG, lock, set(groups), True, list(allowance))


def test_a_new_third_party_import_under_type_checking_in_a_followed_module_is_red(tmp_path):
    files = {
        "tests/system/test_a.py": "import helper\n",
        "tests/helper.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from newlib.api import Thing\n",
    }
    gaps = _gaps(tmp_path, files)

    assert len(gaps) == 1 and gaps[0].startswith(
        "tests.helper (tests/helper.py:3) imports newlib.api under TYPE_CHECKING only"
    ), gaps


def test_the_same_import_at_runtime_is_red_too_and_says_so(tmp_path):
    gaps = _gaps(tmp_path, {"tests/system/test_a.py": "import newlib\n"})

    assert len(gaps) == 1 and "imports newlib at runtime" in gaps[0], gaps


def test_an_import_inside_a_function_and_inside_a_try_is_seen(tmp_path):
    source = "def f():\n    import deep\n\ntry:\n    import maybe\nexcept ImportError:\n    maybe = None\n"
    gaps = _gaps(tmp_path, {"tests/system/test_a.py": source})

    assert sorted(g.split(" imports ")[1].split(" ")[0] for g in gaps) == ["deep", "maybe"], gaps


def test_a_module_the_configured_files_do_not_reach_is_not_followed(tmp_path):
    """A tool nothing imports (`tools/mat_corpus.py`) is not type checked, so what it imports is not asked for."""
    files = {"tests/system/test_a.py": "x = 1\n", "tools/unreached.py": "import newlib\n"}

    assert _gaps(tmp_path, files) == []


def test_the_walk_is_transitive_through_a_relative_import_and_a_package(tmp_path):
    files = {
        "tests/system/test_a.py": "from pkg import inner\n",
        "tests/pkg/__init__.py": "",
        "tests/pkg/inner.py": "from . import leaf\n",
        "tests/pkg/leaf.py": "import newlib\n",
    }
    gaps = _gaps(tmp_path, files)

    assert len(gaps) == 1 and gaps[0].startswith("tests.pkg.leaf (tests/pkg/leaf.py:1) imports newlib"), gaps


def test_what_a_group_installs_is_what_it_names_and_what_those_need(tmp_path):
    lock = _lock_of(runtime=["dep-a"], dev=["pytest"], **{"dep-a": ["transitive"]})
    lock["package"].append({"name": "transitive"})
    files = {"tests/system/test_a.py": "import transitive\nimport pytest\nimport playwright\n"}

    gaps = _gaps(tmp_path, files, lock=lock)
    assert len(gaps) == 1 and "imports playwright" in gaps[0], gaps  # only the browser group names it
    assert _gaps(tmp_path, files, lock=lock, groups=("dev", "browser")) == []


def test_the_allowance_excuses_a_listed_import_and_only_that_one(tmp_path):
    files = {"tests/system/test_a.py": "import newlib.api\nimport other\n"}
    gaps = _gaps(tmp_path, files, allowance=["newlib", "newlib.*"])

    assert len(gaps) == 1 and "imports other" in gaps[0], gaps


def test_an_import_name_unlike_its_distribution_maps_by_the_table_and_an_unmapped_one_is_red(tmp_path):
    lock = _lock_of(runtime=["pyyaml", "left-pad"])
    gaps = _gaps(tmp_path, {"tests/system/test_a.py": "import yaml\nimport leftpad\n"}, lock=lock)

    assert len(gaps) == 1 and "imports leftpad" in gaps[0] and "DISTRIBUTION_OF" in gaps[0], gaps


def test_a_relative_and_a_standard_library_import_are_never_third_party(tmp_path):
    files = {
        "tests/system/test_a.py": "from __future__ import annotations\nimport os, json\nfrom . import sibling\n",
        "tests/system/sibling.py": "",
    }

    assert _gaps(tmp_path, files) == []


@pytest.mark.parametrize(
    "command,groups",
    [
        (["uv", "sync", "--frozen", "--project", "p", "--group", "dev"], {"dev"}),
        (["uv", "sync", "--frozen", "--project", "p", "--group", "dev", "--group", "browser"], {"dev", "browser"}),
        (["uv", "sync", "--project", "p"], {"dev"}),
        (["uv", "sync", "--project", "p", "--no-dev"], set()),
        (["uv", "sync", "--project", "p", "--only-group", "browser"], {"browser"}),
        (["uv", "sync", "--project", "p", "--all-groups"], {"dev", "browser"}),
    ],
)
def test_the_sync_command_is_read_for_the_groups_it_installs(command, groups):
    read = groups_synced({"s": [command]}, default_groups=lambda p: ["dev"], all_groups=lambda p: ["dev", "browser"])

    assert read["p"][0] == groups


def test_a_sync_flag_this_test_cannot_read_is_refused_by_name():
    with pytest.raises(UnreadableSyncCommand, match="--extra"):
        groups_synced({"s": [["uv", "sync", "--project", "p", "--extra", "x"]]})


def test_a_project_with_no_sync_in_the_fallback_is_red_by_name():
    with pytest.raises(AssertionError, match="syncs no environment for contract/"):
        gaps_of_project("contract", {"governance": (["uv", "sync", "--frozen", "--project", "arrt", "--group", "dev"],)})
