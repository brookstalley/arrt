"""Every string a registry hands the Library says what it is (`security-model.md` § Direction).

Registry text reaches the browser as words; only a Commons file may become a URL
there. A work page is a URL too, which the server keeps and never sends there. The
client and the page keep those apart by the field's type, so the two tests here
hold the types:

- **every string on the seam's types, and in every question's answer, is one of the
  named kinds**, so a new field or return cannot arrive as a plain `str` that
  nobody decided about; and
- **a registry answering every question with a stranger's URL** puts it in no
  Commons file, no item id and no identifier key, so the client's checks cannot be
  skipped by a new query. It can make a stranger's URL a work page, which is why
  a work page reaches no response (`tests/integration/test_sightings_api.py`).

Both are derived from the seam itself, the dataclasses it defines and the methods
`Registry` declares, so a new type or question is covered by existing, and a new
question with no stated call fails by name.
"""

import dataclasses
import inspect
import re
import types
import typing

import httpx
import pytest

import arrt.library.registry as seam
from arrt.library.registry import (
    QID,
    CommonsFile,
    ItemId,
    MuseumIdentifier,
    Registry,
    RegistryText,
    RegistryTopic,
    TopicKind,
    WorkPage,
)
from arrt.library.registry.identifiers import IdentifierScheme
from arrt.library.registry.wikidata import WikidataRegistry

#: The named kinds a registry string may be: every `NewType` the seam defines, so
#: a new kind is one the checks below name, rather than one they skip.
KINDS = {member for member in vars(seam).values() if isinstance(member, typing.NewType)}

#: A URL the registry might return where an image or a link belongs. It ends in an
#: item nobody asked about, so a question that keeps unasked items shows it.
STRANGER = "https://evil.example/entity/Q666"

#: The one host an image may come from.
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/"

#: One call per question the seam declares, with arguments that reach every query
#: the question makes (`include` is outside the most renowned, so its query runs).
ASKED = "1"

#: A topic as a caller hands it back: the registry's own answer to `topic`.
_A_SUBJECT = RegistryTopic(qid=ItemId("Q1"), label=RegistryText("winter"), kinds=(TopicKind.SUBJECT,))

CALLS = {
    "works_by_identifier": lambda registry: registry.works_by_identifier(IdentifierScheme.ARTIC, [ASKED]),
    "creators_of": lambda registry: registry.creators_of(["Q1"]),
    "people_named": lambda registry: registry.people_named("anyone"),
    "artist": lambda registry: registry.artist("Q1", works=5, holdings=5, include=["Q2"]),
    "work": lambda registry: registry.work("Q1"),
    "works_matching": lambda registry: registry.works_matching(["any"], prefix=True, limit=5),
    "similar_to": lambda registry: registry.similar_to("Q1", limit=5),
    "label_of": lambda registry: registry.label_of("Q1"),
    "topic": lambda registry: registry.topic("Q1"),
    # A subject reaches both of a topic's queries, the works' and their makers'.
    "topic_works": lambda registry: registry.topic_works(_A_SUBJECT, limit=5),
    "topic_artists": lambda registry: registry.topic_artists(_A_SUBJECT, limit=5),
    "topics_named": lambda registry: registry.topics_named("anything"),
    "topics_of": lambda registry: registry.topics_of(["Q1"], ["Q2"]),
    "pages_about": lambda registry: registry.pages_about("Q1"),
    "creator_names": lambda registry: registry.creator_names("Q1"),
    "image_size": lambda registry: registry.image_size(CommonsFile(f"{COMMONS}A.jpg")),
}

#: Questions whose answer can hold no string at all, so a hostile answer has
#: nothing to put in one and the hostile test below would check nothing. Held to
#: that by `test_an_answer_that_can_hold_no_string_has_no_string_field`, which
#: fails the day one gains a field that could carry one.
NO_STRINGS = {"image_size"}


def _seam_types() -> list[type]:
    return [
        member
        for _, member in inspect.getmembers(seam, inspect.isclass)
        if dataclasses.is_dataclass(member) and member.__module__ == seam.__name__
    ]


def _questions() -> set[str]:
    return {name for name, member in vars(Registry).items() if inspect.isfunction(member) and not name.startswith("_")}


def _plain_strings(annotation: object) -> bool:
    """Whether `annotation` lets a plain `str` through anywhere inside it."""
    if annotation is str:
        return True
    if annotation in KINDS:
        return False
    return any(_plain_strings(argument) for argument in typing.get_args(annotation))


def _answer_type(question: str) -> object:
    return typing.get_type_hints(getattr(Registry, question))["return"]


def test_the_seam_has_types_and_questions_to_check():
    """A rename that emptied either list would leave the tests below passing on nothing."""
    assert {ItemId, RegistryText, CommonsFile, MuseumIdentifier, WorkPage} == KINDS
    assert {kind.__name__ for kind in _seam_types()} >= {"RegistryArtist", "RegistryWorkEntry"}
    assert "artist" in _questions()


@pytest.mark.parametrize("kind", _seam_types(), ids=lambda kind: kind.__name__)
def test_every_registry_string_says_what_it_is(kind):
    hints = typing.get_type_hints(kind)
    plain = [field.name for field in dataclasses.fields(kind) if _plain_strings(hints[field.name])]
    assert not plain, (
        f"{kind.__name__}.{', '.join(plain)} is a plain str. Type it as one of {sorted(k.__name__ for k in KINDS)} "
        "(security-model.md § Direction): only a CommonsFile may become a URL in the browser."
    )


