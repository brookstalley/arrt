"""The MCP tool surface, asserted against a real server over real HTTP.

This is the level that matters most on this product: the MCP surface is the
only one with external consumers, and the only one where a change that looks
cosmetic — rewording a description — is a real behavioural change.
"""

import json
import re
from datetime import datetime
from importlib.metadata import version

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.ask.prompt import ASK_SCOPE
from arrt.library.facade import PlayableWork, UnplayableReason
from arrt.mcp.registry import DESCRIPTION_BUDGET_BYTES
from arrt.mcp.tools import ART_DISPLAY, ART_PLAYERS, ART_THEME, TOOLS, TOOLS_BY_NAME
from arrt.persistence.records import FetchStatus, VocabularyKind
from arrt.services.errors import ServiceError


def _services_clock() -> datetime:
    raise AssertionError("the services' clock is read only inside a test (`_now_is_the_services`)")


@pytest.fixture(autouse=True)
def _now_is_the_services(shared_clock, monkeypatch):
    """`_now` reads the services' clock (`shared_clock`), so what a test writes beside them is on their time."""
    monkeypatch.setitem(globals(), "_services_clock", shared_clock)


def _now() -> datetime:
    return _services_clock()


#: A regression here silently renames the entire MCP tool surface for every
#: client. Tool names are a frozen contract: never renamed, never removed.
#:
#: **The set may grow, and `art_taste` is the case that proved it.** Adding a
#: name here is a deliberate widening of the surface — `api-contract.md` names
#: the tool and the operator's decision to have it — where changing one is the
#: regression this guards. A new entry therefore belongs in the same commit as
#: the tool; an *edited* one never belongs at all.
#:
#: `art_players` joined with the one break the owner allowed (ruling
#: 3 of 2026-11-19): every act on a wall went to `art_display`, and the Player
#: actions left it for this tool so the wall acts fit its description budget.
#: No name here was renamed or removed.
#:
#: `art_spend` joined after the break, as an addition:
#: System › Spend's history had no honest home on an existing tool, and
#: `art_discovery`'s description was at its budget (`tools.py`'s `ART_SPEND`).
FROZEN_TOOL_NAMES = {
    "art_catalogue",
    "art_discovery",
    "art_display",
    "art_players",
    "art_review",
    "art_settings",
    "art_spend",
    "art_taste",
    "art_theme",
    "art_watches",
}


@pytest.fixture
async def tools(server_url):
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        listed = await session.list_tools()
    return {tool.name: tool for tool in listed.tools}


async def test_the_server_boots_and_a_real_client_completes_the_handshake(server_url):
    # The mounted MCP server has no lifespan of its own — Starlette does not
    # run a mounted sub-app's. If the host application failed to drive the
    # session manager, every request below would raise "Task group is not
    # initialized" instead of answering.
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        result = await session.initialize()

    assert result.serverInfo.name == "arrt"
    # The server reports its own version. Left unset the SDK reports its own,
    # so a client asking what it is talking to learns the protocol library's
    # version instead of the product's.
    assert result.serverInfo.version == version("arrt")


async def test_the_tool_names_are_exactly_these(tools):
    assert set(tools) == FROZEN_TOOL_NAMES


async def test_the_registry_and_the_wire_agree_on_the_tool_list(tools):
    assert set(tools) == {tool.name for tool in TOOLS}


def oversized(descriptions: dict[str, str]) -> dict[str, int]:
    """Each description past the client's budget, by its size in bytes (UTF-8, as the client counts)."""
    return {name: len(text.encode()) for name, text in descriptions.items() if len(text.encode()) > DESCRIPTION_BUDGET_BYTES}


async def test_every_description_fits_the_clients_budget(tools):
    # Claude Code truncates a tool description at 2 KB. Past that the action
    # menu is cut mid-word and the model chooses from a list it cannot see.
    assert oversized({name: tool.description for name, tool in tools.items()}) == {}


