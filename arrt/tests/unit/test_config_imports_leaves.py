"""Configuration imports only leaves: nothing it reaches depends on the service layer.

`arrt.config` is read by the composition root and by tools that want a value
and nothing else. Every `arrt` module it imports, and every one those import,
is part of what a reader of one environment variable loads, and a cycle through
it (a service importing configuration for a default while configuration imports
that service for a type) is a start-up failure that depends on which module
Python happens to load first.

**A leaf is a module that imports no `arrt` module but other leaves.** `LEAVES`
names them, and the walk follows every import in each file, a nested one and an
import spelled as a string included, plus the package `__init__` files an import
runs on the way. A module joins `LEAVES` by being added here, in the commit that
shows it imports nothing else of the service layer's.
"""

import ast
import importlib
import pathlib
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest

import arrt

SOURCE_ROOT = pathlib.Path(arrt.__file__).resolve().parent.parent

#: What configuration may reach. Each is checked below to import nothing outside this set.
LEAVES: frozenset[str] = frozenset(
    {
        "arrt",
        "arrt.defaults",
        "arrt.services",
        "arrt.services.errors",
        "arrt.library",
        "arrt.library.dimensions",
        "arrt.library.discovery_settings",
        "arrt.library.setting_declarations",
        "arrt.library.services",
        "arrt.library.services.quality",
    }
)

DYNAMIC_IMPORTERS: frozenset[str] = frozenset({"__import__", "import_module"})


def _file_of(name: str, root: pathlib.Path) -> pathlib.Path | None:
    base = root.joinpath(*name.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _with_parents(name: str) -> Iterator[str]:
    """`arrt.a.b` and the packages whose `__init__` importing it runs."""
    parts = name.split(".")
    for end in range(1, len(parts) + 1):
        yield ".".join(parts[:end])


def _imports_of(name: str, root: pathlib.Path) -> set[str]:
    """Every `arrt` module this module's file imports, anywhere in it."""
    path = _file_of(name, root)
    assert path is not None, f"{name} has no file under {root}"
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = package.split(".")[: len(package.split(".")) - (node.level - 1)]
                base = ".".join([*anchor, *([base] if base else [])])
            found.add(base)
            # `from arrt.x import y` imports the submodule `arrt.x.y` when there is one.
            found.update(f"{base}.{alias.name}" for alias in node.names if _file_of(f"{base}.{alias.name}", root))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name | ast.Attribute)
            and getattr(node.func, "id", getattr(node.func, "attr", "")) in DYNAMIC_IMPORTERS
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            found.add(node.args[0].value)
    return {module for module in found if module == "arrt" or module.startswith("arrt.")}


@dataclass
class Reach:
    """What a module loads: each module reached, and the module that first imported it."""

    first_imported_by: dict[str, str] = field(default_factory=dict)

    def chain(self, name: str, subject: str) -> str:
        links = [name]
        while links[-1] in self.first_imported_by and self.first_imported_by[links[-1]] != subject:
            links.append(self.first_imported_by[links[-1]])
        links.append(subject)
        return " <- ".join(links)


def _reach(subject: str, root: pathlib.Path) -> Reach:
    reach = Reach()
    pending = [subject]
    seen = {subject}
    while pending:
        current = pending.pop()
        for imported in sorted(_imports_of(current, root)):
            for module in _with_parents(imported):
                if module not in seen and _file_of(module, root) is not None:
                    seen.add(module)
                    reach.first_imported_by[module] = current
                    pending.append(module)
    return reach


def _non_leaves(subject: str, root: pathlib.Path, leaves: frozenset[str]) -> list[str]:
    """Each module `subject` loads that is not a leaf, with the chain of imports that brings it."""
    reach = _reach(subject, root)
    return [reach.chain(name, subject) for name in sorted(reach.first_imported_by) if name not in leaves]


def test_configuration_reaches_nothing_but_leaves():
    offences = _non_leaves("arrt.config", SOURCE_ROOT, LEAVES)

    assert offences == [], "arrt.config loads modules that are not leaves:\n" + "\n".join(offences)


