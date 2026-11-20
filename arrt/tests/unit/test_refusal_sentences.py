"""The server's refusals, read from its source: a not-found is `NotFound`, and a sentence names the Library and themes.

Two guards over every place under `arrt/src/arrt` that builds a refusal: a call
to `ServiceError` or to any class the source derives from it (`NotFound`,
`FeedTooLarge`, `ThumbnailUnavailable`, and whatever is added later), and the
`detail` of an `Unplayable`, which `themes.py` raises as it stands. The sites
are derived from the source on every run, never listed by hand, so a refusal
added tomorrow is read tomorrow. Chunk 37 of `build-plan-audit-wave-2b.md`.

1. **A not-found raised as a plain `ServiceError` is refused**, naming its site.
   `/api` answers a `NotFound` with 404 and a plain `ServiceError` with 400
   (`app.py`), so a not-found sentence raised as the plain class is a 404 the
   browser never gets. "Not found" is read off the sentence: "No <thing> with
   id …", "There is no setting …", "… has no facet with id …".
2. **No refusal says catalogue, collection or playlist** (the owner's rulings
   1 and 2 of 2026-11-19: the household's holdings are the Library; theme, not
   playlist, wherever a person reads). A museum's collection is still a
   collection, and no refusal names one today; one that comes to would be
   worded for the museum here, with its reason.

What a sentence is, at a site: its literal text, an f-string's literal parts, a
module-level constant it names (`_SCENE_NOT[...]`), and the returned text of a
function it calls by name (`no_wall(...)`). A message the source cannot resolve
(`str(exc)`, `answer.detail`) is not read at that site; where it is built, it is.
"""

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

import arrt

SRC = Path(arrt.__file__).resolve().parent

#: A sentence that says the thing named is not there.
NOT_FOUND = re.compile(r"^No [A-Za-z][\w -]* with id\b|^There is no setting\b| has no facet with id ")

