"""The server's refusals, read from its source: a not-found is `NotFound`, and a sentence names the Library and themes.

Two guards over every place under `arrt/src/arrt` that builds a refusal: a call
to `ServiceError` or to any class the source derives from it (`NotFound`,
`FeedTooLarge`, `ThumbnailUnavailable`, and whatever is added later), and the
`detail` of an `Unplayable`, which `themes.py` raises as it stands. The sites
are derived from the source on every run, never listed by hand, so a refusal
added tomorrow is read tomorrow.

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

3. **No sentence a person reads, built anywhere, says it either** (the
   section at the end of this file): every prose string in every module, minus
   documentation, a logger's arguments, the start-up refusals and a few reasoned
   sentences. That section says what it reads, what it leaves out and how it knows,
   and what it cannot see.
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


# -- the sentences a person reads, wherever they are built -----------------------
#
# The guards above read refusals. Five other sentences a person reads on a screen
# (Status's description of a household with no wall, the notice after accepting a work the
# Library nearly holds, the backup trouble and its panel, the fetch queue's reason for pausing)
# said "the catalogue" after the refusals stopped, because nothing read them. This reads every
# string the source builds, except the kinds below, and applies the same words.
#
# What it reads: every string literal, and every literal part of an f-string, in every module
# under `arrt/src/arrt`, found by a glob, so a module added tomorrow is read tomorrow. It reads
# prose only: a text of two words or more.
#
# What it does not read, and how it knows each:
#
# * A docstring or any bare string statement: documentation, not a sentence a person is
#   shown (the node is an `ast.Expr` holding a string).
# * An argument to a call on a logger: the operator's journal. A logger is a name the module
#   binds with `logging.getLogger(...)`, found in the module and not listed. The journal says
#   "the catalogue" because the catalogue is the operator's file (`catalogue.sqlite`), and its
#   lines say a client is "removed" where a screen says a Player is forgotten: they are the
#   code's nouns, for whoever reads the NAS's journal, and no test or record names them.
# * The modules that run before the server answers and whose sentences reach the terminal
#   (`START_UP_MODULES`): the start-up refusals. The guard knows by
#   `test_a_start_up_module_reaches_no_person`: no refusal in the `ServiceError` family (which
#   `/api` renders) is built in one, and no exception class one defines is named anywhere else
#   in the source, so nothing catches it and carries its text onward.
# * Code in another language (SQL, SPARQL) and a prompt to a model: a person does not read them.
# * `library/sources/`, for the word "collection" only: a museum speaks of its own collection,
#   and a museum's collection is still a collection (ruling 2).
# * A handful of sentences each given its reason in `OUTSIDE_SENTENCES`, and each checked to
#   still be there (`test_every_exemption_still_exempts_something`), so a stale one is deleted.
#
# What it cannot see: a sentence assembled from parts (`"cata" + "logue"`, `" ".join(...)`, a
# word that arrives from a value such as an enum's, a stored name or a plugin's); a comment (not
# in the tree); a string in a file that is not Python (the client's JavaScript has its own
# guards, `test_client_vocabulary.py`); and whether a sentence in a non-exempt module is in
# fact shown: a literal saying "the catalogue" in a module no person reads is named all the same,
# and the answer is to word it for the Library or to give it its reason below.

#: Modules that run before the server answers, whose sentences go to the operator's terminal.
START_UP_MODULES: dict[str, str] = {
    "__main__.py": "the command line: its help text and its refusals are the operator's",
    "art_root.py": "a start-up refusal (`ArtRootError`) and the marker file's text, both for the operator",
    "persistence/file.py": "`NewerRelease` stops the start, naming the catalogue file the operator holds",
    "persistence/migrations.py": "a migration's refusal names the catalogue file the operator holds",
    "persistence/backup.py": "`SnapshotFailed` stops a migration that has no copy to fall back on",
}

#: Modules whose strings are code in another language, or a prompt to a model: not read by a person.
NOT_PROSE_MODULES: dict[str, str] = {
    "persistence/sqlite.py": "SQL: a comment in a schema is code, read by nobody on a screen",
    "persistence/sqlite_discovery.py": "SQL: a statement, not a sentence",
    "library/registry/wikidata.py": "SPARQL: `?collection` is Wikidata's variable",
    "library/discovery/phase_one.py": "a prompt to a model; a person does not read it",
}

OUTSIDE_MODULES: dict[str, str] = START_UP_MODULES | NOT_PROSE_MODULES

#: Where a museum speaks of its own collection.
MUSEUM_MODULES = "library/sources/"

#: One sentence at a time: (module, the start of its text) to why it may say what the words refuse.
OUTSIDE_SENTENCES: dict[tuple[str, str], str] = {
    ("library/services/runner.py", "Offered by the collection"): "the collection a run browsed is a museum's",
    ("library/services/runner.py", "The collection's own record"): "the collection a run browsed is a museum's",
    (
        "library/sources/plugin.py",
        "A plugin's parts need a finder",
    ): (
        "'collection' is the plugin interface's own word for one of its parts (a collection browser), "
        "not a holding; Status shows this reason for a plugin that did not load"
    ),
    ("mcp/bindings.py", "No image instances have been found"): "the collection that has the work is a museum's",
    ("mcp/bindings.py", " Separately, the collection offered"): "the collection that offered works is a museum's",
}


@dataclass(frozen=True)
class Sentence:
    """One string the source builds that reads as prose: where, in which module, and its text."""

    site: str
    module: str
    text: str


def _loggers(tree: ast.Module) -> set[str]:
    """The names this module binds to `logging.getLogger(...)`."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "getLogger"
        ):
            names |= {target.id for target in node.targets if isinstance(target, ast.Name)}
    return names