def test_configuration_reaches_the_leaves_it_is_given():
    """The walk has to see the imports that are allowed, or a clean result proves nothing."""
    reached = set(_reach("arrt.config", SOURCE_ROOT).first_imported_by)

    assert {"arrt.defaults", "arrt.library.setting_declarations", "arrt.library.discovery_settings"} <= reached


@pytest.mark.parametrize("leaf", sorted(LEAVES))
def test_each_leaf_exists_and_loads_nothing_but_leaves(leaf: str):
    assert _file_of(leaf, SOURCE_ROOT) is not None, f"LEAVES names {leaf}, which has no file"

    assert _non_leaves(leaf, SOURCE_ROOT, LEAVES) == []


def _arrt_modules_loaded_by(module: str) -> set[str]:
    """What a fresh interpreter has loaded of `arrt` once it has imported `module`: the rule as the interpreter keeps it."""
    program = (
        f"import sys, {module}\n" "print('\\n'.join(sorted(m for m in sys.modules if m == 'arrt' or m.startswith('arrt.'))))\n"
    )
    done = subprocess.run(  # noqa: S603 -- this interpreter, running the fixed program above
        [sys.executable, "-I", "-c", program], capture_output=True, text=True, check=True
    )
    return set(done.stdout.split())


@pytest.mark.parametrize("module", ["arrt.config", *sorted(LEAVES)])
def test_importing_it_loads_no_module_that_is_not_a_leaf(module: str):
    """The walk reads the source; this reads what Python did, so an import the walk cannot see still fails here."""
    loaded = _arrt_modules_loaded_by(module)

    assert module in loaded
    assert loaded - LEAVES - {"arrt.config"} == set()


#: Where each name `arrt.defaults` owns was declared before, and so is still imported from.
DEFAULTS_OLD_HOMES: dict[str, str] = {
    "DEFAULT_PREVIEW_MAX_BYTES": "arrt.library.discovery.images",
    "DEFAULT_SOURCE_ORDER": "arrt.library.sources.loading",
    "DEFAULT_WALL_NAME": "arrt.persistence.migrations",
    "MANIFEST_V2_FILENAME_TEMPLATE": "arrt.programming.manifest.v2",
    "manifest_v2_path_in": "arrt.programming.manifest.v2",
    "HEARTBEAT_FILENAME_TEMPLATE": "arrt.programming.manifest.heartbeat",
    "heartbeat_path_in": "arrt.programming.manifest.heartbeat",
}


