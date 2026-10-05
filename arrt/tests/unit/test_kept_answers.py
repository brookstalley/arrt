"""Answers kept on disk: fresh or a miss, bounded, apart by namespace, and never an error.

The store is general purpose: these tests keep plain values and small
dataclasses of their own, and the registry's answer types appear only where the
codec is held to round-trip every one of them.
"""

import dataclasses
import enum
import json
import logging
import sqlite3
import types
import typing
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta

import pytest

import arrt.library.registry as seam
from arrt.persistence.kept import FORMAT, JsonCodec, KeptAnswers

DAY = timedelta(days=1)


class Clock:
    """A clock a test moves by hand, in seconds."""

    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


@dataclass(frozen=True, slots=True)
class Answer:
    name: str
    count: int = 0


#: `Answer` as a later version might declare it: one field more.
@dataclass(frozen=True, slots=True)
class AnswerWithMore:
    name: str
    count: int = 0
    more: int = 0


class Text:
    """A codec that keeps strings as themselves."""

    def encode(self, value):
        return value

    def decode(self, text):
        return text


def _events(caplog):
    """The store's own events since the last `caplog.clear()`.

    Cleared before each block rather than read whole: a test earlier in the
    worker may have set the root logger to INFO, and then the `kept.opened` of
    an open made before the block is captured too.
    """
    return [record.event for record in caplog.records if record.name == "arrt.persistence.kept"]


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def path(tmp_path):
    return tmp_path / "kept-answers.sqlite"


def _open(path, clock, *, name="answers", codec=None, max_age=DAY, size=10):
    answers = KeptAnswers(path, clock=clock)
    return answers, answers.namespace(name, codec=codec or JsonCodec(Answer), max_age=max_age, size=size)


# -- across restarts ---------------------------------------------------------


def test_an_answer_survives_a_restart(path, clock):
    answers, kept = _open(path, clock)
    kept.put(("Q1", ("Q2", "Q3")), Answer("Bruegel", 3))
    answers.close()

    _, reopened = _open(path, clock)

    assert reopened.get(("Q1", ("Q2", "Q3"))) == Answer("Bruegel", 3)
    assert reopened.get(("Q1", ("Q2",))) is None


def test_the_order_of_use_carries_across_a_restart(path, clock):
    """Two hops: the counter a restart resumes from must be above every use before it.

    Started again from nothing, a new answer would rank below the old ones and
    be the first thrown away.
    """
    answers, kept = _open(path, clock, size=2)
    kept.put("a", Answer("a"))
    kept.put("b", Answer("b"))
    assert kept.get("a") == Answer("a")  # b is now the least recently used
    answers.close()

    _, reopened = _open(path, clock, size=2)
    reopened.put("c", Answer("c"))
    reopened.put("d", Answer("d"))

    assert [reopened.get(key) for key in "abcd"] == [None, None, Answer("c"), Answer("d")]


# -- age ---------------------------------------------------------------------


def test_an_answer_is_fresh_until_its_maximum_age_and_a_miss_from_then(path, clock):
    _, kept = _open(path, clock, max_age=timedelta(days=7))
    kept.put("k", Answer("x"))

    clock.now += timedelta(days=7).total_seconds() - 1
    assert kept.get("k") == Answer("x")

    clock.now += 1
    assert kept.get("k") is None


def test_an_expired_answer_stays_a_miss_when_the_clock_comes_back(path, clock):
    """An expired entry is thrown away when found, not merely not served."""
    _, kept = _open(path, clock)
    kept.put("k", Answer("x"))
    clock.now += DAY.total_seconds() + 13
    assert kept.get("k") is None

    clock.now -= DAY.total_seconds()

    assert kept.get("k") is None


def test_an_answer_from_the_future_is_a_miss(path, clock):
    """A clock that went back would otherwise keep an answer fresh for however far it went."""
    _, kept = _open(path, clock)
    kept.put("k", Answer("x"))

    clock.now -= 7

    assert kept.get("k") is None


def test_the_age_is_read_against_the_maximum_the_namespace_sets_now(path, clock):
    answers, kept = _open(path, clock, max_age=timedelta(days=7))
    kept.put("k", Answer("x"))
    answers.close()
    clock.now += timedelta(days=2).total_seconds()

    _, shorter = _open(path, clock, max_age=DAY)

    assert shorter.get("k") is None


def test_a_namespace_nobody_registers_is_thrown_away_once_its_answers_expire(path, clock):
    answers, gone = _open(path, clock, name="gone", max_age=DAY)
    gone.put("k", Answer("x"))
    answers.close()
    clock.now += DAY.total_seconds() + 5

    KeptAnswers(path, clock=clock).close()

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM answers").fetchone()[0] == 0


# -- the bound -----------------------------------------------------------------


def test_the_bound_throws_away_the_least_recently_used_first(path, clock):
    _, kept = _open(path, clock, size=2)
    kept.put("a", Answer("a"))
    kept.put("b", Answer("b"))
    assert kept.get("a") == Answer("a")  # now the most recent

    kept.put("c", Answer("c"))

    assert [kept.get(key) for key in "abc"] == [Answer("a"), None, Answer("c")]


