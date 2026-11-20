"""Where the MCP and HTTP surfaces describe the same record, they must agree.

`http/models.py`'s own docstring states the rule and then leaves it to memory:

    Field names match the MCP surface wherever both carry the same fact … they
    are not allowed to differ in what a thing is *called*, because that is how an
    agent and a click come to disagree about the same catalogue in a way no test
    would catch.

Nothing caught it. A grep over this suite found no reference to `ThemeOut` or
`_theme_fields` and no parity assertion of any kind, so a builder adding a Theme
field while working on the browser surface updated `_theme` and not
`_theme_fields`, `art_theme(action='get')` silently omitted it, and the suite
stayed green — precisely the disagreement the docstring forbids.

**A test rather than a shared projection, and that is a choice with a reason.**
`architecture.md`'s Decision Log (2026-07-27) says the two bindings each format
their own results, because tool results are shaped for a model and HTTP responses
for a UI. Extracting a common formatter would partially reverse that: the MCP
side returns plain dicts and the HTTP side returns pydantic models whose field
docstrings are themselves documentation. This keeps both, and makes divergence a
failure at the moment of the edit instead of a memory exercise.

**What is deliberately NOT pinned here: the artwork projections.** `WorkOut` adds
`fit` and `image` and drops `accepted_at`/`created_at`, where `_artwork_fields`
keeps the timestamps and has neither — they are two shapes for two readers, which
is the case the recorded decision actually describes. Theme, Artist and the
candidate-work summary are not that: they are one shape written twice.
"""

from datetime import UTC, datetime

import pytest
from fakes import an_image

from arrt.http import api as http_api
from arrt.http import models as http_models
from arrt.library.discovery.phase_two import JudgedImage
from arrt.library.services.discovery import VerdictOutcome, WantedWork
from arrt.library.services.look import LookPicture, LookState, LookView, SourceLook, SourceState
from arrt.library.services.quality import Fit
from arrt.library.services.review import WantedView
from arrt.library.sources.loading import PluginIdentity, PluginPart, PluginReading, PluginState
from arrt.mcp import bindings
from arrt.persistence.discovery_records import (
    CandidateWork,
    DiscoveryRun,
    InitiatedBy,
    RunKind,
    RunStatus,
    SearchTally,
    UnresolvedReason,
)
from arrt.persistence.records import Artist, Artwork, Theme
from arrt.services.health import PicturesReading, SourceHealth

WHEN = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def _fields(model: type) -> set[str]:
    """The field names a pydantic response model declares."""
    return set(model.model_fields)


def check_parity(record: str, mcp: set[str], http: set[str], http_only: frozenset[str] = frozenset()) -> None:
    """Raise unless two projections of `record` name the same facts the same way.

    A checked function rather than an assertion per pair, because the pairs in
    this tree all currently agree — so an assertion written directly against them
    can only ever be seen to pass. A mutation sweep loosened `==` to `<=` in two
    of them and nothing went red: with the comparison one-directional, a field
    dropped from a projection would have sailed through the very test written to
    catch it. The fabricated cases below are what make the strictness provable.

    Three ways to disagree, and the third is the one nobody thinks of:

    - a field the HTTP model has and the tool result does not — an agent cannot
      read a fact a click can;
    - the reverse;
    - an **exemption that no longer applies**. If a field named here as
      intentionally HTTP-only later appears on both, the entry stops describing
      anything and starts hiding the next real divergence behind a name that
      looks considered.
    """
    missing_from_mcp = http - mcp - http_only
    missing_from_http = mcp - http
    stale_exemptions = http_only - (http - mcp)

    assert not missing_from_mcp, (
        f"the HTTP {record} model carries {sorted(missing_from_mcp)} that the MCP projection does "
        "not. One record, two readers that must call its facts by the same names — the surface "
        "missing a field will silently omit it while its suite stays green. Add it to both, or "
        "record it as intentionally HTTP-only with its reason."
    )
    assert not missing_from_http, (
        f"the MCP {record} projection carries {sorted(missing_from_http)} that the HTTP model does "
        "not — a fact an agent can read and a click cannot."
    )
    assert not stale_exemptions, (
        f"{sorted(stale_exemptions)} is recorded as intentionally HTTP-only on {record}, but the "
        "two projections now agree about it. Remove the exemption: one that no longer applies "
        "hides the next real divergence behind a name that reads as considered."
    )


def test_the_theme_projections_carry_the_same_field_names():
    """One shape, two writers. Adding a field to one must fail until both follow."""
    theme = Theme(id="thm_1", name="Quiet", created_at=WHEN)

    check_parity("Theme", set(bindings._theme_fields(theme)), _fields(http_models.ThemeOut))


def test_the_artist_projections_carry_the_same_field_names():
    artist = Artist(id="art_1", name="Hokusai")

    check_parity("Artist", set(bindings._artist_fields(artist)), _fields(http_models.ArtistOut))


#: The one field whose name differs between the record and both projections, and
#: it differs on purpose: `id` is unambiguous on a record and would not be in a
#: result object that also carries a work id.
ARTIST_RENAMES = {"id": "artist_id"}


def test_every_fact_the_artist_record_holds_reaches_both_surfaces():
    """**Anchored to the record, which is the check the pair above cannot make.**

    `check_parity` compares the two projections to each other, so a fact missing
    from *both* is invisible to it — they agree, and agreeing is all it asks.
    That is not hypothetical: `display_nationality` was added to the record, the
    store and the manifest builder on 2026-08-13 and reached neither read surface
    until a Critic round found it, with this file green throughout. The e-paper
    label was setting a fact no browser and no agent could see.

    **Artist only, deliberately, and the limit is worth stating.** Every record
    in this tree has the same hole; this is the one where it drew blood, and the
    ten fields here need a single rename to line up. Generalising means an
    exemption list per record for the facts a surface withholds on purpose, which
    is a different piece of work from closing the one that bit — and a list
    written speculatively for eight records is a list nobody has checked.
    """
    artist = Artist(id="art_1", name="Hokusai")
    held = {ARTIST_RENAMES.get(field, field) for field in artist.__dataclass_fields__}

    for surface, carried in (
        ("the MCP tool result", set(bindings._artist_fields(artist))),
        ("the HTTP model", _fields(http_models.ArtistOut)),
    ):
        assert not held - carried, (
            f"{sorted(held - carried)} is on the Artist record and not in {surface}. "
            "A fact the label sets and no reader can see is the shape this test exists for."
        )


#: The fields `CandidateWorkOut` carries that `_work_summary` does not, and why
#: each difference is intended on both sides rather than an omission.
#:
#: `rationale`: the HTTP model shows the run view and the review grid, where a
#: curator judging a work list is judging the engine's reasoning as much as the
#: titles. The MCP summary is deliberately "enough to choose and to act, and no
#: more" — and the same prose repeated across forty listing rows is what pushed
#: that shape past the token budget its own docstring records measuring.
#:
#: `decided`: carried for the browser for the reason `RunOut.is_terminal` is
#: (below). The review card hides its verdict controls on it, and a list of
#: final verdicts copied into the client is what would go stale. A model reads
#: `verdict` itself, and a second verdict's refusal says the first was final.
#:
#: Named rather than tolerated by a subset check: an exemption list is a
#: decision per field, and a bare `<=` would silently absorb the next four.
HTTP_ONLY_ON_CANDIDATE_WORK = frozenset({"rationale", "decided"})


