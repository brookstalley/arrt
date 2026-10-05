"""The suite's fault guard can fail: a contained fault in an unmarked test is a complaint."""

import pytest
from fault_guard import FaultRecords
from plugin_fakes import StubReader, claims_example

from arrt.library.sources.loading import SourceRoster


def _a_contained_fault() -> None:
    def broken(_url: str) -> bool:
        raise ValueError("bad pattern")

    SourceRoster.of(readers={"broken": (broken, StubReader())}).route("https://example.org/x")


@pytest.mark.plugin_fault_expected  # the suite-wide guard sees this fault too
def test_a_fault_in_an_unexpecting_test_is_a_complaint_naming_the_plugin():
    records = FaultRecords()
    records.attach()
    try:
        _a_contained_fault()
    finally:
        records.detach()

    assert records.complaint(expected=False) == "a source plugin faulted: broken in claims"


@pytest.mark.plugin_fault_expected
def test_a_fault_the_test_expected_is_no_complaint():
    records = FaultRecords()
    records.attach()
    try:
        _a_contained_fault()
    finally:
        records.detach()

    assert records.complaint(expected=True) is None


def test_no_fault_is_no_complaint():
    records = FaultRecords()
    records.attach()
    try:
        SourceRoster.of(readers={"good": (claims_example, StubReader())}).route("https://example.org/x")
    finally:
        records.detach()

    assert records.complaint(expected=False) is None