def test_the_budget_is_met_at_2048_bytes_and_broken_at_2049():
    """The edge, in bytes and not characters: a '—' is three of them."""
    assert DESCRIPTION_BUDGET_BYTES == 2048
    at = "—" * 682 + "xx"
    assert len(at.encode()) == 2048
    assert oversized({"at": at, "over": at + "x"}) == {"over": 2049}


async def test_every_tool_declares_its_annotations(tools):
    # Omitted annotations default to the worst case — destructive and
    # open-world — which costs a confirmation prompt on every call.
    for name, tool in tools.items():
        assert tool.annotations is not None, name
        assert tool.annotations.title, name
        assert tool.annotations.readOnlyHint is not None, name
        assert tool.annotations.destructiveHint is not None, name
        assert tool.annotations.openWorldHint is not None, name


async def test_exactly_the_tools_that_leave_the_machine_declare_an_open_world(tools):
    """`openWorldHint` is how a client decides a call warrants confirmation, so it
    has to describe reach rather than intent.

    **This test read `== {"art_discovery"}` and was named for the money tool until
    2026-08-03.** Those were the same set when it was written and are not now:
    `art_catalogue` gained `retry_acquisition`, which fetches an arbitrary museum
    URL, and then `set_mat_color`, which asks a vision model. The tool went on
    declaring a closed world through both, understating its reach to every client
    that reads the hint — and *this test passing* was part of why, because it
    asserted the old set rather than the property.

    Both sides are named below, so it still discriminates: the honest failure mode
    is a tool that grows an outward-reaching action and keeps a stale flag, and a
    one-sided assertion would not catch the reverse — a purely local tool marked
    open-world, which costs a confirmation prompt on every call forever.
    """
    open_world = {name for name, tool in tools.items() if tool.annotations.openWorldHint}

    # Reaches outside: discovery searches the web and queries museums; the
    # catalogue re-fetches images and asks a vision model for mat colours.
    assert open_world == {"art_discovery", "art_catalogue"}
    # Purely local: reviewing candidates, arranging themes, writing the manifest,
    # recording what the curator likes and changing the household's settings all
    # touch this machine's catalogue and its own filesystem.
    assert {
        "art_review",
        "art_theme",
        "art_display",
        "art_players",
        "art_taste",
        "art_settings",
        "art_watches",
        # The spend ledger is this machine's; reading it asks the provider nothing.
        "art_spend",
    } & open_world == set()


async def test_every_tool_requires_an_action_and_nothing_else(tools):
    for name, tool in tools.items():
        assert tool.inputSchema["required"] == ["action"], name
        assert "action" in tool.inputSchema["properties"], name


async def test_every_tool_offers_help_in_its_action_enum(tools):
    for name, tool in tools.items():
        assert "help" in tool.inputSchema["properties"]["action"]["enum"], name


async def test_every_description_lists_the_actions_the_schema_allows(tools):
    # Prose and schema cannot drift: both are generated from one record, and
    # this is the assertion that says so.
    for name, tool in tools.items():
        for action in tool.inputSchema["properties"]["action"]["enum"]:
            assert action in tool.description, f"{name} description omits {action!r}"


# -- a tip is contract text, and must not describe a narrower rule than the code --
#
# Two tips in two consecutive review rounds claimed behaviour the service did not
# have: `activate` said it did not publish when it does, and `show_now` said only
# archived works were refused after the refusal widened. Both were invisible to
# the assertions above, which pin schema and description but never tip text — and
# the tip is the sentence a model reads before deciding whether to call.