def test_the_candidate_work_projections_agree_but_for_the_named_fields():
    """The keys the MCP surface writes once, against the HTTP model's, which adds only the named fields.

    Until 2026-08-06 those seven were written out at four sites with identical
    expressions — three in `bindings.py` and one in `api.py`. Adding `provenance`
    took four coordinated edits, and the next field added to `CandidateWork` would
    have reached some of them and not others.

    Three of the four are now one function. This holds the fourth, which cannot
    be merged into it: the HTTP surface returns a typed model, not a dict.
    """
    work = _work()

    check_parity(
        "CandidateWork",
        set(bindings._work_summary(work)),
        _fields(http_models.CandidateWorkOut),
        HTTP_ONLY_ON_CANDIDATE_WORK,
    )


def test_the_wanted_work_projections_carry_the_same_field_names():
    """Wanted and `art_review(action='list_wanted')` read one listing."""
    entry = WantedView(wanted=WantedWork(work=_work(), scans_turned_down=2), shown=None)

    check_parity("WantedWork", set(bindings._wanted_fields(entry)), _fields(http_models.WantedWorkOut))


#: The one field `RunOut` carries that the tool result does not.
#:
#: `is_terminal` is carried for the browser rather than left for it to derive
#: from a list of status names, because that list is the thing that goes stale: a
#: tenth status added to the enum would leave a browser polling a finished run
#: for ever with nothing failing to say so. A model reads `status` itself and has
#: the enum's meaning in the tool description, so it needs no such crutch.
HTTP_ONLY_ON_RUN = frozenset({"is_terminal"})


def test_the_run_projections_agree_but_for_one_named_field(discovery):
    """Pinned while both surfaces were being changed at once, which is when it matters.

    `http/api.py`'s run listing carried a note saying the cap had to reach both
    surfaces together, "because fixing one alone is how the two come to
    disagree". The same is true of the row's field names, and nothing was
    checking them.
    """
    run = DiscoveryRun(
        id="r1",
        kind=RunKind.DISCOVERY,
        initiated_by=InitiatedBy.MCP_CLIENT,
        status=RunStatus.COMPLETED,
        approval_required=False,
        started_at=WHEN,
    )

    check_parity("DiscoveryRun", set(bindings._run_fields(run, discovery)), _fields(http_models.RunOut), HTTP_ONLY_ON_RUN)


def test_a_field_only_the_http_model_has_is_rejected():
    """The direction a builder hits while working on the browser surface."""
    with pytest.raises(AssertionError, match="MCP projection does not"):
        check_parity("Theme", mcp={"theme_id", "name"}, http={"theme_id", "name", "shuffle"})


def test_a_field_only_the_tool_result_has_is_rejected():
    """The other direction, which a UI-focused reviewer is least likely to notice."""
    with pytest.raises(AssertionError, match="a click cannot"):
        check_parity("Theme", mcp={"theme_id", "name", "shuffle"}, http={"theme_id", "name"})


def test_an_exemption_that_no_longer_applies_is_rejected():
    """A named difference must keep being a difference, or it stops meaning anything."""
    with pytest.raises(AssertionError, match="now agree about it"):
        check_parity(
            "CandidateWork",
            mcp={"work_id", "rationale"},
            http={"work_id", "rationale"},
            http_only=frozenset({"rationale"}),
        )


def test_the_mcp_listing_and_detail_shapes_both_compose_the_summary():
    """The intra-surface half of the same defect, and the reason it is safe here.

    `_candidate_detail` does not compose `_candidate_summary`, and its docstring
    is right about why: `_shown_fields` appends an image block as a side effect
    of assigning an index, so composing the two would picture one instance twice
    and charge the caller for both. That argument is about the image half and
    never reached the seven text keys, which is how they came to be repeated.

    Asserted through the real projections rather than by reading them: a later
    edit that re-inlines one of these shapes would restore the drift this whole
    module exists to prevent, and nothing else would notice.
    """
    work = _work()
    view = _view(work)
    pictures = bindings._Pictures()
    summary_keys = set(bindings._work_summary(work))

    assert summary_keys <= set(bindings._candidate_summary(view, pictures))
    assert summary_keys <= set(bindings._candidate_detail(view, pictures))


def check_divergence(mcp: set[str], http: set[str], mcp_only: set[str], http_only: set[str]) -> None:
    """Raise unless each surface still carries the fields that make it its own shape.

    The mirror of `check_parity`, and it needs the same treatment for the same
    reason: written as a bare assertion against the real tree it can only be seen
    to pass, and a sweep proved that. Weakening `>= {"accepted_at", "created_at"}`
    to `>= set()` left it vacuously true and every test green — an alert that had
    stopped alerting, in a test whose entire purpose is to alert.
    """
    lost_from_http = http_only - (http - mcp)
    lost_from_mcp = mcp_only - (mcp - http)

    assert not lost_from_http, (
        f"WorkOut no longer carries {sorted(lost_from_http)} uniquely — the fields that make it a "
        "UI's shape rather than a tool result's: how the held master meets the wall, and where to "
        "fetch the picture. These projections converging is a reason to re-read the Decision Log's "
        "per-surface-formatting rationale, not to widen this test."
    )
    assert not lost_from_mcp, (
        f"the tool result no longer carries {sorted(lost_from_mcp)} uniquely — the timestamps "
        "WorkOut drops. Same conclusion as above."
    )


def test_the_artwork_projections_are_free_to_differ_and_actually_do():
    """The scoped-out case, asserted so the scope-out is a fact rather than a claim.

    `architecture.md`'s per-surface-formatting rationale describes exactly this
    pair — two shapes for two readers — and the tests above would be wrong to
    cover it. Written as a test because "these may differ" is otherwise
    indistinguishable from "nobody checked", and because the divergence is the
    *evidence* for the rationale: if the two ever converged, the recorded reason
    for keeping every projection independent would have lost its only example,
    and the tests above would deserve to grow a fourth pair.
    """
    artwork = Artwork(id="awk_1", title="The Great Wave", created_at=WHEN)

    check_divergence(
        mcp=set(bindings._artwork_fields(artwork)),
        http=_fields(http_models.WorkOut),
        mcp_only={"accepted_at", "created_at"},
        http_only={"fit", "image"},
    )


def test_the_ui_shape_losing_its_own_fields_is_reported():
    """The alert firing, which the real tree cannot show while the pair still differs.

    **One direction per case, and that is the correction rather than the design.**
    A single fabricated case that broke both directions at once passed whichever
    assertion fired first, so a sweep could blank either one and the test stayed
    green — the same vacuity it was written to prevent, one level up. Each case
    now leaves the other direction intact, so only the assertion under test can
    raise.
    """
    with pytest.raises(AssertionError, match="WorkOut no longer carries"):
        check_divergence(
            mcp={"artwork_id", "created_at"},
            http={"artwork_id"},
            mcp_only={"created_at"},
            http_only={"fit"},
        )


def test_the_tool_result_losing_its_own_fields_is_reported():
    with pytest.raises(AssertionError, match="the tool result no longer carries"):
        check_divergence(
            mcp={"artwork_id"},
            http={"artwork_id", "fit"},
            mcp_only={"created_at"},
            http_only={"fit"},
        )