def _unread(tree: ast.Module) -> set[int]:
    """The ids of the nodes the guard does not read: bare string statements and everything a logger is given."""
    loggers = _loggers(tree)
    unread: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            unread.add(id(node.value))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in loggers
        ):
            unread |= {id(each) for each in ast.walk(node)}
    return unread


def _module(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name


def sentences(modules: dict[Path, ast.Module] | None = None, *, root: Path = SRC) -> Iterator[Sentence]:
    """Every prose string the source builds, outside documentation and a logger's arguments."""
    modules = _parsed() if modules is None else modules
    for path, tree in modules.items():
        unread = _unread(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in unread
                and len(node.value.split()) >= 2
            ):
                yield Sentence(_site(path, root, node), _module(path, root), node.value)


def exempt(sentence: Sentence) -> str | None:
    """Why this sentence may use the words, or None when it may not."""
    if sentence.module in OUTSIDE_MODULES:
        return OUTSIDE_MODULES[sentence.module]
    for (module, start), reason in OUTSIDE_SENTENCES.items():
        if sentence.module == module and sentence.text.startswith(start):
            return reason
    if sentence.module.startswith(MUSEUM_MODULES):
        # A museum's collection is a collection; its catalogue or its playlist is still not the Library's.
        words = {match.group(1).lower() for match in REFUSED_WORDS.finditer(sentence.text)}
        if words <= {"collection", "collections"}:
            return "a museum speaks of its own collection"
    return None


def said(found: list[Sentence]) -> list[Sentence]:
    """The sentences that use a refused word and have no reason to."""
    return [sentence for sentence in found if REFUSED_WORDS.search(sentence.text) and exempt(sentence) is None]


SENTENCES = list(sentences())


def _planted(tmp_path: Path, source: str, name: str = "planted.py") -> list[Sentence]:
    planted = tmp_path / name
    planted.write_text(source, encoding="utf-8")
    return list(sentences({planted: ast.parse(source)}, root=tmp_path))


def test_the_sentences_are_read_from_every_module_and_every_kind_of_literal():
    """The anchor: a plain literal and an f-string's part are read, and the glob found a tree."""
    texts = {sentence.text for sentence in SENTENCES}
    assert "The Library was last backed up " in texts, "the literal part of an f-string"
    assert "The Library has never been backed up" in texts, "a plain literal passed to a constructor"
    assert any(sentence.module == "programming/reports.py" for sentence in SENTENCES)
    assert len({sentence.module for sentence in SENTENCES}) > 100, "the glob found a tree, not a file"


def test_documentation_and_a_loggers_arguments_are_not_read_and_a_returned_sentence_is(tmp_path):
    """The three kinds of string, one module: only the returned sentence is a sentence a person reads."""
    source = (
        '"""The catalogue is documented here, in the docstring."""\n'
        "import logging\n"
        "log = logging.getLogger(__name__)\n"
        "def f():\n"
        '    """The catalogue is documented here too."""\n'
        '    log.warning("the catalogue backup failed: %s", 1, extra={"event": "the catalogue went wrong"})\n'
        '    return "The catalogue has never been backed up"\n'
    )
    found = _planted(tmp_path, source)
    assert [sentence.text for sentence in found] == ["The catalogue has never been backed up"]
    assert [sentence.site for sentence in said(found)] == ["planted.py:7"]


#: The five sentences at the wording they had when this chunk began, each in the shape it was built in.
FIVE_AS_THEY_WERE = {
    "reports": 'def f():\n    return "No wall is in the catalogue, so there is nothing for a Player to report about."\n',
    "near-miss": (
        'def f(names):\n    return (f"A new artist was recorded, and the catalogue already holds {names}. They may be "\n'
        '        "the same painter under different spellings.")\n'
    ),
    "trouble": 'def f():\n    return [Trouble(TroubleKind.BACKUP, None, None, "The catalogue has never been backed up")]\n',
    "panel": 'def f(self):\n    return f"The catalogue was last backed up {self.ago}."\n',
    "pause": (
        "def f(check):\n    raise NotEnoughSpace(\n"
        '        f"{check.free} free ({check.short} short); acquisition would risk the catalogue on the same disk."\n    )\n'
    ),
}


@pytest.mark.parametrize("name", sorted(FIVE_AS_THEY_WERE))
def test_each_of_the_five_sentences_at_its_old_wording_is_named(name, tmp_path):
    assert len(said(_planted(tmp_path, FIVE_AS_THEY_WERE[name]))) == 1


def test_a_sentence_planted_in_a_module_the_guard_had_not_seen_is_named(tmp_path):
    """A new module, a new path, a sentence built by a function nothing here names: still read."""
    found = _planted(tmp_path, 'class Brand:\n    def blurb(self):\n        return "Your playlist is ready."\n', "brand_new.py")
    assert [sentence.site for sentence in said(found)] == ["brand_new.py:3"]


def test_a_sentence_assembled_from_parts_is_the_one_thing_it_does_not_see(tmp_path):
    """Said out loud, so the limit is a fact the suite holds and not a hope: a joined or concatenated word is invisible."""
    source = (
        "def f():\n"
        '    return "The cata" + "logue is empty"\n'
        "def g():\n"
        '    return " ".join(["The", "catalogue", "is", "empty"])\n'
    )
    assert said(_planted(tmp_path, source)) == []


@pytest.mark.parametrize("sentence", said(SENTENCES) or [None], ids=lambda sentence: getattr(sentence, "site", "none"))
def test_no_sentence_a_person_reads_names_the_catalogue_a_collection_or_a_playlist(sentence):
    """Parametrised over the sentences that say one, so each is named by its site; `None` alone is the pass."""
    assert sentence is None, f"{sentence.site} says: {sentence.text}"


def test_every_exemption_still_exempts_something():
    """A reason that no longer matches a sentence is deleted, not kept: a stale one would excuse the next."""
    said_words = [sentence for sentence in SENTENCES if REFUSED_WORDS.search(sentence.text)]
    for module in OUTSIDE_MODULES:
        assert any(sentence.module == module for sentence in said_words), f"{module} no longer says a refused word"
    for module, start in OUTSIDE_SENTENCES:
        assert any(
            sentence.module == module and sentence.text.startswith(start) for sentence in said_words
        ), f"{module} no longer says {start!r}"
    assert any(sentence.module.startswith(MUSEUM_MODULES) for sentence in said_words), "no museum says collection"


def test_a_start_up_module_reaches_no_person():
    """How the guard knows `START_UP_MODULES`' refusals reach the terminal and no screen.

    No refusal of the `ServiceError` family (which `/api` renders) is built in one of them, and no
    exception class one defines is named in any other module of the source, so nothing catches it
    and carries its text to a screen. `NotEnoughSpace` is the counter-example: a `RuntimeError`
    too, but the fetch queue names it and stores its text as the pause's detail, so it is read.
    """
    modules = _parsed()
    start_up = set(START_UP_MODULES)
    built_here = {refusal.site.split(":")[0] for refusal in ALL}
    assert built_here.isdisjoint(start_up), built_here & start_up
    for path, tree in modules.items():
        module = _module(path, SRC)
        if module not in start_up:
            continue
        raised_classes = (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            and any(isinstance(base, ast.Name) and base.id in {"Exception", "RuntimeError"} for base in node.bases)
        )
        for cls in raised_classes:
            for other, other_tree in modules.items():
                if _module(other, SRC) == module:
                    continue
                named = {
                    each.id if isinstance(each, ast.Name) else each.attr
                    for each in ast.walk(other_tree)
                    if isinstance(each, (ast.Name, ast.Attribute))
                } | {alias.name for each in ast.walk(other_tree) if isinstance(each, ast.ImportFrom) for alias in each.names}
                assert cls.name not in named, f"{_module(other, SRC)} names {cls.name}, which {module} raises at start-up"


# -- a Get is a Get wherever a person reads it -----------------------------------
#
# The owner's ruling of 2026-11-25 (3): MCP keeps "run" in its names (`run_id`, `list_runs`, the
# action names), and a sentence the server writes that reaches a screen, or a refusal an agent
# relays to a person, says "Get". The browser calls a first-time search, a re-search and a Get by
# one word, and a refusal reading "No discovery run with id …" was the one place a person met the
# other.
#
# What it reads: every refusal the source builds, in any module (`ALL`), and every prose string in
# the two modules that write a Get's own sentences (`GET_MODULES`).
#
# What it reads for: "run" used as the noun for a Get, in the forms a Get's sentence takes
# ("a run", "this run's", "discovery run", "Run '…'", "run in …"). A verb is not read ("nothing
# runs with nobody watching", "cannot run in this deployment"), and neither is a Watch's own
# "Last run finished".
#
# What it does not read, and says so: a sentence about a Get built in another module. The status
# notices and the tool descriptions in `mcp/bindings.py` and `mcp/tools.py` still say "this run"
# for a Get, and the Watches' sentences say "run" for a Watch's pass; neither is in this guard's
# reach, and the guard cannot see a sentence assembled from parts.

RUN_FOR_A_GET = re.compile(
    r"\b(?:(?:discovery|resolve) runs?\b"
    r"|(?:this|the|a|an|one|that|its|each|every|no|originating) runs?\b"
    r"|Run (?:\{|')"
    r"|runs? in \{)",
    re.IGNORECASE,
)

#: The modules whose every sentence is read for it: where a Get's own sentences are written.
GET_MODULES = ("library/services/discovery.py", "library/services/runner.py")


def run_for_a_get(found: list[Sentence]) -> list[Sentence]:
    """The sentences that call a Get a run."""
    return [sentence for sentence in found if RUN_FOR_A_GET.search(sentence.text)]


@pytest.mark.parametrize("refusal", [refusal for refusal in ALL if RUN_FOR_A_GET.search(refusal.text)] or [None], ids=str)
def test_no_refusal_calls_a_get_a_run(refusal):
    """Parametrised over the refusals that do, so each is named; `None` alone is the pass."""
    assert refusal is None, f"{refusal.site} ({refusal.raised_as}) says: {refusal.text}"


@pytest.mark.parametrize(
    "sentence",
    run_for_a_get([each for each in SENTENCES if each.module in GET_MODULES]) or [None],
    ids=lambda sentence: getattr(sentence, "site", "none"),
)
def test_no_sentence_in_the_modules_that_write_a_gets_calls_it_a_run(sentence):
    assert sentence is None, f"{sentence.site} says: {sentence.text}"


def _refusals_in(source: str, tmp_path: Path) -> list[Refusal]:
    planted_module = tmp_path / "planted.py"
    planted_module.write_text(source, encoding="utf-8")
    return list(refusals({planted_module: ast.parse(source)}, root=tmp_path))


@pytest.mark.parametrize(
    "planted",
    [
        'raise NotFound(f"No discovery run with id {run_id!r} exists.")',
        'raise ServiceError(f"Run {run_id!r} is {status}, so it cannot cancel.")',
        "raise ServiceError(f\"Run '{run_id}' ended.\")",
        'raise ServiceError("A resolve run needs at least one candidate work.")',
        'raise ServiceError(f"{doing} needs a run in {expected}.")',
        'raise ServiceError("Start one per originating run.")',
        'raise ServiceError("Nothing here: this run\'s works are off.")',
    ],
)
def test_a_planted_refusal_calling_a_get_a_run_is_named(planted, tmp_path):
    found = _refusals_in(f"def f(run_id, status, doing, expected):\n    {planted}\n", tmp_path)
    assert [refusal.site for refusal in found if RUN_FOR_A_GET.search(refusal.text)] == ["planted.py:2"]


@pytest.mark.parametrize(
    "innocent",
    [
        'raise ServiceError("Unattended work is off, so nothing runs with nobody watching.")',
        'raise ServiceError("Tiled acquisition cannot run in this deployment.")',
        'raise ServiceError(f"No Get with id {run_id!r} exists.")',
        'raise ServiceError("Last run finished; what it found is in To review.")',
        'raise ServiceError(f"Get {run_id!r} is {status}, so it cannot cancel; that needs a Get in {expected}.")',
    ],
)
def test_what_does_not_call_a_get_a_run_is_not_named(innocent, tmp_path):
    found = _refusals_in(f"def f(run_id, status, doing, expected):\n    {innocent}\n", tmp_path)
    assert [refusal.site for refusal in found if RUN_FOR_A_GET.search(refusal.text)] == []


def test_the_get_modules_are_modules_that_say_something_a_person_reads():
    """Falsifiable: each is read, and each says a Get somewhere, so an empty list is not a blind guard."""
    assert {sentence.module for sentence in SENTENCES} >= set(GET_MODULES)
    for module in GET_MODULES:
        assert any(sentence.module == module and "Get" in sentence.text for sentence in SENTENCES), module