def test_putting_a_key_again_replaces_it_and_makes_it_recent(path, clock):
    _, kept = _open(path, clock, size=2)
    kept.put("a", Answer("a"))
    kept.put("b", Answer("b"))
    kept.put("a", Answer("a", 10))

    kept.put("c", Answer("c"))

    assert [kept.get(key) for key in "abc"] == [Answer("a", 10), None, Answer("c")]


def test_an_expired_answer_goes_before_a_fresh_one_used_longer_ago(path, clock):
    _, kept = _open(path, clock, size=2, max_age=DAY)
    kept.put("old", Answer("old"))
    clock.now += 0.75 * DAY.total_seconds()
    kept.put("fresh", Answer("fresh"))
    clock.now += 0.15 * DAY.total_seconds()
    assert kept.get("old") == Answer("old")  # now the most recently used
    clock.now += 0.35 * DAY.total_seconds()  # and expired; "fresh" is not

    kept.put("new", Answer("new"))

    with sqlite3.connect(path) as connection:
        keys = {row[0] for row in connection.execute("SELECT key FROM answers")}
    assert keys == {'"fresh"', '"new"'}


def test_each_namespace_is_bounded_by_its_own_size(path, clock):
    """A burst of one namespace (typing a search) must not throw away another's (an artist's page)."""
    answers = KeptAnswers(path, clock=clock)
    pages = answers.namespace("pages", codec=Text(), max_age=DAY, size=2)
    searches = answers.namespace("searches", codec=Text(), max_age=DAY, size=2)
    pages.put("p", "page")

    for n in range(5):
        searches.put(f"s{n}", "found")

    assert pages.get("p") == "page"


# -- namespaces --------------------------------------------------------------


def test_two_namespaces_with_the_same_key_do_not_collide(path, clock):
    answers = KeptAnswers(path, clock=clock)
    artists = answers.namespace("artists", codec=Text(), max_age=DAY, size=10)
    works = answers.namespace("works", codec=Text(), max_age=DAY, size=10)

    artists.put("Q1", "an artist")
    works.put("Q1", "a work")

    assert (artists.get("Q1"), works.get("Q1")) == ("an artist", "a work")


def test_a_name_is_registered_once_per_file(path, clock):
    answers = KeptAnswers(path, clock=clock)
    answers.namespace("artists", codec=Text(), max_age=DAY, size=10)

    with pytest.raises(ValueError, match="already registered"):
        answers.namespace("artists", codec=Text(), max_age=DAY, size=10)


@pytest.mark.parametrize(("max_age", "size"), [(timedelta(0), 1), (DAY, 0)])
def test_a_namespace_must_keep_something_for_some_time(path, clock, max_age, size):
    with pytest.raises(ValueError, match="at least one answer for some time"):
        KeptAnswers(path, clock=clock).namespace("n", codec=Text(), max_age=max_age, size=size)


# -- what cannot be read is a miss -----------------------------------------------


def test_an_entry_of_a_changed_shape_is_a_miss_and_is_dropped(path, clock, caplog):
    answers, old = _open(path, clock, codec=JsonCodec(Answer))
    old.put("k", Answer("x", 2))
    answers.close()

    _, new = _open(path, clock, codec=JsonCodec(AnswerWithMore))
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="arrt.persistence.kept"):
        assert new.get("k") is None

    assert _events(caplog) == ["kept.unreadable"]
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM answers").fetchone()[0] == 0


def test_an_entry_that_is_not_json_is_a_miss(path, clock):
    _, kept = _open(path, clock)
    kept.put("k", Answer("x"))
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE answers SET value = 'not json {'")

    assert kept.get("k") is None


def test_a_value_the_codec_cannot_write_is_not_kept_and_raises_nothing(path, clock, caplog):
    _, kept = _open(path, clock, codec=JsonCodec(Answer))

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="arrt.persistence.kept"):
        kept.put("k", "not an Answer")

    assert kept.get("k") is None
    assert _events(caplog) == ["kept.unwritable"]


def test_a_file_the_disk_will_not_serve_is_a_miss_and_raises_nothing(path, clock, caplog):
    answers, kept = _open(path, clock)
    kept.put("k", Answer("x"))
    answers.close()

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="arrt.persistence.kept"):
        assert kept.get("k") is None
        kept.put("k", Answer("y"))

    assert _events(caplog) == ["kept.failed", "kept.failed"]


# -- the file ----------------------------------------------------------------


def test_a_file_that_is_not_a_database_is_replaced(path, clock, caplog):
    path.write_bytes(b"this is not a database, and is longer than a header" * 20)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="arrt.persistence.kept"):
        _, kept = _open(path, clock)
    kept.put("k", Answer("x"))

    assert kept.get("k") == Answer("x")
    assert _events(caplog) == ["kept.replaced"]