def _work() -> CandidateWork:
    """The minimum a candidate work needs to exist. Only its key names matter here."""
    return CandidateWork(
        id="cw_1",
        discovery_run_id="run_1",
        proposed_title="The Great Wave",
        rationale="named by the model",
        work_dedup_key="great-wave",
    )


def _view(work: CandidateWork):
    """A CandidateView with no instances, which is all these shapes need.

    Built here rather than in a fixture because only this module wants it: the
    parity claim is about key *names*, so an empty view exercises every key
    without needing a store, a run, or an image on disk.
    """
    from arrt.library.services.review import CandidateView

    return CandidateView(work=work, instances_held=0, instances_surviving=0, shown=None)


def test_the_two_verdict_notices_say_exactly_the_same_thing():
    """Two copies of one sentence, held identical by a test rather than by memory.

    `http/api.py`'s copy carried a docstring explaining why it did *not* share
    with the MCP one — "that one is written for a model and names tool calls in
    backticks; this one is read by a person". That is true of the run-view
    sentence and false of this: the text names artists, and the two functions
    were byte-for-byte identical, so the paragraph asserted a divergence nobody
    had built and nothing would have caught.

    They stay two — the day one needs a reader-specific word is the day sharing
    would be in the way, and merging formatters across surfaces is what the
    Decision Log declines. This is what makes "identical" a fact instead of a
    coincidence: a word changed on one surface and not the other fails here.
    """
    minted = Artist(id="art_1", name="Hokusai")
    outcome = VerdictOutcome(
        work=_work(),
        minted_artist=minted,
        duplicate_candidates=(Artist(id="art_2", name="Katsushika Hokusai"),),
    )

    assert http_api._verdict_notice(outcome) == bindings._verdict_notice(outcome)


def test_the_two_verdict_notices_are_both_silent_on_the_same_input():
    """Identical text is half the claim; identical *silence* is the other half.

    Both return None unless a mint and a near-miss arrive together, and a copy
    that drifted on the guard rather than on the wording would still pass the
    test above for every case that produces a sentence.
    """
    outcome = VerdictOutcome(work=_work(), minted_artist=None, duplicate_candidates=())

    assert http_api._verdict_notice(outcome) is None
    assert bindings._verdict_notice(outcome) is None


def test_a_held_work_is_reported_as_held_on_every_surface():
    """The review card and both tool shapes carry which artwork a candidate already is.

    A non-default value, so a formatter that dropped the field, or wrote a
    constant, fails here rather than passing on the null every other view carries.
    """
    from arrt.library.services.review import CandidateView

    view = CandidateView(work=_work(), instances_held=0, instances_surviving=0, shown=None, held_artwork_id="aw_7")

    assert http_api._candidate_card(view).held_artwork_id == "aw_7"
    assert bindings._candidate_summary(view, bindings._Pictures())["held_artwork_id"] == "aw_7"
    assert bindings._candidate_detail(view, bindings._Pictures())["held_artwork_id"] == "aw_7"


def test_the_wikidata_match_projections_carry_the_same_field_names():
    """The browser's picker and `art_review(action='wikidata_matches')` read one listing."""
    from arrt.library.registry import ItemId, RegistryText, RegistryWorkMatch
    from arrt.library.services.wikidata_match import WorkMatch

    entry = WorkMatch(
        match=RegistryWorkMatch(qid=ItemId("Q2990594"), title=RegistryText("Lobster Telephone"), sitelinks=13),
        by_proposed_artist=True,
    )

    check_parity("WorkMatch", set(bindings._match_fields(entry)), _fields(http_models.WorkMatchOut))


#: The could-not-be-asked and answered counts (wave 2b, Chunk 32) and the search
#: record's (Chunk 33), as fields: HTTP carried them first, MCP since Chunk 53.
#: Each named so the value test below holds every one to its own reading.
SOURCE_PLUGIN_COUNTS = ("unasked", "last_unasked_at", "last_unasked_age_seconds", "last_unasked", "answered")
SOURCE_PLUGIN_SEARCH_COUNTS = ("searched", "searches_answered", "searches_unasked", "searches_owed", "last_search_answered_at")


def test_the_source_plugin_projections_agree_value_for_value():
    """Settings › Sources and `art_discovery(action='source_plugins')` read one plugin the same way."""
    reading = PluginReading(
        name="met",
        state=PluginState.LOADED,
        reason=None,
        faults=2,
        last_fault_at=WHEN,
        last_fault="ImageSearchFailure: down",
        identity=PluginIdentity(distribution="arrt", version="0.3.0", api_major=1, provides=(PluginPart.FINDS_IMAGES,)),
        unasked=3,
        last_unasked_at=WHEN,
        last_unasked="the Met plugin could not be asked: it did not answer within 60 seconds",
        answered=5,
    )
    searches = SearchTally(provider="met", searched=9, answered=4, unasked=3, owed=2, last_answered_at=WHEN)
    health = SourceHealth(reading=reading, last_fault_age_seconds=12.0, last_unasked_age_seconds=7.0, searches=searches)

    check_parity("SourcePlugin", set(bindings._source_plugin_fields(health)), _fields(http_models.SourcePluginOut))
    http = http_api._source_plugin(health).model_dump()
    tool = bindings._source_plugin_fields(health)
    assert tool == http
    # The counts are the reading's, as fields, not only inside `description`, on both surfaces.
    assert {name: tool[name] for name in sorted(SOURCE_PLUGIN_COUNTS)} == {
        "answered": 5,
        "last_unasked": "the Met plugin could not be asked: it did not answer within 60 seconds",
        "last_unasked_age_seconds": 7.0,
        "last_unasked_at": WHEN.isoformat(),
        "unasked": 3,
    }
    # The search record's counts, as fields: each its own, none a default.
    assert {name: tool[name] for name in sorted(SOURCE_PLUGIN_SEARCH_COUNTS)} == {
        "last_search_answered_at": WHEN.isoformat(),
        "searched": 9,
        "searches_answered": 4,
        "searches_owed": 2,
        "searches_unasked": 3,
    }


def test_a_plugin_never_searched_reads_alike_on_both_surfaces():
    """No search record: both surfaces say zero searches and no last answer, not one a null and one a zero."""
    reading = PluginReading(
        name="met",
        state=PluginState.LOADED,
        reason=None,
        faults=0,
        last_fault_at=None,
        last_fault=None,
        identity=PluginIdentity(distribution="arrt", version="0.3.0", api_major=1, provides=(PluginPart.FINDS_IMAGES,)),
    )
    health = SourceHealth(reading=reading, last_fault_age_seconds=None)

    tool = bindings._source_plugin_fields(health)
    assert tool == http_api._source_plugin(health).model_dump()
    assert (tool["searched"], tool["searches_owed"], tool["last_search_answered_at"]) == (0, 0, None)