#: The word a caller reading the tip would recognise, per cause `show_now` can
#: refuse for. Deliberately not the whole sentence: the tip summarises, and
#: pinning it verbatim would make every wording improvement a failure. What must
#: hold is that no cause is missing from the tip altogether.
#:
#: **Every token must be distinct, and that is asserted below.** Two reasons
#: sharing one word silently satisfies the row for whichever is not actually named
#: — the first version of this table gave both rendition reasons "render", so a
#: stale render went unmentioned in the tip while this guard reported it covered.
_SHOW_NOW_TIP_PREPARES_FOR = {
    UnplayableReason.ARCHIVED: "archived",
    UnplayableReason.NO_ORIGINAL: "missing its picture",
    UnplayableReason.NO_MAT_COLOR: "mat colour",
    UnplayableReason.NO_RENDITION: "copy for the walls",
    # A stale render is present rather than missing, so "render" alone does not
    # describe it and would be satisfied by the row above.
    UnplayableReason.STALE_RENDITION: "earlier acquisition",
    # An id that resolves to nothing. Refused before the facade existed too, by
    # the catalogue's own lookup; naming it as a reason is what put it in the tip.
    # "library holds": the tip says ruling 2's word.
    UnplayableReason.NOT_IN_CATALOGUE: "library holds",
}


def _exclusion_for(library, work):
    """What the readiness rule actually says about this work."""
    excluded = library.playable([work.id])[work.id]
    assert not isinstance(excluded, PlayableWork), "this work is displayable, so the row it stands for is untested"
    return excluded


def _show_now_tips() -> str:
    action = next(entry for entry in ART_DISPLAY.actions if entry.name == "show_now")
    return " ".join(action.tips).lower()


def test_every_reason_show_now_can_refuse_for_is_named_in_its_tip():
    """A new exclusion cause must not silently outrun the text that documents it.

    This fails the moment someone adds another `UnplayableReason`, which is the
    point: readiness widened once already and the tip did not follow.
    """
    missing = [reason for reason in UnplayableReason if reason not in _SHOW_NOW_TIP_PREPARES_FOR]
    assert not missing, f"exclusion reasons with no entry in this table: {missing}"

    tokens = list(_SHOW_NOW_TIP_PREPARES_FOR.values())
    assert len(set(tokens)) == len(
        tokens
    ), f"two reasons share a token in this table, which makes one row pass on the other's word: {tokens}"

    tips = _show_now_tips()
    for reason, expected in _SHOW_NOW_TIP_PREPARES_FOR.items():
        assert expected in tips, f"the show_now tip does not prepare a caller for {reason.value!r}"


@pytest.mark.parametrize(
    ("reason", "unready"),
    [
        (UnplayableReason.NO_ORIGINAL, {"original": False}),
        (UnplayableReason.NO_MAT_COLOR, {"mat": False}),
        (UnplayableReason.NO_RENDITION, {"master": False}),
    ],
)
def test_each_documented_refusal_is_one_the_service_actually_raises(display, library, ready_work, reason, unready, wall_id):
    """The other half: the tip must not promise a refusal the code does not make.

    Driving the real service rather than reading the table above, so this pins
    tip text to behaviour rather than to itself. The state is asserted through
    `assess` — the reason, not a noun in the message — because two reasons can
    share a word and then this proves nothing about which one fired.
    """
    work = ready_work(**unready)

    excluded = _exclusion_for(library, work)
    assert excluded.reason is reason, "the fixture did not reach the state this row is about"

    with pytest.raises(ServiceError) as refused:
        display.show_work_now(wall_id, work.id)

    # The tip promises the refusal uses the same words sync uses for an
    # excluded work. That is the claim under test, not a shared noun.
    assert excluded.detail in str(refused.value)


def test_an_archived_work_is_refused_in_the_words_the_tip_uses(service, display, library, ready_work, wall_id):
    work = ready_work()
    service.archive_artwork(work.id)

    excluded = _exclusion_for(library, work)
    assert excluded.reason is UnplayableReason.ARCHIVED

    with pytest.raises(ServiceError) as refused:
        display.show_work_now(wall_id, work.id)

    assert excluded.detail in str(refused.value)
    assert "archived" in str(refused.value).lower()


