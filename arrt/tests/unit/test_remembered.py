"""The registry pages' shared memory: bounded, most recently used kept, and never a failure."""

import pytest

from arrt.library.services.remembered import Remembered, checked_qid
from arrt.services.errors import ServiceError


def test_the_least_recently_used_answer_goes_first():
    memory: Remembered[str, int] = Remembered(size=2)
    memory.put("a", 1)
    memory.put("b", 2)
    assert memory.get("a") == 1  # now the most recent
    memory.put("c", 3)

    assert (memory.get("a"), memory.get("b"), memory.get("c")) == (1, None, 3)


def test_putting_a_key_again_refreshes_it():
    memory: Remembered[str, int] = Remembered(size=2)
    memory.put("a", 1)
    memory.put("b", 2)
    memory.put("a", 10)
    memory.put("c", 3)

    assert (memory.get("a"), memory.get("b")) == (10, None)


@pytest.mark.parametrize("address", ["Q0", "q1", "Q1 ", "https://www.wikidata.org/wiki/Q1", ""])
def test_an_address_that_is_not_a_qid_is_the_curators_mistake(address):
    with pytest.raises(ServiceError):
        checked_qid(address)