def test_a_works_place_in_the_queue_agrees_value_for_value():
    """`art_catalogue(action='get')`'s `acquisition` is `AcquisitionStateOut`: Chunk 32's outcome, plugin and failure time too.

    Every field filled, so a formatter that dropped one or wrote a constant
    fails here, not only one that misnamed it. No test held this pair until
    wave 2b's Chunk 53: the route gained three fields and the tool did not.
    """
    from arrt.library.acquisition.queue import AcquisitionPhase, AcquisitionState
    from arrt.persistence.records import FetchOutcome

    state = AcquisitionState(
        artwork_id="awk_1",
        phase=AcquisitionPhase.FAILED,
        failures=2,
        detail="The Met plugin could not be asked: it did not answer within 60 seconds",
        next_try_at=WHEN,
        since=WHEN,
        condition="DiskFull",
        outcome=FetchOutcome.UNASKED,
        plugin="met",
        failed_at=WHEN,
    )

    tool = bindings._acquisition_fields(state)
    assert tool is not None
    check_parity("AcquisitionState", set(tool), _fields(http_models.AcquisitionStateOut))
    assert tool == http_api._acquisition(state).model_dump()
    assert (tool["outcome"], tool["plugin"], tool["failed_at"]) == ("unasked", "met", WHEN.isoformat())


def test_the_picture_store_readings_agree_value_for_value():
    """Status and `art_display(action='status')` state the store's size in the same names and numbers."""
    reading = PicturesReading(pictures_bytes=123_456_789, pictures_files=2_468, age_seconds=42.0, unreadable=3)

    check_parity("Pictures", set(bindings._pictures_fields(reading)), _fields(http_models.PicturesOut))
    assert bindings._pictures_fields(reading) == http_api._pictures(reading).model_dump()
    assert {"pictures_bytes", "pictures_files"} <= set(bindings._pictures_fields(reading))


def check_not_yet_on_mcp(record: str, mcp: set[str], http: set[str], not_yet: frozenset[str]) -> None:
    """Raise unless the two surfaces agree but for `not_yet`, each of which HTTP answers and MCP does not.

    Both ways an exemption goes stale fail by name: a field it names that HTTP
    no longer answers, and one MCP now answers too (then the exemption is
    deleted, not kept as a name that reads as considered).
    """
    gone = not_yet - http
    arrived = not_yet & mcp
    assert not gone, f"{sorted(gone)} is exempted as not yet on MCP for {record}, but HTTP does not answer it"
    assert not arrived, f"{sorted(arrived)} is exempted as not yet on MCP for {record}, but MCP answers it now: delete it"
    assert mcp == http - not_yet, (
        f"{record}: MCP answers {sorted(mcp - http)} HTTP does not, and HTTP answers "
        f"{sorted(http - mcp - not_yet)} MCP does not"
    )


def test_an_exemption_for_a_field_http_no_longer_answers_is_refused():
    with pytest.raises(AssertionError, match="HTTP does not answer it"):
        check_not_yet_on_mcp("Client", mcp={"name"}, http={"name"}, not_yet=frozenset({"state"}))


def test_an_exemption_for_a_field_mcp_now_answers_is_refused():
    with pytest.raises(AssertionError, match="MCP answers it now"):
        check_not_yet_on_mcp("Client", mcp={"name", "state"}, http={"name", "state"}, not_yet=frozenset({"state"}))


def test_a_field_neither_answered_alike_nor_exempted_is_refused():
    with pytest.raises(AssertionError, match=r"HTTP answers \['shuffle'\] MCP does not"):
        check_not_yet_on_mcp("Client", mcp={"name"}, http={"name", "shuffle", "state"}, not_yet=frozenset({"state"}))


def test_every_health_reading_is_placed_on_the_mcp_status_or_left_off_it_by_name():
    """`art_display(action='status')` is the panel's twin; a new panel signal must be placed, not forgotten.

    Derived from `HealthReading`'s own fields, so a reading added to the panel
    fails here until the binding says whether its twin carries it. Every one is
    placed since wave 2b's Chunk 53 gave the status each Player's state and the
    failed fetches; there is no "not yet" list any more.

    The readings the panel derives rather than holds (`troubles()`,
    `setup_steps()`, `describe()`) are not fields, so they are held here by
    name to the status keys that carry them; a fourth derived reading fails
    until it is placed. `test_client_tools.py` holds the values to the route's.
    """
    from dataclasses import fields

    from arrt.services.health import HealthReading

    panel = {field.name for field in fields(HealthReading)}
    carried, left = set(bindings._STATUS_CARRIES), set(bindings._STATUS_LEAVES)

    assert carried | left == panel
    assert not carried & left
    assert all(reason.strip() for reason in bindings._STATUS_LEAVES.values())
    derived = {
        name
        for name in dir(HealthReading)
        if not name.startswith("_") and name not in panel and callable(getattr(HealthReading, name))
    }
    assert derived == set(STATUS_KEY_OF_A_DERIVED_READING)
    from contract.test_mcp_break import surface_shape

    answered = set(surface_shape()["art_display"]["actions"]["status"]["result_keys"])
    assert set(STATUS_KEY_OF_A_DERIVED_READING.values()) <= answered


#: The readings `HealthReading` derives, and the `art_display(action='status')`
#: key that carries each: the panel's sentence is the status's `observation`.
STATUS_KEY_OF_A_DERIVED_READING = {"troubles": "troubles", "setup_steps": "setup_steps", "describe": "observation"}


def test_a_players_state_agrees_value_for_value():
    """`art_players(action='clients')`'s `state` is `GET /api/clients`' `PlayerStateOut`, by name and by value.

    A reporting Player with a display, a label panel and an output it has not
    reported yet, so `since`, each output's kind, state and `connected` are
    values and not the nulls of a Player with no report.
    """
    from arrt.programming.player_state import OutputKind, OutputState, PlayerReading, PlayerState

    reading = PlayerReading(
        state=PlayerState.REPORTING,
        since=WHEN,
        outputs=(
            OutputState(kind=OutputKind.DISPLAY, name="hdmi-a-1", state=PlayerState.REPORTING, connected=True),
            OutputState(kind=OutputKind.LABEL, name="epd-0", state=PlayerState.REPORTING, connected=False),
            OutputState(kind=OutputKind.DISPLAY, name="hdmi-a-2", state=PlayerState.AWAITING_REPORT, connected=None),
        ),
    )

    tool = bindings._player_state_fields(reading)
    check_parity("PlayerState", set(tool), _fields(http_models.PlayerStateOut))
    check_parity("OutputState", set(tool["outputs"][0]), _fields(http_models.OutputStateOut))
    assert tool == http_api._player_state(reading).model_dump()
    assert tool["since"] == WHEN.isoformat()


#: The one name a look's picture carries on MCP alone: which image block is its
#: own. A browser asks for the picture by key instead.
MCP_ONLY_ON_LOOK_PICTURE = frozenset({"image_block_index"})


def _a_look() -> LookView:
    found = an_image("Tantra-Vision", artist="Ejler Bille", width=2201, height=2221, provider="smk")
    fit = Fit.MEETS_MINIMUM
    picture = LookPicture(
        key="a" * 64, judged=JudgedImage(found=found, confidence=0.95, quality_score=0.8, rationale="Why.", fit=fit)
    )
    source = SourceLook(
        provider="smk",
        state=SourceState.FOUND,
        pictures=(picture,),
        refusals=frozenset({UnresolvedReason.NOT_HELD}),
        answered_at=WHEN,
    )
    return LookView(qid="Q20267229", state=LookState.ANSWERED, sources=(source,), pictures=(picture,))