def test_a_stale_render_is_refused_in_the_words_the_tip_uses(service, display, library, ready_work, wall_id):
    """Re-acquiring leaves the previous render in place, and it is no longer of this image."""
    work = ready_work()
    source = service.list_sources(work.id)[0]
    service.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path=f"raw/{work.id}.tif",
        width=6000,
        height=4000,
        byte_size=90_000_000,
        content_hash="a-later-acquisition",
        fetch_status=FetchStatus.OK,
    )

    # On the reason, not on "render": NO_RENDITION's message says "rendered" too,
    # so a noun match would pass on the wrong exclusion entirely.
    excluded = _exclusion_for(library, work)
    assert excluded.reason is UnplayableReason.STALE_RENDITION

    with pytest.raises(ServiceError) as refused:
        display.show_work_now(wall_id, work.id)

    assert excluded.detail in str(refused.value)
    assert "earlier acquisition" in str(refused.value).lower()


# -- the wall a refusal turns on must be in the text that documents it ----------
#
# `delete_theme` refuses, and the *reason* it once gave changed underneath: "the active theme, while another exists" became "a theme
# hanging on any wall". A refusal that changes without its tip changing is the
# drift the guards above exist for, and it has now happened twice on this file's
# watch, so the delete tip gets the same treatment `show_now`'s did.

#: What every cause `delete_theme` can refuse for must be recognisable by in the
#: tip. One cause today, which is the whole shape of the generalisation: the
#: theme-count clause went away, so a table with a `last theme` row in it would be
#: documenting a rule the code no longer has.
_DELETE_TIP_PREPARES_FOR = {"hung on a wall": ("hanging", "wall")}

#: Words the retired rule used, which must not survive anywhere in this tool's
#: prose. Asserting the absence rather than only the presence: a tip can name the
#: new rule and go on stating the old one beside it, and a caller reading both
#: learns a rule the service will not honour.
_RETIRED_SINGLE_WALL_PHRASES = (
    "the active theme",
    "while another exists",
    "whichever is oldest",
    "exactly one theme is active",
    "and the only one",
)


def _tool_prose(record) -> str:
    """Every sentence a client can read off one tool record."""
    parts = [record.summary]
    for action in record.actions:
        parts.extend([action.description, *action.tips])
    return " ".join(parts).lower()


def test_the_delete_tip_states_the_refusal_the_service_actually_makes(display, wall_id, ready_work):
    """Driven through the real service, so the tip is pinned to behaviour.

    The check runs both ways round. The tip has to prepare a caller for the
    refusal that fires, and the service has to actually fire it — a tip promising
    a refusal nobody makes is the same defect wearing the other face.
    """
    theme = display.add_theme(name="Late night")
    display.add_to_theme(theme_id=theme.id, artwork_id=ready_work().id)
    display.activate_theme(theme.id, wall_id=wall_id)

    with pytest.raises(ServiceError) as refused:
        display.delete_theme(theme.id)

    action = next(entry for entry in ART_THEME.actions if entry.name == "delete")
    tips = " ".join(action.tips).lower()
    for cause, tokens in _DELETE_TIP_PREPARES_FOR.items():
        for token in tokens:
            assert token in tips, f"the delete tip does not prepare a caller for {cause!r}"
    # And the tip's remedy is one the surface offers: an instruction naming an
    # action that does not exist is worse than none. Both are the wall tool's,
    # and the tip names the tool with them.
    assert {entry.name for entry in ART_DISPLAY.actions} >= {"activate", "unhang"}
    assert "art_display(action='activate')" in tips
    assert "art_display(action='unhang')" in tips
    # The message itself, whole, the same treatment the `unhang` notice gets and
    # for the same reason: `api-contract.md` calls this sentence normative and
    # asks two things of it — that it names the walls, and that it offers *both*
    # ways out. A substring check on the wall's name leaves the remedy clause
    # deletable with the suite still green, and the remedy is the half § Errors
    # teach actually binds. The wall's name is read off the service rather than
    # written as a literal, because the default happens to be "The wall": a
    # hardcoded copy would pass on the name while asserting nothing about a wall
    # being named at all, and would fail the day the default is reconfigured.
    assert str(refused.value) == (
        f"Theme 'Late night' is hanging on {display.get_wall(wall_id).name!r}. Hang another theme there first, "
        "or take this one down, so that what those walls show next is a choice rather than whatever was on "
        "them before."
    )


