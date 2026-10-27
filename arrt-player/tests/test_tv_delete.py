"""Deleting from the television reports what the television actually holds.

The library's async `delete_list` returns None whether it removed anything or
not, so every assertion here is about the wrapper distinguishing outcomes the
library cannot: gone, still listed, and unknown.

`tv_delete` is a hand-run tool's module (`tools/tv_api_check.py` removes the
image it uploaded through it), so it is imported from `tools/` as that tool
imports it, a sibling on the path. `asyncio.run` drives each coroutine.
"""

import asyncio
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from tv_delete import UPLOADED_CATEGORY, DeleteNotConfirmed, delete_list_confirmed


class FakeTv:
    """A television that honours some removals and not others.

    `honours` is the set of ids it will actually drop; anything else stays
    listed, which is exactly the silent failure the wrapper exists to catch. A
    real set gives no signal about which case it is in, so the fake models the
    outcome rather than the protocol.
    """

    def __init__(self, listed, honours=None, confirm_raises=None, delete_raises=None):
        self.listed = list(listed)
        self.honours = set(self.listed) if honours is None else set(honours)
        self.confirm_raises = confirm_raises
        self.delete_raises = delete_raises
        self.delete_calls: list[list[str]] = []
        self.available_calls: list[str | None] = []

    async def delete_list(self, content_ids):
        self.delete_calls.append(list(content_ids))
        if self.delete_raises is not None:
            raise self.delete_raises
        self.listed = [c for c in self.listed if not (c in content_ids and c in self.honours)]
        # The library returns None here regardless of outcome. That is the defect.

    async def available(self, category=None):
        self.available_calls.append(category)
        if self.confirm_raises is not None:
            raise self.confirm_raises
        return [{"content_id": c, "category_id": category or UPLOADED_CATEGORY} for c in self.listed]


def test_a_removal_the_television_honoured_reads_as_complete():
    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-2", "MY-C0002-3"])

    result = asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1", "MY-C0002-2"]))

    assert result.complete
    assert result.deleted == ("MY-C0002-1", "MY-C0002-2")
    assert result.surviving == ()
    assert tv.listed == ["MY-C0002-3"]


def test_the_request_actually_carries_the_ids():
    """Without this, a wrapper that only ever read the list would pass every
    other test in this file — the TV would look correct because nothing had
    asked it to change."""
    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-2"])

    asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1"]))

    assert tv.delete_calls == [["MY-C0002-1"]]
    assert tv.available_calls == [UPLOADED_CATEGORY]


def test_images_the_television_kept_are_named_not_counted_as_deleted():
    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-2"], honours=["MY-C0002-1"])

    result = asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1", "MY-C0002-2"]))

    assert not result.complete
    assert result.surviving == ("MY-C0002-2",)
    assert result.deleted == ("MY-C0002-1",)


def test_a_partial_removal_warns_even_if_the_caller_ignores_the_result(caplog):
    """The return value can be dropped; the log line cannot. A caller that does
    not look must still leave a record naming the images that stayed."""
    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-2"], honours=[])

    with caplog.at_level(logging.WARNING):
        asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1", "MY-C0002-2"]))

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "MY-C0002-1" in warnings[0].getMessage()
    assert "MY-C0002-2" in warnings[0].getMessage()


def test_a_removal_that_worked_says_nothing(caplog):
    tv = FakeTv(listed=["MY-C0002-1"])

    with caplog.at_level(logging.WARNING):
        asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1"]))

    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_an_unreadable_content_list_is_unknown_not_failure():
    """samsungtvws signals a timed-out art request by asserting on a None
    response, so AssertionError is the library's timeout rather than a broken
    assumption here — and the outcome is genuinely unknown, not failed."""
    tv = FakeTv(listed=["MY-C0002-1"], confirm_raises=AssertionError())

    with pytest.raises(DeleteNotConfirmed) as exc:
        asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1"]))

    assert isinstance(exc.value.__cause__, AssertionError)
    assert tv.delete_calls == [["MY-C0002-1"]], "the request was still sent; only the confirmation failed"


