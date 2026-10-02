"""The check on a QID an address carries. The bounded, least-recently-used memory
this file once held is `persistence/kept.py`'s now, and `test_kept_answers.py` holds it."""

import pytest

from arrt.library.services.remembered import checked_qid
from arrt.services.errors import ServiceError


@pytest.mark.parametrize("address", ["Q0", "q1", "Q1 ", "https://www.wikidata.org/wiki/Q1", ""])
def test_an_address_that_is_not_a_qid_is_the_curators_mistake(address):
    with pytest.raises(ServiceError):
        checked_qid(address)