def test_the_refusal_no_longer_fires_for_the_rule_it_used_to(display, wall_id):
    """The other half of the generalisation: a theme that hangs nowhere is deletable.

    It was refused while it was the active theme and another existed, and that
    clause is gone — so a second theme, unhung, deletes even though a theme is
    hanging elsewhere in the catalogue.
    """
    hanging = display.add_theme(name="Late night")
    spare = display.add_theme(name="Daylight")
    display.activate_theme(hanging.id, wall_id=wall_id)

    display.delete_theme(spare.id)

    assert [theme.id for theme in display.list_themes()] == [hanging.id]


def test_the_last_theme_becomes_deletable_by_being_taken_down(display, wall_id):
    """The route the tip points at has to work, or the refusal is a dead end.

    Deleting the last theme was permitted even while active, ratified 2026-08-11
    *because* there was no way to take one down — so a curator could never empty
    the catalogue. The refusal is absolute now, and this is what pays for that.
    """
    only = display.add_theme(name="Late night")
    display.activate_theme(only.id, wall_id=wall_id)

    with pytest.raises(ServiceError):
        display.delete_theme(only.id)

    display.clear_wall(wall_id)
    display.delete_theme(only.id)

    assert display.list_themes() == []


#: Every way `add_wall` can refuse, and a word a caller reading the tip would
#: recognise it by. The wall creator is the newest write on this tool and the
#: only one that was shipped with tips naming no refusal at all — this table is
#: what stops a third cause arriving the same way.
_ADD_WALL_TIP_PREPARES_FOR = {"a blank name": "empty", "a name already taken": "taken"}


def test_the_add_wall_tips_state_the_refusals_the_service_actually_makes(display):
    """Both refusals driven through the real service, like the delete tip above.

    A model reads the tips, not the docstring, and it reaches this action with a
    name a human said out loud — which is exactly how a duplicate arrives. The
    check runs both ways: the tip must prepare the caller, and the service must
    actually refuse, because a tip promising a refusal nobody makes teaches the
    same wrong lesson.
    """
    action = next(entry for entry in ART_DISPLAY.actions if entry.name == "add_wall")
    tips = " ".join(action.tips).lower()
    for cause, token in _ADD_WALL_TIP_PREPARES_FOR.items():
        assert token in tips, f"the add_wall tip does not prepare a caller for {cause!r}"

    with pytest.raises(ServiceError) as blank:
        display.add_wall(name="   ")
    assert "empty" in str(blank.value)

    display.add_wall(name="Study")
    with pytest.raises(ServiceError) as duplicate:
        display.add_wall(name="Study")
    assert "Study" in str(duplicate.value)


@pytest.mark.parametrize("record", TOOLS, ids=lambda record: record.name)
def test_no_tool_still_teaches_the_single_wall_rule_it_replaced(record):
    """Retiring a rule is a sweep of the sentences that taught it, not a local edit.

    The prose is the contract a model reads, and a retired rule left in it is
    indistinguishable from a live one to the only reader that matters.
    """
    prose = _tool_prose(record)
    surviving = [phrase for phrase in _RETIRED_SINGLE_WALL_PHRASES if phrase in prose]

    assert not surviving, f"{record.name} still teaches the retired single-wall rule: {surviving}"


#: Every action that changes one wall. Written out rather than derived from the
#: parameter lists, because deriving it from what the code declares would make
#: this test agree with any answer the code gave — including an action that
#: quietly stopped naming a wall.
_ACTS_ON_ONE_WALL = {
    ("art_display", "activate"),
    ("art_display", "unhang"),
    ("art_display", "hang_selection"),
    ("art_display", "not_again"),
    ("art_display", "preview"),
    ("art_display", "sync"),
    ("art_display", "show_now"),
    ("art_display", "next"),
    ("art_display", "set_mat_mode"),
    ("art_players", "assign_wall"),
    ("art_players", "unassign_wall"),
}