def test_the_look_projections_agree_value_for_value_but_for_the_image_block():
    """`art_discovery(action='look')` is `GET /api/registry/works/{qid}/look`, in the same names and values."""
    view = _a_look()
    tool = bindings._look_fields(view, bindings._Pictures(), {})
    route = http_api._look(view)

    check_parity("Look", set(tool), _fields(http_models.LookOut))
    check_parity("LookSource", set(tool["sources"][0]), _fields(http_models.LookSourceOut))
    check_parity("LookPicture", set(tool["pictures"][0]) - MCP_ONLY_ON_LOOK_PICTURE, _fields(http_models.LookPictureOut))
    check_parity("Fit", set(bindings._fit_fields(view.pictures[0].judged.fit)), _fields(http_models.FitOut))
    assert set(tool["pictures"][0]) >= MCP_ONLY_ON_LOOK_PICTURE, "an exemption for a field the tool no longer carries"
    tool["pictures"] = [{k: v for k, v in p.items() if k not in MCP_ONLY_ON_LOOK_PICTURE} for p in tool["pictures"]]
    assert tool == route.model_dump()


#: The names MCP's wall answers and HTTP's spell differently, per record, MCP's
#: name first. One fact, two names, on purpose: MCP's wall answers say
#: `artwork_id` for a work since wave 2b (the owner's ruling 3 of 2026-11-19), the
#: name every MCP action takes, and `/api`, whose only reader is the browser,
#: keeps `work_id` (`build-plan-audit-wave-2b.md`'s Goals, "Tradeoffs accepted").
#: Every other name on these records is the same on both. `check_renamed` refuses
#: a rename that no longer describes the two surfaces. Each record is compared
#: below, but `Upcoming`, which `tests/integration/test_walls_last_shown.py`
#: compares through a real server, as `GET /api/walls` and `art_display(action='walls')`.
WALL_RENAMES: dict[str, dict[str, str]] = {
    "DisplayState": {"artwork_id": "work_id"},
    "ReportedState": {"artwork_id": "work_id"},
    "LastShown": {"artwork_id": "work_id"},
    "Upcoming": {"artwork_id": "work_id"},
    "SceneWall": {"artwork_id": "work_id"},
    "Next": {"artwork_id": "work_id"},
}


def check_renamed(record: str, mcp: set[str], http: set[str], renames: dict[str, str] | None = None) -> set[str]:
    """Raise unless each rename is live, and return MCP's names in HTTP's spelling.

    Live means the MCP name is one MCP answers and HTTP does not, and the HTTP
    name one HTTP answers and MCP does not. A rename either surface has stopped
    needing would otherwise go on translating a name nobody sends, and hide the
    next real divergence behind a pair that reads as considered.
    """
    renames = WALL_RENAMES[record] if renames is None else renames
    for mcp_name, http_name in renames.items():
        mcp_alone = mcp_name in mcp and mcp_name not in http
        assert mcp_alone, (
            f"{record}: the rename {mcp_name!r} -> {http_name!r} is stale: MCP does not answer {mcp_name!r} "
            "where HTTP does not. Delete it."
        )
        http_alone = http_name in http and http_name not in mcp
        assert http_alone, (
            f"{record}: the rename {mcp_name!r} -> {http_name!r} is stale: HTTP does not answer {http_name!r} "
            "where MCP does not. Delete it."
        )
    return {renames.get(name, name) for name in mcp}


def in_http_names(value: object, renames: dict[str, str]) -> object:
    """An MCP answer with every renamed key spelt as HTTP spells it, at any depth."""
    if isinstance(value, dict):
        return {renames.get(key, key): in_http_names(inner, renames) for key, inner in value.items()}
    if isinstance(value, list):
        return [in_http_names(inner, renames) for inner in value]
    return value


def test_a_rename_mcp_no_longer_needs_is_refused():
    with pytest.raises(AssertionError, match="stale: MCP does not answer 'artwork_id'"):
        check_renamed("Upcoming", mcp={"work_id", "starts_at"}, http={"work_id", "starts_at"})


def test_a_rename_http_no_longer_needs_is_refused():
    with pytest.raises(AssertionError, match="stale: HTTP does not answer 'work_id'"):
        # The day /api renames its field too, or drops it.
        check_renamed("Upcoming", mcp={"artwork_id", "starts_at"}, http={"starts_at"})


def test_a_planted_rename_is_refused():
    """A rename for a name both surfaces already share is stale the day it is written."""
    with pytest.raises(AssertionError, match="stale"):
        check_renamed(
            "Upcoming",
            mcp={"artwork_id", "starts_at"},
            http={"work_id", "starts_at"},
            renames={"artwork_id": "work_id", "starts_at": "starts_at"},
        )


def test_a_walls_display_state_agrees_value_for_value_but_for_the_one_rename():
    """`art_display(action='walls')` and `GET /api/walls` state a wall's screen alike, `artwork_id` aside."""
    from arrt.programming.display_state import DisplayState, ReportedState, ScreenState

    shown = DisplayState(
        state=ScreenState.SILENT,
        work_id=None,
        since=WHEN,
        reported_at=WHEN,
        age_seconds=4000.0,
        last=ReportedState(state=ScreenState.SHOWING_ART, work_id="wrk_1", since=WHEN),
    )
    tool = bindings._display_state_fields(shown)
    route = http_api._display_state(shown).model_dump()

    check_parity("DisplayState", check_renamed("DisplayState", set(tool), set(route)), _fields(http_models.DisplayStateOut))
    check_parity(
        "ReportedState",
        check_renamed("ReportedState", set(tool["last"]), set(route["last"])),
        _fields(http_models.ReportedStateOut),
    )
    assert in_http_names(tool, WALL_RENAMES["DisplayState"]) == route
    assert tool["last"]["artwork_id"] == "wrk_1"


#: `WallHeartbeatOut.heartbeat` is one nested record on HTTP; the status carries
#: it flattened onto the wall, in these names, MCP's first. `has_reported` is
#: `absent` negated, the status's name since before wave 2b.
STATUS_WALL_HEARTBEAT: dict[str, str] = {
    "observation": "description",
    "has_reported": "absent",
    "reported_at": "reported_at",
    "age_seconds": "age_seconds",
    "problem": "problem",
    "reported": "reported",
}

#: `HeartbeatOut`'s fields the status leaves off, and why.
STATUS_WALL_LEAVES_OF_THE_HEARTBEAT: dict[str, str] = {
    "path": "where the heartbeat file lies on the server's disk is the operator's to read, not a question a model is asked",
}

#: The one name MCP's wall and `WallOut` spell differently, MCP's first: what
#: hangs on the wall. Named before the two were paired here (wave 2b, Chunk 66).
WALL_RECORD_RENAMES: dict[str, str] = {"hanging": "theme"}


def _a_wall_waiting_for_its_player(services):
    """A wall shown by a Player with no token: it waits, so every wait field is a value, not null."""
    wall = services.display.add_wall(name="The hall")
    player = services.clients.add_client(name="Hall Pi")
    services.clients.assign_wall(wall.id, client_id=player.id, output="hdmi-a-1")
    return wall, player


