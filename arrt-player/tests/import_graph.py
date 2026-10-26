"""How the plane-isolation guard reads this project's source.

A copy of Arrt's own reader (its governance suite's `import_graph.py`, behind its
seam guard), carried when the repositories split so this guard needs nothing
outside the Player: a relative import, a `from x import y` that names a
submodule, and an import spelled as a string all count as imports.
"""

import ast
import pathlib
from collections.abc import Iterator

#: How a module smuggles an import past an AST that only reads `import` lines.
DYNAMIC_IMPORTERS: frozenset[str] = frozenset({"__import__", "import_module"})


def imported_names(path: pathlib.Path) -> Iterator[str]:
    """Every module name this file imports, absolute and relative alike.

    Relative imports are resolved against the file's own package, so
    `from .helper import x` yields `plane.helper` and can be followed like any
    other name. Names passed to `import_module` or `__import__` as literals are
    yielded too — an import expressed as a string is still an import.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = package_of(path)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            yield from _from_names(node, package)
        elif isinstance(node, ast.Call):
            called = node.func
            name = called.attr if isinstance(called, ast.Attribute) else getattr(called, "id", None)
            argument = node.args[0] if node.args else None
            if name in DYNAMIC_IMPORTERS and isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                yield argument.value


def _from_names(node: ast.ImportFrom, package: list[str]) -> Iterator[str]:
    """The names a `from … import …` may import, resolving a relative one against `package`."""
    if node.level:
        # `package_of` ends with the module's own stem, so the package a
        # level-1 import resolves against is everything before it — one
        # more level strips one more parent. Getting this off by one is
        # how a guard silently stops following the relative imports that
        # make up most of a well-formed package.
        base = package[: max(0, len(package) - node.level)]
        prefix = ".".join([*base, node.module] if node.module else base)
    else:
        prefix = node.module or ""
    if prefix:
        yield prefix
        for alias in node.names:
            # `from x import y` may be importing the submodule `x.y`
            # rather than a name inside `x`, and only the filesystem can
            # say which — so both readings are offered to the resolver.
            yield f"{prefix}.{alias.name}"


def package_of(path: pathlib.Path) -> list[str]:
    """The dotted package this file sits in, by walking up while `__init__.py` lasts."""
    parts: list[str] = []
    directory = path.parent
    while (directory / "__init__.py").is_file():
        parts.insert(0, directory.name)
        directory = directory.parent
    return [*parts, path.stem]


def resolve(name: str, roots: tuple[pathlib.Path, ...]) -> pathlib.Path | None:
    """Where a module name lands in this repository, or None if it is third-party.

    Returning None for third-party names is what keeps the television's transport
    out of scope: `samsungtvws` imports `aiohttp`, and following into
    site-packages would report the library's own dependency as this plane's.
    """
    relative = pathlib.Path(*name.split("."))
    for root in roots:
        for candidate in (root / relative.with_suffix(".py"), root / relative / "__init__.py"):
            if candidate.is_file():
                return candidate
    return None