#: Every action that acts on one client, for the reason `_ACTS_ON_ONE_WALL` is
#: written out: derived from the declarations, it would agree with any answer.
_ACTS_ON_ONE_CLIENT = {
    ("art_players", "rename_client"),
    ("art_players", "remove_client"),
    ("art_players", "issue_client_token"),
    ("art_players", "assign_wall"),
}


@pytest.mark.parametrize(("tool_name", "action_name"), sorted(_ACTS_ON_ONE_CLIENT))
def test_every_act_against_a_client_names_it_and_says_where_its_id_comes_from(tool_name, action_name):
    """A client id is obtainable from `action='clients'` and from nothing else, so each says so."""
    action = next(entry for entry in TOOLS_BY_NAME[tool_name].actions if entry.name == action_name)

    client = next((param for param in action.params if param.name == "client_id"), None)
    assert client is not None, f"{tool_name}(action={action_name!r}) does not require a client"
    assert client.required, f"{tool_name}(action={action_name!r}) does not require a client"
    assert "client_id=" in action.example
    assert "action='clients'" in " ".join([client.description, *action.tips])


def test_the_players_tool_declares_itself_destructive_since_it_can_forget_a_client():
    """`remove_client` and `issue_client_token` cannot be undone, so the hint must not say otherwise.

    A client that auto-approves non-destructive tools would otherwise rotate a
    working Player's token, refusing it, without asking anyone. The wall tool,
    which carried them before the break, stays destructive for `delete_wall`.
    """
    assert {"remove_client", "issue_client_token"} <= set(ART_PLAYERS.action_names)
    assert ART_PLAYERS.destructive is True
    assert "delete_wall" in ART_DISPLAY.action_names
    assert ART_DISPLAY.destructive is True


#: What `art_watches(action='delete')` was said to do before the screens' word
#: for it, Forget (the vocabulary's: Forget drops a record the household made of
#: something outside, a Watch among them), reached MCP.
_RETIRED_WATCH_WORDS = ("remove a watch", "what was removed", "a deleted watch", "removes a watch")


def test_the_watches_tool_says_a_watch_is_forgotten_as_the_screens_do():
    """Watches' button is *Forget…*; an agent reading "remove" would tell the household a different act."""
    record = TOOLS_BY_NAME["art_watches"]
    delete = next(action for action in record.actions if action.name == "delete")
    prose = _tool_prose(record)

    assert delete.description.startswith("Forget a Watch")
    assert [words for words in _RETIRED_WATCH_WORDS if words in prose] == []


@pytest.mark.parametrize(("tool_name", "action_name"), sorted(_ACTS_ON_ONE_WALL))
def test_every_act_against_a_wall_names_which_wall(tool_name, action_name):
    """Required even while there is one wall and the answer is obvious.

    An action that guessed the wall is worse here than on the web surface, where
    a confirmation dialog could at least catch it. The example is asserted too:
    it is what a model copies, and one that omitted the parameter would teach a
    call the schema refuses.
    """
    record = TOOLS_BY_NAME[tool_name]
    action = next(entry for entry in record.actions if entry.name == action_name)

    wall = next((param for param in action.params if param.name == "wall_id"), None)
    assert wall is not None, f"{tool_name}(action={action_name!r}) does not take a wall"
    assert wall.required, f"{tool_name}(action={action_name!r}) makes the wall optional"
    assert "wall_id=" in action.example, f"{tool_name}(action={action_name!r})'s example omits the wall"


def test_the_walls_action_is_where_every_wall_id_comes_from(tools):
    """An action is only usable if its arguments are obtainable from something built.

    Every action above requires a `wall_id` and nothing else on the surface returns one,
    so this listing is load-bearing rather than a convenience — and the actions
    that need it say where to get it.
    """
    assert "walls" in tools["art_display"].inputSchema["properties"]["action"]["enum"]

    for tool_name, action_name in sorted(_ACTS_ON_ONE_WALL):
        record = TOOLS_BY_NAME[tool_name]
        action = next(entry for entry in record.actions if entry.name == action_name)
        wall = next(param for param in action.params if param.name == "wall_id")
        pointer = " ".join([wall.description, *action.tips]).lower()
        assert "walls" in pointer, f"{tool_name}(action={action_name!r}) never says where a wall id comes from"