def check_status_wall(tool: dict, route: dict) -> None:
    """Raise unless a status wall is `WallHeartbeatOut`'s fields, the heartbeat flattened and `path` left off by name."""
    left = set(STATUS_WALL_LEAVES_OF_THE_HEARTBEAT)
    assert set(STATUS_WALL_HEARTBEAT.values()) | left == _fields(http_models.HeartbeatOut), (
        "HeartbeatOut carries a field the status neither flattens onto its wall nor leaves off by name: "
        f"{sorted(_fields(http_models.HeartbeatOut) - set(STATUS_WALL_HEARTBEAT.values()) - left)}"
    )
    assert set(STATUS_WALL_HEARTBEAT) <= set(tool), f"the status wall lost {sorted(set(STATUS_WALL_HEARTBEAT) - set(tool))}"
    check_parity("WallHeartbeat", (set(tool) - set(STATUS_WALL_HEARTBEAT)) | {"heartbeat"}, set(route))


def test_a_status_wall_is_the_health_answers_wall_by_name_and_by_value(services):
    """`art_display(action='status')`'s walls against `WallHeartbeatOut`, `waiting_for` included (Chunk 66).

    Unpaired until Chunk 66, so `waiting_for` reached the health answer with
    neither a twin nor an exemption and nothing said so. A field added to a
    wall's health answer now fails here by name until the status carries it.
    """
    wall, player = _a_wall_waiting_for_its_player(services)
    reading = services.health.observe()
    [tool] = [e for e in bindings._wall_status(services, {})["walls"] if e["wall_id"] == wall.id]
    [route] = [e for e in http_api._health(reading).model_dump()["walls"] if e["wall_id"] == wall.id]

    check_status_wall(tool, route)
    check_parity("WallWait", set(tool["waiting_for"]), _fields(http_models.WallWaitOut))
    assert tool["waiting_for"] == route["waiting_for"]
    assert route["waiting_for"]["client_id"] == player.id
    assert tool["has_reported"] is not route["heartbeat"]["absent"]
    for mcp_name, http_name in STATUS_WALL_HEARTBEAT.items():
        if mcp_name != "has_reported":
            assert tool[mcp_name] == route["heartbeat"][http_name], mcp_name


def test_a_field_added_to_a_walls_health_answer_and_not_to_the_status_is_refused_by_name():
    tool = {"wall_id", "wall_name", "display_state", "waiting_for", *STATUS_WALL_HEARTBEAT}
    route = dict.fromkeys(_fields(http_models.WallHeartbeatOut))
    with pytest.raises(AssertionError, match=r"carries \['waiting_for'\] that the MCP projection does not"):
        check_status_wall(dict.fromkeys(tool - {"waiting_for"}), route)
    with pytest.raises(AssertionError, match="the status wall lost"):
        check_status_wall(dict.fromkeys(tool - {"problem"}), route)


def test_a_wall_reads_alike_on_the_walls_answer_and_mcp_walls_but_for_the_one_rename(services):
    """`art_display(action='walls')` against `WallOut`, by name, and `waiting_for` by value (Chunk 66)."""
    wall, player = _a_wall_waiting_for_its_player(services)
    view = services.display.get_wall_view(wall.id)
    tool = bindings._wall_view_fields(services, view)
    route = http_api._wall(services, view).model_dump()

    check_parity("Wall", check_renamed("Wall", set(tool), set(route), WALL_RECORD_RENAMES), _fields(http_models.WallOut))
    waits = services.health.observe_waiting()
    assert tool["waiting_for"] == route["waiting_for"] == bindings._wall_wait_fields(waits[wall.id])
    assert route["waiting_for"]["client_id"] == player.id


def test_a_walls_last_showing_agrees_value_for_value_but_for_the_one_rename():
    from arrt.persistence.records import Showing

    showing = Showing(wall_id="wal_1", work_id="wrk_1", started_at=WHEN, last_seen_at=WHEN)
    tool = bindings._last_shown_fields(showing)
    route = http_api._last_shown(showing).model_dump()

    check_parity("LastShown", check_renamed("LastShown", set(tool), set(route)), _fields(http_models.LastShownOut))
    assert in_http_names(tool, WALL_RENAMES["LastShown"]) == route


def test_a_step_answers_in_the_routes_names_but_for_the_one_rename_and_its_notice():
    """`next` and `show_now` against `NextOut`, which carries no notice: the tool's says what was not confirmed."""
    stepped = bindings._republished_fields("wal_1", "wrk_1")

    check_parity(
        "Next", check_renamed("Next", set(stepped) - {"notice"}, _fields(http_models.NextOut)), _fields(http_models.NextOut)
    )
    assert stepped["artwork_id"] == "wrk_1"


def test_the_scene_projections_carry_the_same_field_names():
    """`GET /api/scenes/live` and `art_display(action='scenes')` read one scene, its walls included."""
    from arrt.persistence.records import Scene, SceneLifetime, SceneStatus
    from arrt.programming.display import SceneWall
    from arrt.programming.display_state import ScreenState

    scene = Scene(
        id="scn_1", status=SceneStatus.ENDED, created_at=WHEN, lifetime=SceneLifetime.HOLD, starts_at=WHEN, ended_at=WHEN
    )
    wall = SceneWall(
        wall_id="wal_1",
        wall_name="Hall",
        work_id="wrk_1",
        title="Golconda",
        reached=True,
        cannot_show=None,
        screen=ScreenState.SHOWING_ART,
    )

    projected = bindings._scene_projection(scene, [wall])

    check_parity("Scene", set(projected), _fields(http_models.SceneOut))
    check_parity(
        "SceneWall",
        check_renamed("SceneWall", set(projected["walls"][0]), _fields(http_models.SceneWallOut)),
        _fields(http_models.SceneWallOut),
    )
    assert projected["walls"][0]["artwork_id"] == "wrk_1"


def test_the_setting_projections_agree():
    """The route's `SettingOut` and `art_settings`' fields, for a stored setting, so every field is filled."""
    from arrt.library.services.settings import LABEL_UNITS, SettingSource, SettingState

    state = SettingState(LABEL_UNITS, "metric", SettingSource.STORED, WHEN, InitiatedBy.WEB_UI)

    check_parity("Setting", set(bindings._setting_fields(state)), _fields(http_models.SettingOut))


def test_the_unattended_projections_agree():
    from decimal import Decimal

    from arrt.library.services.unattended import Refusal, Standing

    standing = Standing(
        switched_on=True, allowance_usd=Decimal(5), spent_usd=Decimal(1), refusal=Refusal.ALLOWANCE_SPENT, sentence="s"
    )

    check_parity("UnattendedStanding", set(bindings._unattended_fields(standing)), _fields(http_models.UnattendedOut))


#: MCP's `run_direct_cost_usd`, which `SpendOut`'s docstring leaves off HTTP by
#: decision: the browser reads that figure off the run record.
MCP_ONLY_ON_SPEND = frozenset({"run_direct_cost_usd"})