def _declared_names(module: str) -> list[str]:
    """The public names a module's own file defines at its top level: its classes, functions and assignments."""
    path = _file_of(module, SOURCE_ROOT)
    assert path is not None
    names: list[str] = []
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names.extend(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return [name for name in names if not name.startswith("_")]


def _moved_names() -> list[tuple[str, str, str]]:
    """(new home, old home, name) for every public name a leaf declares that used to be declared elsewhere."""
    moved = [("arrt.defaults", old, name) for name, old in DEFAULTS_OLD_HOMES.items()]
    moved += [
        ("arrt.library.setting_declarations", "arrt.library.services.settings", n)
        for n in _declared_names("arrt.library.setting_declarations")
    ]
    moved += [
        ("arrt.library.discovery_settings", "arrt.library.services.runner", n)
        for n in _declared_names("arrt.library.discovery_settings")
    ]
    return moved


@pytest.mark.parametrize(("new_home", "old_home", "name"), _moved_names())
def test_a_moved_name_is_still_importable_from_its_old_home_as_the_same_object(new_home: str, old_home: str, name: str):
    new, old = importlib.import_module(new_home), importlib.import_module(old_home)

    assert getattr(old, name) is getattr(new, name)


def test_the_old_homes_table_names_everything_defaults_owns():
    """A value added to `arrt.defaults` is either declared in the table above or has never lived anywhere else."""
    unlisted = set(_declared_names("arrt.defaults")) - set(DEFAULTS_OLD_HOMES)

    assert unlisted == set(), f"arrt.defaults declares names with no old home in DEFAULTS_OLD_HOMES: {sorted(unlisted)}"


def _tree(base: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    for relative, text in files.items():
        path = base / "arrt" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return base


class TestTheGuardCanFail:
    """Planted imports, one for each way a module gets onto configuration's path."""

    LEAF_SET = frozenset({"arrt", "arrt.defaults"})

    def _files(self, config_source: str, **more: str) -> dict[str, str]:
        files = {
            "__init__.py": "",
            "defaults.py": "X = 1\n",
            "config.py": config_source,
            "runner.py": "import arrt.persistence.migrations\n",
            "persistence/__init__.py": "",
            "persistence/migrations.py": "Y = 2\n",
        }
        files.update({key.replace("__", "/") + ".py": value for key, value in more.items()})
        return files

    def test_a_clean_configuration_passes(self, tmp_path: pathlib.Path):
        root = _tree(tmp_path, self._files("from arrt.defaults import X\n"))

        assert _non_leaves("arrt.config", root, self.LEAF_SET) == []

    def test_it_names_a_direct_import_of_the_service_layer(self, tmp_path: pathlib.Path):
        root = _tree(tmp_path, self._files("from arrt.defaults import X\nfrom arrt.runner import Y\n"))

        offences = _non_leaves("arrt.config", root, self.LEAF_SET)

        assert "arrt.runner <- arrt.config" in offences
        assert any(offence.startswith("arrt.persistence.migrations <- arrt.runner") for offence in offences)

    def test_it_names_what_a_leaf_itself_imports(self, tmp_path: pathlib.Path):
        files = self._files("from arrt.defaults import X\n")
        files["defaults.py"] = "from arrt.runner import Y\nX = 1\n"
        root = _tree(tmp_path, files)

        offences = _non_leaves("arrt.config", root, self.LEAF_SET)

        assert any(offence.startswith("arrt.runner <- arrt.defaults") for offence in offences)

    def test_it_catches_an_import_inside_a_function(self, tmp_path: pathlib.Path):
        root = _tree(tmp_path, self._files("def f():\n    from arrt.runner import Y\n    return Y\n"))

        assert "arrt.runner <- arrt.config" in _non_leaves("arrt.config", root, self.LEAF_SET)

    def test_it_catches_an_import_spelled_as_a_string(self, tmp_path: pathlib.Path):
        source = "import importlib\nimportlib.import_module('arrt.runner')\n"
        root = _tree(tmp_path, self._files(source))

        assert "arrt.runner <- arrt.config" in _non_leaves("arrt.config", root, self.LEAF_SET)

    def test_it_catches_a_package_whose_init_imports_the_service_layer(self, tmp_path: pathlib.Path):
        files = self._files("from arrt.persistence.migrations import Y\n")
        files["persistence/__init__.py"] = "from arrt import runner\n"
        root = _tree(tmp_path, files)

        offences = _non_leaves("arrt.config", root, self.LEAF_SET)

        assert any(offence.startswith("arrt.runner <- arrt.persistence") for offence in offences)

    def test_it_catches_a_relative_import(self, tmp_path: pathlib.Path):
        root = _tree(tmp_path, self._files("from . import runner\n"))

        assert "arrt.runner <- arrt.config" in _non_leaves("arrt.config", root, self.LEAF_SET)


def test_the_guard_reads_the_real_tree_when_an_import_is_planted(tmp_path: pathlib.Path):
    """The offence the owner named: one import of the discovery runner, back in the real configuration."""
    root = tmp_path / "src"
    shutil.copytree(SOURCE_ROOT / "arrt", root / "arrt", ignore=shutil.ignore_patterns("static", "__pycache__"))
    config = root / "arrt" / "config.py"
    config.write_text("from arrt.library.services.runner import DiscoverySettings\n" + config.read_text())

    offences = _non_leaves("arrt.config", root, LEAVES)

    assert "arrt.library.services.runner <- arrt.config" in offences
