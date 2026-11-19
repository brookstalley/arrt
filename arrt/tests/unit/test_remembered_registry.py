"""One Wikidata answer per work: the registry the plugins and phase 2 are handed remembers each item's pages.

Every finder asks `pages_about` for the same item at the same moment, so a bare
registry sent the query service one identical query per finder for every Get.
"""

import inspect
import threading
from types import SimpleNamespace

import pytest
from fakes import FakeRegistry

from arrt.__main__ import _registry
from arrt.library.registry import Registry, RegistryUnavailable
from arrt.library.registry.remembering import PAGES_REMEMBERED_SECONDS, RememberingRegistry
from arrt.library.registry.wikidata import WikidataRegistry

ITEM = "Q5308687"
PAGE = "https://www.moma.org/collection/works/80249"
#: The finders that ask `pages_about` in one Get: 18 plugin modules and phase 2 (audit-4 finding 2).
ASKERS = 19
SETTLE = 10.0


class Clock:
    def __init__(self) -> None:
        self.at = 1000.0

    def __call__(self) -> float:
        return self.at


class Slow(FakeRegistry):
    """A registry whose `pages_about` waits at a gate, so callers asking together overlap."""

    def __init__(self, **tables) -> None:
        super().__init__(**tables)
        self.gate = threading.Event()

    def pages_about(self, qid):
        assert self.gate.wait(SETTLE), "the test never opened the gate"
        return super().pages_about(qid)


def ask_together(registry: Registry, count: int, opened: threading.Event) -> list[object]:
    """`count` threads asking `pages_about` for one item at once; what each got, a list or what it raised."""
    start = threading.Barrier(count + 1, timeout=SETTLE)
    got: list[object] = [None] * count

    def one(index: int) -> None:
        start.wait()
        try:
            got[index] = registry.pages_about(ITEM)
        except Exception as exc:  # noqa: BLE001 -- what it raised is what the test reads
            got[index] = exc

    threads = [threading.Thread(target=one, args=(index,), daemon=True) for index in range(count)]
    for thread in threads:
        thread.start()
    start.wait()
    # Every asker is past the barrier and inside `pages_about` well before this;
    # the first holds the request at the gate while the rest arrive.
    threading.Timer(0.3, opened.set).start()
    for thread in threads:
        thread.join(SETTLE)
    return got


def test_nineteen_finders_asking_for_one_item_at_once_cause_one_request():
    inner = Slow(pages={ITEM: [PAGE]})

    got = ask_together(RememberingRegistry(inner), ASKERS, inner.gate)

    assert inner.pages_asked == [ITEM]
    assert got == [[PAGE]] * ASKERS


def test_an_item_is_remembered_for_ten_minutes_and_asked_again_after():
    clock = Clock()
    inner = FakeRegistry(pages={ITEM: [PAGE]})
    registry = RememberingRegistry(inner, clock=clock)

    assert registry.pages_about(ITEM) == [PAGE]
    clock.at += PAGES_REMEMBERED_SECONDS - 1
    assert registry.pages_about(ITEM) == [PAGE]
    assert inner.pages_asked == [ITEM], "asked again inside ten minutes"

    clock.at += 1
    assert registry.pages_about(ITEM) == [PAGE]
    assert inner.pages_asked == [ITEM, ITEM], "not asked again after ten minutes"
    assert PAGES_REMEMBERED_SECONDS == 600


def test_an_item_with_no_pages_is_remembered_too_and_each_item_on_its_own():
    inner = FakeRegistry(pages={ITEM: [PAGE]})
    registry = RememberingRegistry(inner)

    assert registry.pages_about("Q1") == []
    assert registry.pages_about("Q1") == []
    assert registry.pages_about(ITEM) == [PAGE]
    assert inner.pages_asked == ["Q1", ITEM]


def test_a_caller_changing_its_answer_changes_nobody_elses():
    registry = RememberingRegistry(FakeRegistry(pages={ITEM: [PAGE]}))

    registry.pages_about(ITEM).append("https://example.org/mine")

    assert registry.pages_about(ITEM) == [PAGE]


def test_a_failure_is_shared_by_the_callers_waiting_on_it_and_never_remembered():
    class Down(Slow):
        def pages_about(self, qid):
            self.pages_asked.append(qid)
            assert self.gate.wait(SETTLE)
            raise RegistryUnavailable("the query service refused")

    inner = Down()
    registry = RememberingRegistry(inner)

    got = ask_together(registry, 5, inner.gate)

    assert inner.pages_asked == [ITEM]
    assert all(isinstance(each, RegistryUnavailable) for each in got), got
    inner.gate.set()
    with pytest.raises(RegistryUnavailable):
        registry.pages_about(ITEM)
    assert inner.pages_asked == [ITEM, ITEM], "the outage was remembered as an answer"


def test_a_caller_waiting_on_another_s_request_gives_up_at_its_bound_as_could_not_be_asked():
    inner = Slow(pages={ITEM: [PAGE]})
    registry = RememberingRegistry(inner, shared_wait=0.1)
    first = threading.Thread(target=registry.pages_about, args=(ITEM,), daemon=True)
    first.start()
    try:
        # Until the first is inside the inner registry, a second ask would be first itself.
        until_asked = threading.Event()
        while not until_asked.wait(0.01):
            if registry._asking:
                until_asked.set()
        with pytest.raises(RegistryUnavailable, match="did not answer another caller's question"):
            registry.pages_about(ITEM)
    finally:
        inner.gate.set()
        first.join(SETTLE)


def _questions() -> list[str]:
    """Every question the `Registry` protocol asks, read from it, so a question added later is held here too."""
    return sorted(name for name in vars(Registry) if not name.startswith("_") and callable(getattr(Registry, name)))


def test_the_questions_are_read_from_the_protocol():
    assert "pages_about" in _questions()
    assert "creator_names" in _questions()
    assert len(_questions()) >= 17


@pytest.mark.parametrize("question", [q for q in _questions() if q != "pages_about"])
def test_every_other_question_reaches_the_registry_underneath_unchanged(question):
    asked: list[tuple[str, tuple, dict]] = []
    answer = object()

    class Recording:
        def __getattr__(self, name):
            def call(*args, **kwargs):
                asked.append((name, args, kwargs))
                return answer

            return call

    registry = RememberingRegistry(Recording())  # type: ignore[arg-type]
    method = getattr(RememberingRegistry, question)
    assert method is not getattr(Registry, question), f"{question} is not RememberingRegistry's own"

    parameters = list(inspect.signature(getattr(Registry, question)).parameters.values())[1:]
    args = [f"positional-{p.name}" for p in parameters if p.kind is p.POSITIONAL_OR_KEYWORD and p.default is p.empty]
    kwargs = {p.name: f"keyword-{p.name}" for p in parameters if p.kind is p.KEYWORD_ONLY}

    assert getattr(registry, question)(*args, **kwargs) is answer
    assert asked == [(question, tuple(args), kwargs)]


def test_the_wiring_hands_the_plugins_and_phase_two_wikidata_remembering_its_pages():
    registry = _registry(SimpleNamespace(wikidata_user_agent="arrt-tests/0 (+https://example.org)"))

    assert isinstance(registry, RememberingRegistry)
    assert isinstance(registry.inner, WikidataRegistry)
    assert _registry(SimpleNamespace(wikidata_user_agent="")) is None