def test_a_file_of_another_format_is_replaced(path, clock, caplog):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE answers (whatever TEXT)")
        connection.execute(f"PRAGMA user_version = {FORMAT + 1}")

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="arrt.persistence.kept"):
        _, kept = _open(path, clock)
    kept.put("k", Answer("x"))

    assert kept.get("k") == Answer("x")
    assert _events(caplog) == ["kept.replaced"]


def test_a_file_of_this_format_is_not_replaced(path, clock, caplog):
    answers, kept = _open(path, clock)
    kept.put("k", Answer("x"))
    answers.close()

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="arrt.persistence.kept"):
        _, reopened = _open(path, clock)

    assert reopened.get("k") == Answer("x")
    assert _events(caplog) == []


# -- the codec -----------------------------------------------------------------


class Kind(enum.Enum):
    ONE = "one"
    TWO = "two"


@dataclass(frozen=True, slots=True)
class Shaped:
    kind: Kind
    flag: bool
    count: int
    ratio: float
    optional: str | None
    many: tuple[int, ...]


def _shaped(**changes):
    return dataclasses.replace(Shaped(kind=Kind.TWO, flag=True, count=3, ratio=0.5, optional=None, many=(1, 2)), **changes)


@pytest.mark.parametrize(
    ("field", "stored"),
    [
        ("kind", "three"),  # an enum member that no longer exists
        ("flag", 1),  # a number where a flag belongs
        ("count", True),  # a flag where a number belongs
        ("count", "3"),
        ("optional", 4),
        ("many", "12"),
        ("many", [1, None]),
    ],
)
def test_the_codec_reads_a_value_of_another_type_as_unreadable(field, stored):
    data = json.loads(JsonCodec(Shaped).encode(_shaped()))
    data[field] = stored

    with pytest.raises((TypeError, ValueError)):
        JsonCodec(Shaped).decode(json.dumps(data))


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_the_codec_reads_a_dataclass_with_other_fields_as_unreadable(change):
    data = json.loads(JsonCodec(Shaped).encode(_shaped()))
    if change == "missing":
        del data["ratio"]
    else:
        data["added"] = 1

    with pytest.raises(TypeError):
        JsonCodec(Shaped).decode(json.dumps(data))


def test_the_codec_refuses_a_shape_it_cannot_keep_where_it_is_made():
    @dataclass(frozen=True)
    class WithBytes:
        raw: bytes

    with pytest.raises(TypeError):
        JsonCodec(WithBytes)


def test_an_int_is_a_float_on_the_way_back():
    assert JsonCodec(Shaped).decode(JsonCodec(Shaped).encode(_shaped(ratio=2))).ratio == 2.0


# -- every registry answer, round trip ---------------------------------------------


def _seam_dataclasses() -> list[type]:
    return [
        member
        for member in vars(seam).values()
        if isinstance(member, type) and dataclasses.is_dataclass(member) and member.__module__ == seam.__name__
    ]


def _filled(shape, depth=0):  # noqa: C901, PLR0911 -- one branch per kind of type form the codec accepts
    """A value of `shape` with nothing left at a default: every optional set, every sequence two long."""
    while isinstance(shape, typing.NewType):
        shape = shape.__supertype__
    origin, args = typing.get_origin(shape), typing.get_args(shape)
    if origin is typing.Union or origin is types.UnionType:
        return _filled(next(arg for arg in args if arg is not type(None)), depth)
    if shape is str:
        return f"text {depth}"
    if shape is bool:
        return True
    if shape is int:
        return 7 + depth
    if shape is float:
        return 0.5
    if isinstance(shape, type) and issubclass(shape, enum.Enum):
        return list(shape)[-1]
    if isinstance(shape, type) and dataclasses.is_dataclass(shape):
        hints = typing.get_type_hints(shape)
        return shape(**{f.name: _filled(hints[f.name], depth + 1) for f in dataclasses.fields(shape)})
    if origin in (tuple, Sequence, list):
        return tuple(_filled(args[0], depth + n) for n in range(2))
    if origin in (dict, Mapping):
        return {f"Q{depth + n}": _filled(args[1], depth + n) for n in range(2)}
    raise AssertionError(f"no filler for {shape!r}")


def test_every_registry_type_is_found():
    """The vacuity check: a round trip over nothing passes."""
    assert {seam.RegistryArtist, seam.RegistryWork, seam.RegistrySimilar, seam.RegistryTopic} <= set(_seam_dataclasses())


@pytest.mark.parametrize("shape", _seam_dataclasses(), ids=lambda shape: shape.__name__)
def test_every_registry_answer_comes_back_as_it_went(path, clock, shape):
    value = _filled(shape)
    defaulted = [f.name for f in dataclasses.fields(shape) if getattr(value, f.name) == f.default]
    assert defaulted == [], f"the filler left {defaulted} at their defaults, which a dropped field would also read back as"
    answers, kept = _open(path, clock, codec=JsonCodec(shape))
    kept.put("k", value)
    answers.close()

    _, reopened = _open(path, clock, codec=JsonCodec(shape))

    assert reopened.get("k") == value