def test_a_parameter_that_is_required_by_some_actions_is_described_neutrally(tools):
    """Every action's parameters are flattened onto one wire schema, and only the
    first description survives.

    `run_id` is required by `status`, `approve`, `decline` and `cancel`, and
    optional to `estimate` and `spend`. A description written for either case is
    published as though it governed both — so one that said "omit this for the
    cost of a new question" would be telling a model that omitting it is
    meaningful on the four actions where it is simply an error. What each action
    does with the parameter belongs in that action's own description and tips.
    """
    published = tools["art_discovery"].inputSchema["properties"]["run_id"]["description"]

    assert "omit" not in published.lower(), f"run_id's published description assumes one action's arity: {published!r}"
    assert "run" in published.lower()


def test_every_facet_kind_the_collection_filters_by_is_a_parameter_of_the_listing(tools):
    """The browser and the tool surface offer the same filters, or one of them lies.

    `GET /api/works` takes one repeatable parameter per facet kind, named from
    `VocabularyKind`; `art_catalogue(action='list')` declares its six by hand,
    because the useful half of each description is an example of that kind's
    *values* and the enum does not carry those. Hand-written means it can drift,
    and a seventh kind reaching the vocabulary and not this tuple would be a
    filter a curator could apply and a model could not — the exact
    agent-and-a-click disagreement the shared service layer exists to prevent.
    """
    published = tools["art_catalogue"].inputSchema["properties"]
    listing = next(action for action in TOOLS_BY_NAME["art_catalogue"].actions if action.name == "list")
    declared = {param.name for param in listing.params}

    for kind in VocabularyKind:
        assert str(kind) in declared, f"art_catalogue(action='list') takes no {kind} filter"
        assert published[str(kind)]["type"] == "array", f"{kind} is not published as a repeatable filter"
        assert published[str(kind)]["items"] == {"type": "string"}
    assert "q" in declared, "the listing offers facets and no free text"


def test_an_id_the_catalogue_does_not_hold_is_refused_in_the_words_the_tip_uses(display, library, wall_id):
    """The newest row's other half: the refusal is real, and it is the facade's sentence."""
    excluded = library.playable(["nope"])["nope"]
    assert excluded.reason is UnplayableReason.NOT_IN_CATALOGUE

    with pytest.raises(ServiceError) as refused:
        display.show_work_now(wall_id, "nope")

    assert excluded.detail in str(refused.value)


# -- what the grouping guaranteed without anyone writing it down ------------------------


@pytest.mark.parametrize("record", TOOLS, ids=lambda record: record.name)
def test_every_action_has_an_example_that_calls_it_where_it_is(record):
    """The example is what a model copies. One naming the tool an action moved from teaches a refused call."""
    for action in record.actions:
        assert action.example.startswith(
            f"{record.name}(action={action.name!r}"
        ), f"{record.name}(action={action.name!r})'s example is {action.example!r}"


def test_every_action_ask_may_call_is_one_the_surface_takes():
    """`ASK_SCOPE` names tools and actions by string; a regroup must not leave one pointing at nothing."""
    for tool_name, actions in ASK_SCOPE.items():
        assert tool_name in TOOLS_BY_NAME, f"Ask may call {tool_name}, which the surface does not have"
        missing = actions - set(TOOLS_BY_NAME[tool_name].action_names)
        assert not missing, f"Ask may call {tool_name}'s {sorted(missing)}, which it does not take"