def test_the_spend_projections_agree_but_for_the_named_fields():
    from decimal import Decimal
    from types import SimpleNamespace

    from arrt.library.services.runner import SpendReport

    report = SpendReport(scope="run", cost_usd=Decimal("0.05"), run_id="r1", run_direct_usd=Decimal("0.01"), unknown_cost_calls=1)
    services = SimpleNamespace(runner=SimpleNamespace(spend_report=lambda **_: report))

    tool = bindings._spend(services, {"run_id": "r1"})
    projected = set(tool) - {"success"}
    assert projected >= MCP_ONLY_ON_SPEND, "an MCP-only field named here that MCP no longer has is a stale exemption"
    check_parity("Spend", projected - MCP_ONLY_ON_SPEND, _fields(http_models.SpendOut))
    # Value for value: the unknown-cost count and "at least" in words (Chunk 35's), on both since Chunk 53.
    route = http_api._spend(report).model_dump()
    assert {name: tool[name] for name in route} == route
    assert (tool["unknown_cost_calls"], tool["summary"]) == (1, report.summary)
    assert tool["summary"].startswith("at least")


def test_the_spend_history_agrees_value_for_value():
    """`art_spend(action='history')` is `GET /api/spend`, by name and value, at every depth.

    A month with a kind of spending, a Get and a call whose cost is unknown, so
    no list is the empty one every shape agrees on.
    """
    from decimal import Decimal

    from arrt.library.services import spend_history
    from arrt.library.services.discovery import SpendTotal
    from arrt.persistence.discovery_records import SpendCategory

    run = DiscoveryRun(
        id="r1",
        kind=RunKind.DISCOVERY,
        initiated_by=InitiatedBy.MCP_CLIENT,
        status=RunStatus.COMPLETED,
        approval_required=False,
        started_at=WHEN,
        intent_text="Hokusai's waves",
        watch_id="w1",
    )
    floor = SpendTotal(cost_usd=Decimal("0.42"), unknown_calls=2)
    history = spend_history.SpendHistory(
        months=[
            spend_history.SpendMonth(
                year=2026,
                month=8,
                total=floor,
                categories=[spend_history.SpendByCategory(category=SpendCategory.DISCOVERY_TOKENS, calls=5, total=floor)],
                gets=[spend_history.SpendOnGet(run=run, calls=5, total=floor)],
                unknown_calls=[
                    spend_history.UnknownCostCall(
                        spend_id="s1", category=SpendCategory.DISCOVERY_TOKENS, occurred_at=WHEN, model_id="m/1", run_id="r1"
                    )
                ],
            )
        ],
        older_months=3,
    )

    tool = bindings._spend_history_fields(history)
    route = http_api._spend_history(history).model_dump()

    check_parity("SpendHistory", set(tool), _fields(http_models.SpendHistoryOut))
    check_parity("SpendMonth", set(tool["months"][0]), _fields(http_models.SpendMonthOut))
    check_parity("SpendByCategory", set(tool["months"][0]["categories"][0]), _fields(http_models.SpendByCategoryOut))
    check_parity("SpendOnGet", set(tool["months"][0]["gets"][0]), _fields(http_models.SpendOnGetOut))
    check_parity("UnknownCostCall", set(tool["months"][0]["unknown_calls"][0]), _fields(http_models.UnknownCostCallOut))
    assert tool == route
    assert tool["months"][0]["summary"] == floor.words
    assert floor.words.startswith("at least")


def test_the_watch_projections_agree_value_for_value():
    """`WatchOut` and `art_watches`' fields, for a Watch with every field filled, compared by value, not only by name."""
    from decimal import Decimal

    from arrt.library.services.settings import Cadence
    from arrt.library.services.watches import WatchStanding
    from arrt.persistence.discovery_records import RunStatus, Watch

    class Rules:
        def cadence_of(self, _watch):
            return Cadence.WEEKLY

        def effective_cap(self, _watch):
            return Decimal("1.50")

        def standing(self, watch):
            return WatchStanding(
                watch=watch,
                cadence=Cadence.WEEKLY,
                last_run_status=RunStatus.FAILED,
                next_due_at=WHEN,
                overdue=True,
                spent_usd=Decimal("0.4"),
                cap_usd=Decimal("1.50"),
                in_flight=False,
                sentence="s",
            )

    watch = Watch(
        id="w",
        intent_text="words",
        enabled=False,
        created_at=WHEN,
        created_by=InitiatedBy.MCP_CLIENT,
        updated_at=WHEN,
        updated_by=InitiatedBy.WEB_UI,
        cadence="weekly",
        monthly_cap_usd=Decimal("2.5"),
        last_attempt_at=WHEN,
        last_run_id="r",
        last_refusal="cap_spent",
    )

    over_mcp = bindings._watch_fields(Rules(), watch)
    check_parity("Watch", set(over_mcp), _fields(http_models.WatchOut))
    assert over_mcp == http_api._watch(Rules(), watch).model_dump()
    assert (over_mcp["monthly_cap_usd"], over_mcp["effective_cap_usd"]) == ("2.50", "1.50")
    assert (over_mcp["spent_usd"], over_mcp["last_run_status"], over_mcp["overdue"]) == ("0.40", "failed", True)


# -- every read route has a twin, or a reason it has none --------------------------------
#
# The tests above hold the fields of records both surfaces answer. Nothing held
# the routes themselves against the actions until wave 2b's Chunk 53: `GET
# /api/spend` landed with no MCP twin and no exemption, and nothing said so.
# These tables are read against the application's own routes (`create_app`), so
# a new read route fails by name until it is paired or given a reason here, and
# an entry naming a route or an action that no longer exists fails as stale.
#
# A page (`http/pages.py`) and a Player's route (`http/player.py`, the
# contract's) are classed by the router that serves them, not listed: neither is
# a read an agent makes. Everything else a GET answers is listed below.

#: Each read route and the MCP action that answers the same question.
READ_ROUTE_TWINS: dict[str, tuple[str, str]] = {
    "/api/works": ("art_catalogue", "list"),
    "/api/works/{artwork_id}": ("art_catalogue", "get"),
    "/api/acquisitions": ("art_catalogue", "queue"),
    "/api/acquisitions/causes": ("art_catalogue", "failures"),
    "/api/acquisitions/causes/works": ("art_catalogue", "failures"),
    "/api/topics": ("art_catalogue", "topics"),
    "/api/topics/{qid}": ("art_catalogue", "topic"),
    "/api/history": ("art_catalogue", "history"),
    "/api/artists/{artist_id}/registry": ("art_discovery", "artist"),
    "/api/registry/artists/{qid}": ("art_discovery", "artist"),
    "/api/registry/search": ("art_discovery", "search"),
    "/api/registry/artists/{qid}/similar": ("art_discovery", "similar_artists"),
    "/api/registry/works/{qid}": ("art_discovery", "work"),
    "/api/registry/works/{qid}/look": ("art_discovery", "look"),
    "/api/registry/topics": ("art_discovery", "find_topics"),
    "/api/topics/{qid}/registry": ("art_discovery", "topic"),
    "/api/topics/{qid}/works": ("art_discovery", "topic"),
    "/api/topics/{qid}/artists": ("art_discovery", "topic"),
    "/api/sources": ("art_discovery", "source_plugins"),
    "/api/estimate": ("art_discovery", "estimate"),
    "/api/runs": ("art_discovery", "list_runs"),
    "/api/runs/{run_id}": ("art_discovery", "status"),
    "/api/runs/{run_id}/spend": ("art_discovery", "spend"),
    "/api/runs/{run_id}/candidates": ("art_review", "list_works"),
    "/api/candidates/{work_id}": ("art_review", "get_work"),
    "/api/candidates/{work_id}/images": ("art_review", "list_images"),
    "/api/candidates/{work_id}/wikidata-matches": ("art_review", "wikidata_matches"),
    "/api/wanted": ("art_review", "list_wanted"),
    "/api/sightings/hosts": ("art_review", "sighting_hosts"),
    "/api/themes": ("art_theme", "list"),
    "/api/themes/{theme_id}": ("art_theme", "get"),
    "/api/walls": ("art_display", "walls"),
    "/api/exclusions": ("art_display", "kept_off"),
    "/api/scenes/live": ("art_display", "scenes"),
    "/api/manifest": ("art_display", "preview"),
    "/api/health": ("art_display", "status"),
    "/api/clients": ("art_players", "clients"),
    "/api/affinities": ("art_taste", "list"),
    "/api/settings": ("art_settings", "list"),
    "/api/unattended": ("art_settings", "unattended"),
    "/api/watches": ("art_watches", "list"),
    "/api/watches/{watch_id}": ("art_watches", "get"),
    "/api/spend": ("art_spend", "history"),
}