def test_any_library_error_on_the_read_is_the_same_unknown_outcome():
    """Not only the library's assert. Its error taxonomy is not stable and is
    not ours — a subset named here is a subset that escapes as an abort."""

    class ResponseError(Exception):
        pass

    tv = FakeTv(listed=["MY-C0002-1"], confirm_raises=ResponseError("get_content_list failed with error number 3"))

    with pytest.raises(DeleteNotConfirmed) as exc:
        asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1"]))

    assert isinstance(exc.value.__cause__, ResponseError), "the original must survive as the cause"


def test_a_removal_request_the_set_refuses_is_unknown_too():
    """The set answering `event: error` to the removal itself raises before the
    confirming read ever runs. It is the same finding: nobody can say what the
    set holds, and it must not escape as an abort through the caller."""

    class ResponseError(Exception):
        pass

    tv = FakeTv(listed=["MY-C0002-1"], delete_raises=ResponseError("delete_image_list failed with error number 3"))

    with pytest.raises(DeleteNotConfirmed):
        asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1"]))

    assert tv.available_calls == [], "the read is unreachable once the request itself raised"


def test_nothing_to_remove_does_not_touch_the_television():
    """An empty batch is the common case on a settled wall. The library's
    `available` asserts on an empty response, so a pointless round trip is a
    real failure risk and not only a wasted one."""
    tv = FakeTv(listed=["MY-C0002-1"])

    result = asyncio.run(delete_list_confirmed(tv, []))

    assert result.complete
    assert result.requested == ()
    assert tv.delete_calls == []
    assert tv.available_calls == []


def test_repeated_ids_are_asked_for_once_and_reported_in_order():
    tv = FakeTv(listed=["MY-C0002-2", "MY-C0002-1"], honours=[])

    result = asyncio.run(delete_list_confirmed(tv, ["MY-C0002-2", "MY-C0002-1", "MY-C0002-2"]))

    assert tv.delete_calls == [["MY-C0002-2", "MY-C0002-1"]]
    assert result.requested == ("MY-C0002-2", "MY-C0002-1")
    assert result.surviving == ("MY-C0002-2", "MY-C0002-1")


def test_other_artwork_on_the_television_is_not_mistaken_for_a_survivor():
    tv = FakeTv(listed=["MY-C0002-1", "MY-C0002-9"])

    result = asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1"]))

    assert result.complete
    assert result.surviving == ()


def test_the_confirming_read_is_scoped_to_the_category_asked_for():
    tv = FakeTv(listed=["MY-C0004-1"])

    asyncio.run(delete_list_confirmed(tv, ["MY-C0004-1"], category="MY-C0004"))

    assert tv.available_calls == ["MY-C0004"]


def test_the_reason_reaches_the_message_and_not_only_the_chain():
    """`str()` of an exception never renders `__cause__`, and an unattended
    loader is read through its journal. Without the cause in the message every
    failure reads alike — including a defect in this repo, which would look like
    a television that timed out and be continued past."""

    class ResponseError(Exception):
        pass

    tv = FakeTv(listed=["MY-C0002-1"], confirm_raises=ResponseError("error number 3"))

    with pytest.raises(DeleteNotConfirmed) as refused:
        asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1"]))

    assert "ResponseError" in str(refused.value), "the cause's type must survive into the message"
    assert "error number 3" in str(refused.value)


def test_a_defect_in_this_repo_is_not_dressed_up_as_a_television_fault():
    """The cost of catching every cause is that they all look alike unless the
    message says otherwise. A TypeError is ours, not the set's."""
    tv = FakeTv(listed=["MY-C0002-1"], confirm_raises=TypeError("available() got an unexpected keyword"))

    with pytest.raises(DeleteNotConfirmed) as refused:
        asyncio.run(delete_list_confirmed(tv, ["MY-C0002-1"]))

    assert "TypeError" in str(refused.value)