#: What no description may carry, each with why. An environment variable's name
#: is the operator's, read in the deployment's files, never a step an agent can
#: take (`art_catalogue`'s topics tip once named one). The owner's rulings
#: 1 and 2 of 2026-11-19: a theme, never a playlist, and the household's holdings
#: are the Library, never the collection or the catalogue. `art_catalogue` is a
#: tool name, frozen, and the `\b` keeps it out: `_` is a word character.
_NOT_IN_A_DESCRIPTION: dict[str, re.Pattern[str]] = {
    "an environment variable's name": re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b"),
    "'playlist' (ruling 1: theme)": re.compile(r"(?i)\bplaylists?\b"),
    "'catalogue' (ruling 2: the Library)": re.compile(r"(?i)\bcatalog"),
    "'collection' (ruling 2: the Library)": re.compile(r"(?i)\bcollections?\b"),
}


def what_an_agent_reads(tool) -> str:
    """Every word a client shows a model of one tool: its title, its description and its whole `help`."""
    from arrt.mcp import registry

    return "\n".join((tool.title, registry.description(tool), json.dumps(registry.help_payload(tool), ensure_ascii=False)))


def refused_words(text: str) -> list[tuple[str, str]]:
    """Each thing `text` says that no description may, as (the rule, the words)."""
    return [(rule, found.group(0)) for rule, pattern in _NOT_IN_A_DESCRIPTION.items() for found in pattern.finditer(text)]


@pytest.mark.parametrize("record", TOOLS, ids=lambda record: record.name)
def test_no_description_names_a_variable_or_a_retired_word(record):
    """Over every tool: theme and the Library, and no environment variable."""
    assert refused_words(what_an_agent_reads(record)) == []


@pytest.mark.parametrize(
    ("planted", "rule"),
    [
        ("state='not_configured' means WIKIDATA_USER_AGENT is unset", "an environment variable's name"),
        ("Hang a playlist on a wall.", "'playlist' (ruling 1: theme)"),
        ("Accepting puts it in the catalogue.", "'catalogue' (ruling 2: the Library)"),
        ("Search and filter catalogued works.", "'catalogue' (ruling 2: the Library)"),
        ("The works already accepted into the Collection.", "'collection' (ruling 2: the Library)"),
    ],
)
def test_each_refused_word_is_found_when_planted(planted, rule):
    from dataclasses import replace

    tool = replace(TOOLS_BY_NAME["art_theme"], summary=planted, _by_name={})

    # The summary is in the description and in help, so it is found twice: once per place a model reads it.
    assert {found for found, _words in refused_words(what_an_agent_reads(tool))} == {rule}


def test_a_tool_name_holding_a_retired_word_is_not_refused():
    """`art_catalogue` is frozen; calling it by name is not calling the Library the catalogue."""
    assert refused_words("art_catalogue(action='list') lists the Library's works.") == []


async def test_the_spend_history_over_mcp_is_get_api_spend(server_url, services):
    """`art_spend(action='history')` against `GET /api/spend`, whole, with a known and an unknown-cost call this month."""
    import json
    from decimal import Decimal

    import httpx

    from arrt.persistence.discovery_records import CostStatus, InitiatedBy, SpendCategory

    now = _now()
    run = services.discovery.start_discovery_run(intent_text="Dalí", initiated_by=InitiatedBy.MCP_CLIENT)
    for cost, status in ((Decimal("0.0213"), CostStatus.KNOWN), (Decimal(0), CostStatus.UNKNOWN)):
        services.discovery.record_spend(
            category=SpendCategory.DISCOVERY_TOKENS,
            cost_usd=cost,
            discovery_run_id=run.id,
            model_id="the-model",
            at=now,
            cost_status=status,
        )

    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("art_spend", {"action": "history"})
    payload = json.loads(result.content[0].text)
    async with httpx.AsyncClient(base_url=server_url, timeout=30.0) as client:
        route = (await client.get("/api/spend")).raise_for_status().json()

    assert payload.pop("success") is True
    assert payload == route
    assert payload["months"][0]["summary"] == "at least $0.0213, and 1 call whose cost is unknown"
    assert [each["run_id"] for each in payload["months"][0]["gets"]] == [run.id]