#: The words rulings 1 and 2 take out of what a person reads.
REFUSED_WORDS = re.compile(r"\b(catalogue|collections?|playlists?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Refusal:
    """One place a refusal is built: where, which class, and the text the source says it carries."""

    site: str
    raised_as: str
    text: str


def _parsed() -> dict[Path, ast.Module]:
    return {path: ast.parse(path.read_text(encoding="utf-8")) for path in sorted(SRC.rglob("*.py"))}


def _family(modules: dict[Path, ast.Module]) -> set[str]:
    """`ServiceError` and every class the source derives from it, however many steps removed."""
    bases: dict[str, set[str]] = {}
    for tree in modules.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases[node.name] = {base.id for base in node.bases if isinstance(base, ast.Name)}
    family = {"ServiceError"}
    grew = True
    while grew:
        grew = False
        for name, parents in bases.items():
            if name not in family and parents & family:
                family.add(name)
                grew = True
    return family


class _Texts:
    """The text a refusal's argument resolves to, through constants and the functions that return it."""

    def __init__(self, modules: dict[Path, ast.Module]) -> None:
        self._constants: dict[tuple[Path, str], ast.expr] = {}
        self._functions: dict[str, list[ast.FunctionDef]] = {}
        for path, tree in modules.items():
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self._constants[(path, target.id)] = node.value
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                    self._constants[(path, node.target.id)] = node.value
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    self._functions.setdefault(node.name, []).append(node)

    def of(self, node: ast.expr, path: Path, depth: int = 0) -> list[str]:
        if depth > 4:
            return []
        literal = _literal(node)
        if literal:
            return literal
        if isinstance(node, ast.Call):
            return self._called(node, path, depth)
        if isinstance(node, ast.Name):
            value = self._constants.get((path, node.id))
            return (
                []
                if value is None
                else [text for each in ast.walk(value) if isinstance(each, ast.expr) for text in _literal(each)]
            )
        parts = (
            [node.left, node.right] if isinstance(node, ast.BinOp) else [node.value] if isinstance(node, ast.Subscript) else []
        )
        return [text for part in parts for text in self.of(part, path, depth + 1)]

    def _called(self, node: ast.Call, path: Path, depth: int) -> list[str]:
        """`"…".format(...)` reads its string; `no_wall(...)` reads what the function returns."""
        if isinstance(node.func, ast.Attribute):
            return self.of(node.func.value, path, depth + 1)
        if isinstance(node.func, ast.Name):
            return [
                text
                for function in self._functions.get(node.func.id, [])
                for each in ast.walk(function)
                if isinstance(each, ast.Return) and each.value is not None
                for text in self.of(each.value, path, depth + 1)
            ]
        return []


def _literal(node: ast.expr) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return ["".join(part.value if isinstance(part, ast.Constant) else "{}" for part in node.values)]
    return []


def _site(path: Path, root: Path, node: ast.AST) -> str:
    where = path.relative_to(root) if path.is_relative_to(root) else path
    return f"{where}:{getattr(node, 'lineno', 0)}"


def _is_super_init(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "__init__"
        and isinstance(node.func.value, ast.Call)
        and isinstance(node.func.value.func, ast.Name)
        and node.func.value.func.id == "super"
        and bool(node.args)
    )


def _arguments(node: ast.Call, family: set[str]) -> tuple[str, list[ast.expr]] | None:
    """The class a call builds and the argument carrying its sentence, or None for a call that builds no refusal."""
    if not isinstance(node.func, ast.Name):
        return None
    if node.func.id in family and node.args:
        return node.func.id, [node.args[0]]
    if node.func.id == "Unplayable":
        return "Unplayable", [keyword.value for keyword in node.keywords if keyword.arg == "detail"]
    return None


def refusals(modules: dict[Path, ast.Module] | None = None, *, root: Path = SRC) -> Iterator[Refusal]:
    """Every refusal the source builds, with the text each resolves to."""
    modules = _parsed() if modules is None else modules
    family = _family(modules) | {"ServiceError", "NotFound"}
    texts = _Texts(modules)
    for path, tree in modules.items():
        # A subclass that writes its own sentence passes it to `super().__init__`.
        for cls in ast.walk(tree):
            if isinstance(cls, ast.ClassDef) and cls.name in family:
                for node in filter(_is_super_init, ast.walk(cls)):
                    assert isinstance(node, ast.Call)
                    for text in texts.of(node.args[0], path):
                        yield Refusal(_site(path, root, node), cls.name, text)
        for node in ast.walk(tree):
            built = _arguments(node, family) if isinstance(node, ast.Call) else None
            if built is not None:
                raised_as, carrying = built
                for argument in carrying:
                    for text in texts.of(argument, path):
                        yield Refusal(_site(path, root, node), raised_as, text)


def plain_not_found(found: list[Refusal]) -> list[str]:
    """The sites raising a not-found sentence as a plain `ServiceError`."""
    return sorted({refusal.site for refusal in found if refusal.raised_as == "ServiceError" and NOT_FOUND.search(refusal.text)})


ALL = list(refusals())


def test_the_derivation_reads_each_way_a_refusal_is_built():
    """The anchor: each resolution path finds a sentence it must find, so a silent guard is not a blind one."""
    by_head = {refusal.raised_as for refusal in ALL}
    assert {"ServiceError", "NotFound", "FeedTooLarge", "ThumbnailUnavailable", "Unplayable"} <= by_head
    texts = {refusal.text for refusal in ALL}
    assert "No wall with id {} is recorded." in texts, "a sentence returned by a function the refusal calls (no_wall)"
    assert any(text.startswith("No work in the queue failed for that reason now") for text in texts), "a literal"
    assert "That scene is {status}." in texts, "a module constant it names (_SCENE_NOT)"


def test_a_planted_plain_not_found_is_named_by_its_site(tmp_path):
    """The guard can fail: a `ServiceError` with a not-found sentence is caught, a `NotFound` with the same is not."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        "def find(wall_id):\n"
        "    raise ServiceError(f'No wall with id {wall_id!r} is recorded.')\n"
        "def find_properly(wall_id):\n"
        "    raise NotFound(f'No wall with id {wall_id!r} is recorded.')\n",
        encoding="utf-8",
    )
    modules = {planted: ast.parse(planted.read_text(encoding="utf-8"))}

    assert plain_not_found(list(refusals(modules, root=tmp_path))) == ["planted.py:2"]


def test_no_not_found_is_raised_as_a_plain_service_error():
    assert plain_not_found(ALL) == []


@pytest.mark.parametrize("refusal", [refusal for refusal in ALL if REFUSED_WORDS.search(refusal.text)] or [None], ids=str)
def test_no_refusal_names_the_catalogue_a_collection_or_a_playlist(refusal):
    """Parametrised over the refusals that say one, so each is named; `None` alone is the pass."""
    assert refusal is None, f"{refusal.site} ({refusal.raised_as}) says: {refusal.text}"