#: Read routes no agent makes, by design, each with why.
READS_NOT_FOR_AN_AGENT: dict[str, str] = {
    "/healthz": "a container's liveness probe; it answers 'ok' and reads nothing",
    "/openapi.json": "the framework's schema of /api, for a developer; the MCP surface describes itself (action='help')",
    "/docs": "the framework's page over that schema, for a developer",
    "/docs/oauth2-redirect": "the framework's page over that schema, for a developer",
    "/redoc": "the framework's page over that schema, for a developer",
    "/api/works/{artwork_id}/thumbnail": "image bytes for an <img>; art_catalogue answers ids, not pictures",
    "/api/works/{artwork_id}/wall-preview": "image bytes for an <img>; art_display(action='preview') says what a wall would show",
    "/api/candidate-images/{image_id}/preview": "image bytes for an <img>; art_review inlines the picture as an image block",
    "/api/registry/works/{qid}/look/pictures/{key}": "image bytes for an <img>; art_discovery(action='look') inlines them",
    "/api/ask": "Ask is the browser's agent over this same surface; an agent asking it would ask itself",
    "/api/ask/threads/{thread_id}": "an Ask thread, the browser's conversation with that agent",
}

#: Read routes an agent would ask and the surface does not answer yet: owed,
#: each with what it is. Recorded in the Chunk 53 report as follow-up work; none
#: is a field or route wave 2b added, which the tables above all twin.
READS_OWED_TO_MCP: dict[str, str] = {
    "/api/artists": "the Library's artists, with what each holds; art_catalogue lists works, filterable by artist_id",
    "/api/artists/{artist_id}": "one Library artist, with what they hold and the work they are pictured by",
    "/api/works/{artwork_id}/mat": "a work's mat colours, newest first; set_mat_color writes one and answers it",
    "/api/works/{artwork_id}/placements": "which themes hold a work and where each hangs; art_theme(action='get') is per theme",
    "/api/sources/yields": "what each source plugin has given the Library; source_plugins is how each is doing",
    "/api/budget": "what is left of the month's budget, read from the provider's key",
}


def check_routes_paired(
    routes: set[str],
    twins: dict[str, tuple[str, str]],
    not_for_an_agent: dict[str, str],
    owed: dict[str, str],
    actions: set[tuple[str, str]],
) -> None:
    """Raise unless every read route is in exactly one table, each entry names a route there is, and each twin an action."""
    tables = (("twinned", set(twins)), ("not for an agent", set(not_for_an_agent)), ("owed", set(owed)))
    unplaced = sorted(routes - set().union(*(names for _, names in tables)))
    assert not unplaced, (
        f"the read routes {unplaced} have no MCP twin and no reason they have none. Pair each with the action "
        "that answers it, or name it as not for an agent or as owed, with why."
    )
    for name, names in tables:
        stale = sorted(names - routes)
        assert not stale, f"{stale} is listed as {name}, and no such read route is served: delete it"
    for (first, a), (second, b) in [(x, y) for i, x in enumerate(tables) for y in tables[i + 1 :]]:
        assert not a & b, f"{sorted(a & b)} is listed both as {first} and as {second}"
    missing = sorted(
        f"{route} -> {tool}(action={action!r})" for route, (tool, action) in twins.items() if (tool, action) not in actions
    )
    assert not missing, f"{missing}: no such action answers it"
    assert all(reason.strip() for reason in (*not_for_an_agent.values(), *owed.values()))


def _read_routes(app) -> set[str]:
    """Every GET the application answers that is not a page's or a Player's, from the application itself.

    An included router is walked into (FastAPI 0.140 keeps it whole, as an
    entry holding `original_router`, where earlier releases copied its routes
    flat), and the pages' and the Player's routers are left out by identity.
    A mount (`/mcp`, `/static`) is not a route and is not read.
    """
    from starlette.routing import Route

    from arrt.http import pages, player

    found: set[str] = set()
    pending = list(app.routes)
    while pending:
        route = pending.pop()
        included = getattr(route, "original_router", None)
        if included is not None:
            if included not in (pages.router, player.router):
                pending.extend(included.routes)
        elif isinstance(route, Route) and "GET" in (route.methods or ()):
            found.add(route.path)
    return found


def test_every_read_route_has_an_mcp_twin_or_a_reason_it_has_none(services):
    from arrt.app import create_app

    routes = _read_routes(create_app(services))
    # Anchors, so a walk that read nothing cannot pass: one route of each router read, none of the two left out.
    assert {"/api/spend", "/api/ask", "/healthz"} <= routes, "the routes were not read, so this would pass vacuously"
    assert not {"/client", "/walls/{wall_id}/manifest/v{major}", "/"} & routes, "a Player's route or a page was read"
    check_routes_paired(routes, READ_ROUTE_TWINS, READS_NOT_FOR_AN_AGENT, READS_OWED_TO_MCP, set(bindings.BINDINGS))


def test_a_read_route_with_neither_twin_nor_reason_is_refused_by_name():
    with pytest.raises(AssertionError, match=r"the read routes \['/api/new'\] have no MCP twin"):
        check_routes_paired(
            {"/api/new", "/api/walls"}, {"/api/walls": ("art_display", "walls")}, {}, {}, {("art_display", "walls")}
        )


def test_a_twin_naming_an_action_that_does_not_exist_is_refused():
    with pytest.raises(AssertionError, match="no such action answers it"):
        check_routes_paired({"/api/walls"}, {"/api/walls": ("art_display", "wallz")}, {}, {}, {("art_display", "walls")})


def test_an_entry_for_a_route_no_longer_served_is_refused():
    with pytest.raises(AssertionError, match=r"\['/api/gone'\] is listed as owed, and no such read route"):
        check_routes_paired(
            {"/api/walls"}, {"/api/walls": ("art_display", "walls")}, {}, {"/api/gone": "x"}, {("art_display", "walls")}
        )


def test_a_route_in_two_tables_is_refused():
    with pytest.raises(AssertionError, match="listed both as twinned and as owed"):
        check_routes_paired(
            {"/api/walls"}, {"/api/walls": ("art_display", "walls")}, {}, {"/api/walls": "x"}, {("art_display", "walls")}
        )