@pytest.mark.parametrize("question", sorted(_questions()))
def test_every_answer_says_what_its_strings_are(question):
    assert not _plain_strings(_answer_type(question)), f"Registry.{question} returns a plain str somewhere."


def test_every_question_has_a_stated_call():
    assert set(CALLS) == _questions()


#: `VALUES ?name { first … }`: what a query asked about, by variable.
_VALUES = re.compile(r"VALUES\s+\?(\w+)\s*\{\s*(\S+)")


def _hostile(request: httpx.Request) -> httpx.Response:
    """A stranger's URL in every column, twice: once alone, and once beside what was asked.

    The second row echoes each `VALUES` variable's first value, as a real answer
    would, so a question that keeps only rows about what it asked still has one to
    keep, and the stranger's URL is in every other column of it.
    """
    query = httpx.QueryParams(request.content.decode())["query"]
    names = set(re.findall(r"\?(\w+)", query))
    alone = {name: {"type": "uri", "value": STRANGER} for name in names}
    echoed = dict(alone)
    for name, first in _VALUES.findall(query):
        echoed[name] = {"value": f"http://www.wikidata.org/entity/{first[3:]}" if first.startswith("wd:") else first.strip('"')}
    return httpx.Response(200, json={"results": {"bindings": [alone, echoed]}})


def _walk(value: object, kind: object, found: list[tuple[object, object]]) -> None:
    """Every (declared kind, string) pair inside a registry answer, typed from the top down."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        hints = typing.get_type_hints(type(value))
        for field in dataclasses.fields(value):
            _walk(getattr(value, field.name), hints[field.name], found)
    elif isinstance(value, typing.Mapping):
        key_kind, item_kind = _arguments(kind, 2)
        for key, item in value.items():
            _walk(key, key_kind, found)
            _walk(item, item_kind, found)
    elif isinstance(value, (tuple, list, frozenset, set)):
        (item_kind,) = _arguments(kind, 1)
        for item in value:
            _walk(item, item_kind, found)
    elif isinstance(value, str) or (value is None and _named(kind) is not None):
        found.append((_named(kind), value))


def _arguments(kind: object, count: int) -> list[object]:
    arguments = [argument for argument in typing.get_args(_unwrap(kind)) if argument is not Ellipsis]
    return arguments[:count] if len(arguments) >= count else [None] * count


def _unwrap(kind: object) -> object:
    """`X` from `X | None`."""
    if isinstance(kind, types.UnionType) or typing.get_origin(kind) is typing.Union:
        rest = [argument for argument in typing.get_args(kind) if argument is not type(None)]
        return rest[0] if len(rest) == 1 else kind
    return kind


def _named(kind: object) -> object:
    unwrapped = _unwrap(kind)
    return unwrapped if unwrapped in KINDS else None


def _answer(question: str) -> list[tuple[object, object]]:
    registry = WikidataRegistry(
        user_agent="arrt test (+https://example.org)",
        client=httpx.Client(transport=httpx.MockTransport(_hostile), follow_redirects=False),
    )
    found: list[tuple[object, object]] = []
    _walk(CALLS[question](registry), _answer_type(question), found)
    return found


def _can_hold_a_string(kind: object) -> bool:
    """Whether a value of `kind` could carry a string anywhere inside it, a dataclass's fields included."""
    kind = getattr(kind, "__supertype__", kind)
    if kind is str:
        return True
    if dataclasses.is_dataclass(kind):
        hints = typing.get_type_hints(kind)
        return any(_can_hold_a_string(hints[field.name]) for field in dataclasses.fields(kind))
    return any(_can_hold_a_string(argument) for argument in typing.get_args(kind))


@pytest.mark.parametrize("question", sorted(NO_STRINGS))
def test_an_answer_that_can_hold_no_string_has_no_string_field(question):
    assert not _can_hold_a_string(_answer_type(question)), f"Registry.{question} can now carry a string: check it below."


def test_the_string_check_sees_a_string_inside_a_dataclass():
    """`_can_hold_a_string` saying no about everything would exempt every question."""
    assert _can_hold_a_string(_answer_type("work"))


@pytest.mark.parametrize("question", sorted(set(CALLS) - NO_STRINGS))
def test_a_hostile_registry_reaches_no_image_id_or_key(question):
    found = _answer(question)

    assert found, f"Registry.{question} answered nothing, so this test checked nothing."
    assert not [value for kind, value in found if kind is None], "a string with no declared kind"
    assert all(value is None or value.startswith(COMMONS) for kind, value in found if kind is CommonsFile)
    assert all(QID.match(str(value)) for kind, value in found if kind is ItemId)
    assert all(value == ASKED for kind, value in found if kind is MuseumIdentifier)
    # Checked only as an address, because it never leaves the server.
    assert all(value.startswith(("https://", "http://")) for kind, value in found if kind is WorkPage)


def test_the_walk_reaches_an_image_field():
    """Every image is dropped under a hostile answer, so the image check above could pass on none."""
    found = _answer("artist")
    assert {kind for kind, _ in found} >= {CommonsFile, ItemId, RegistryText}


def test_an_identifier_the_registry_was_not_asked_about_is_not_a_key():
    assert {value for kind, value in _answer("works_by_identifier") if kind is MuseumIdentifier} == {ASKED}


def test_an_item_the_registry_was_not_asked_about_is_not_a_key():
    answer = CALLS["creators_of"](
        WikidataRegistry(
            user_agent="arrt test (+https://example.org)",
            client=httpx.Client(transport=httpx.MockTransport(_hostile), follow_redirects=False),
        )
    )
    assert set(answer) == {"Q1"}
