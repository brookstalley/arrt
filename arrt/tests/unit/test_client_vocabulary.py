"""The words the client has for the states the server can send it.

The browser renders enum values as sentences a curator acts on — "no wired
collection holds it" rather than `not_held`. A value with no entry in those maps
falls through to the raw token, which is a diagnostic label leaking onto a
screen: readable to whoever wrote the enum, meaningless to the person deciding
whether to re-search.

So the maps are checked against the enums rather than trusted. This is the same
bargain `test_design_tokens.py` strikes with the stylesheet: the client is not a
Python module and nothing else would notice the day a sixth reason is added, so
the check reads the real files — every module the client is built from. A member added without a sentence fails here,
which is the point at which it is cheap to write one.
"""

import re
import shutil
import subprocess

import pytest

from arrt.http.pages import STATIC_DIR
from arrt.library.services.get import SkipReason
from arrt.library.services.look import SourceState
from arrt.library.services.spending import CostTier
from arrt.library.services.topics import FACET_KINDS
from arrt.mcp.bindings import RESTORE_NOTICE
from arrt.persistence.discovery_records import (
    AffinityDerivation,
    AffinitySentiment,
    Confirmation,
    ResolutionStatus,
    RunKind,
    RunStatus,
    UnresolvedReason,
    Verdict,
    WorkProvenance,
)
from arrt.persistence.records import VocabularyKind

#: Every module the client is made of, boot and `core/` and `screens/` alike.
#:
#: Sorted so the concatenation below is stable, and gathered by glob rather than
#: listed: the client became a tree of ES modules when the navigation was
#: reshaped, and a hand-written list is a list that stops including the newest
#: screen — silently, since every check here would go on passing against the
#: modules it still knew about.
CLIENT_PATHS = sorted(STATIC_DIR.rglob("*.js"))

#: The whole client as one text. Every check below asks "does the client say
#: this", which was one file's question and is now the tree's; concatenating is
#: what keeps the question the same one after the split.
CLIENT = "\n".join(path.read_text(encoding="utf-8") for path in CLIENT_PATHS)


def test_the_client_is_more_than_one_module():
    """The glob found a tree, so every check below reads the whole client.

    A `rglob` that matched one file — or none — would leave these checks passing
    against whatever it happened to find, which is the failure mode that made the
    hand-written list unacceptable in the first place. This is the assertion that
    the gathering worked.
    """
    names = {path.relative_to(STATIC_DIR).as_posix() for path in CLIENT_PATHS}
    assert "app.js" in names, "the client's boot module is missing from what these checks read"
    assert any(name.startswith("core/") for name in names), "no core module was gathered"
    assert any(name.startswith("screens/") for name in names), "no screen module was gathered"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed; this check is opportunistic")
@pytest.mark.parametrize("path", CLIENT_PATHS, ids=lambda path: path.name)
def test_the_client_parses(path):
    """A syntax error here kills the entire browser surface and no other test notices.

    Every Python test asserts what the *server* sends and that the script is
    served; none of them runs a line of it. So a stray brace ships a page that
    loads, fetches nothing, and shows the "Loading the catalogue…" placeholder
    forever, against a fully green suite — the shape of failure this product
    exists to refuse.

    **Per module, not over the concatenation.** Two files joined end to end parse
    as neither of them — an unbalanced brace in the first would be closed by the
    second and the check would pass on a client that cannot load.

    **This is a check, not a toolchain.** It shells out to whatever `node`
    happens to be on the machine and skips when there is none, so it adds no
    dependency and no build step, and the deliberate decision against a Node
    toolchain on a Pi is untouched. It cannot say the client is *correct* — only
    that it is parseable, which is the cheapest fact worth having about a file
    nothing else executes.
    """
    result = subprocess.run(  # noqa: S603 -- a fixed argv over a repo file
        ["node", "--check", str(path)],  # noqa: S607 -- whatever node is on PATH, skipped without one
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, f"{path.name} does not parse:\n{result.stderr}"


def _literal_body(name: str) -> str:
    """The raw text inside a top-level `const <name> = { ... }` object literal.

    The two readers below both strip or extract before they answer; this is what
    is left for a literal whose values are neither bare identifiers nor strings.
    Brace-counted for the reason they are: a non-greedy pattern stops at the
    first `}` and silently reads a truncated object, and a check that reads half
    its input passes for the wrong reason.
    """
    opening = re.search(rf"^(?:export )?const {re.escape(name)} = (?={{)", CLIENT, re.MULTILINE)
    assert opening, f"the client has no top-level `const {name} = {{`"
    start = opening.end()
    depth = 0
    for index in range(start, len(CLIENT)):
        if CLIENT[index] == "{":
            depth += 1
        elif CLIENT[index] == "}":
            depth -= 1
            if depth == 0:
                return CLIENT[start + 1 : index]
    raise AssertionError(f"`{name}` is never closed")


def _object_keys(name: str) -> set[str]:
    """The keys of a top-level `const <name> = { ... }` object literal in the client.

    Brace-counted rather than matched with a non-greedy regex, for the reason
    recorded in `test_design_tokens.py`: a pattern that stops at the first `}`
    silently reads a truncated object, and a check that reads half its input
    passes for the wrong reason.
    """
    opening = re.search(rf"^(?:export )?const {re.escape(name)} = (?={{)", CLIENT, re.MULTILINE)
    assert opening, f"the client has no top-level `const {name} = {{`"
    start = opening.end()
    depth = 0
    for index in range(start, len(CLIENT)):
        if CLIENT[index] == "{":
            depth += 1
        elif CLIENT[index] == "}":
            depth -= 1
            if depth == 0:
                # String values are removed before keys are looked for. The
                # sentences in these maps are prose, and prose acquires a colon
                # eventually — at which point a scan of the raw body would report
                # a key that does not exist and fail against a correct client.
                body = re.sub(r'"(?:[^"\\]|\\.)*"', '""', CLIENT[start + 1 : index])
                return set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", body))
    raise AssertionError(f"`{name}` is never closed")


def _object_values(name: str) -> dict[str, str]:
    """The `key: "string"` pairs of a top-level `const <name> = { ... }` literal.

    The sibling above deliberately strips string values before reading keys, so
    it cannot answer "does this key have words behind it" — which is a separate
    failure and, until this existed, an unchecked one: a map with the right key
    set and an empty value renders a badge with nothing in it, and every keys
    test stays green.
    """
    opening = re.search(rf"^(?:export )?const {re.escape(name)} = (?={{)", CLIENT, re.MULTILINE)
    assert opening, f"the client has no top-level `const {name} = {{`"
    start = opening.end()
    depth = 0
    for index in range(start, len(CLIENT)):
        if CLIENT[index] == "{":
            depth += 1
        elif CLIENT[index] == "}":
            depth -= 1
            if depth == 0:
                body = CLIENT[start + 1 : index]
                return dict(re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*:\s*"((?:[^"\\]|\\.)*)"', body))
    raise AssertionError(f"`{name}` is never closed")


@pytest.mark.parametrize("name", ["REASON_SENTENCES", "REASON_WORDS"])
def test_every_unresolved_reason_has_words_for_a_curator(name):
    """A run that resolved nothing has to say which kind of nothing, in English.

    Chunk-independent statement of the requirement: the reason exists so a
    curator knows whether to re-search, re-word the intent, or accept that the
    work may not exist — and only one of the five points at the last of those.
    A raw `identity_refused` on the page communicates none of that.
    """
    assert _object_keys(name) == {str(reason) for reason in UnresolvedReason}


def test_every_resolution_status_has_words_for_a_curator():
    assert _object_keys("RESOLUTION_WORDS") == {str(status) for status in ResolutionStatus}


@pytest.mark.parametrize("name", ["RESOLUTION_WORDS", "REASON_WORDS", "REASON_SENTENCES"])
def test_every_phrase_a_curator_reads_actually_has_words_in_it(name):
    """Right keys, empty value: a badge that renders nothing and passes every keys test.

    The keys checks above strip string values before reading keys, so none of
    them can see this. A mutation sweep emptying `RESOLUTION_WORDS.pending`
    survived all three suites — the browser tests assert the two entries that
    were reworded, and nothing looked at the third.

    Asserted over every map rather than the one the sweep found, because the
    hole is in the *shape* of the keys checks and applies to all of them
    equally.
    """
    values = _object_values(name)
    assert values, f"`{name}` parsed to no string values at all — this guard would pass vacuously"

    empty = sorted(key for key, phrase in values.items() if not phrase.strip())
    assert not empty, f"{name} carries {empty} with no words behind them; each renders as an empty badge"


def test_every_run_status_is_named_in_the_client():
    """`runSentence` says what a run's state means, and it must cover all of them.

    **A weaker check than the maps above, deliberately, and worth being exact
    about what it does and does not prove.** The sentences are an if-chain rather
    than an object literal because several branches read the tally, the run kind
    and whether image resolution is wired — they are not one-liners and a map of
    bare strings could not hold them. So this asserts only that each status value
    appears somewhere in the client, not that it has a branch, nor that the
    branch is right.

    What it does buy is the property that matters: a tenth `RunStatus` added to
    the enum fails here, at the moment it is cheap to write a sentence for.
    Without it the fallback renders "This run is halted_by_something." — a raw
    diagnostic token in the one sentence on the page that exists to tell a
    curator what happened and what to do about it.
    """
    for status in RunStatus:
        assert f'"{status}"' in CLIENT, f"the client has no sentence naming the {status} state"


def test_every_resolution_status_has_a_glyph():
    """Colour is never the sole carrier of state, so the glyph is not optional."""
    assert _object_keys("RESOLUTION_GLYPHS") == {str(status) for status in ResolutionStatus}


@pytest.mark.parametrize("name", ["VERDICT_WORDS", "VERDICT_GLYPHS"])
def test_every_decided_verdict_has_words_and_a_glyph(name):
    """Accept and reject must be distinguishable without colour, by decision.

    `design_decisions.accessibility_approach` names the candidate grid outright,
    and the glyph is the half a stylesheet cannot supply. A fifth verdict added
    to the enum would otherwise reach a card as `awaiting_third_opinion` — the
    raw token, on the one screen where the whole point is that the curator knows
    what they are looking at.

    `pending` is excluded because an undecided work draws no badge at all, which
    is how the ordinary case is shown: a badge on every card makes the two
    decided states harder to pick out rather than easier.
    """
    assert _object_keys(name) == {str(verdict) for verdict in Verdict if verdict is not Verdict.PENDING}


@pytest.mark.parametrize("name", ["PROVENANCE_WORDS", "PROVENANCE_GLYPHS"])
def test_every_provenance_has_words_and_a_glyph(name):
    """Every provenance is drawn as itself, never as another one.

    The client once drew provenance as offered-or-not, and a third member would
    have been rendered as "asked for" — silently, and wrongly, on the one
    distinction the supplement exists to keep visible. `chosen` was that third
    member. Keyed on the enum, so a fourth fails here by name rather than at the
    moment a curator accepts a work believing it was something else.
    """
    assert _object_keys(name) == {str(provenance) for provenance in WorkProvenance}


def test_every_confirmation_is_drawn_as_itself():
    """A review card never reads as confirmed for a state the client has no words for.

    `confirmed` maps to no badge on purpose; the other two each carry one. A
    fourth member keyed nowhere would fall to the client's fallback, which is
    honest but wordless, so it fails here by name instead.
    """
    assert _object_keys("CONFIRMATION_MARKS") == {str(confirmation) for confirmation in Confirmation}


def test_every_cost_tier_has_words_a_spending_control_can_show():
    """A tier the client has no word for is drawn as the server spells it; one keyed nowhere fails here.

    Read from the raw literal rather than through `_object_keys`, whose keys are
    identifiers: three of the four tiers are spelled in dollar signs and are
    quoted keys.
    """
    body = _literal_body("TIER_WORDS")
    keys = {quoted or bare for quoted, bare in re.findall(r'^\s*(?:"([^"]+)"|([A-Za-z_]\w*))\s*:', body, re.MULTILINE)}
    assert keys == {str(tier) for tier in CostTier}


def test_every_facet_kind_has_a_word_the_work_screen_can_label_it_with():
    """The typed vocabulary reaches a museum label, so every kind needs one.

    `VocabularyKind` is shared with `Affinity.kind` precisely so that what a work
    *is* and what a curator *likes* are said in one set of terms — which means a
    seventh member arrives for reasons that have nothing to do with this screen,
    and reaches it as its raw token. The Work screen falls through to that token
    rather than dropping the fact, so nothing on the page would look broken; it
    would simply read `date_range` where a label belongs.
    """
    assert _object_keys("FACET_KIND_WORDS") == {str(kind) for kind in VocabularyKind}


def test_every_facet_kind_label_actually_has_a_word_in_it():
    """Right keys, empty value: a term with nothing in it, and every keys test green."""
    values = _object_values("FACET_KIND_WORDS")
    assert values, "`FACET_KIND_WORDS` parsed to no string values at all — this guard would pass vacuously"

    empty = sorted(key for key, phrase in values.items() if not phrase.strip())
    assert not empty, f"`FACET_KIND_WORDS` has keys with no words behind them: {empty}"


def test_both_surfaces_say_the_same_sentence_about_a_restored_work():
    """One fact, one wording, across a boundary no compiler checks.

    The agent-facing notice and the Work screen's confirmation are the same
    sentence deliberately: a curator who restores through the browser and an
    agent that restores through `art_catalogue` are told the same thing about
    when the wall catches up and how to make it sooner. Two surfaces stating one
    fact in different words is how a reader learns to trust neither, and the
    divergence is invisible from either side alone — each file reads fine.

    Python and JavaScript cannot share a literal, so this is the join. It fails
    the moment one side is reworded, which is the only moment the fix is cheap.
    """
    assert RESTORE_NOTICE in CLIENT, (
        "The client no longer contains the restore notice verbatim. Either the browser was "
        "reworded and `bindings.RESTORE_NOTICE` was not, or the reverse — the two surfaces "
        "have started saying one fact in two wordings."
    )


def test_the_restore_sentence_says_the_wall_catches_up_by_itself_and_offers_no_remedy():
    """The wall takes a restored work back as the restore lands (the owner, 2026-10-10).

    This test said the opposite until then: nothing republished an addition, so
    the operator's 2026-08-12 ruling required the sentence to name re-hanging as
    the way to make the wall catch up. Once the hung theme's feed takes the work
    back by itself, that remedy is a pointless errand, and a tidying edit that
    kept it would be the drift this guards against. The behaviour it describes
    is `test_reconciliation.py`'s restore test.
    """
    assert "rotation of every wall" in RESTORE_NOTICE
    assert "hang" not in RESTORE_NOTICE.replace(
        "hanging a theme", ""
    ), "The restore notice offers re-hanging again, which the wall no longer needs."


def test_every_taste_kind_has_a_heading_the_screen_can_group_under():
    """The Taste screen groups by kind, and a kind with no heading has no group.

    Same shared vocabulary and the same failure as the Work screen's labels, one
    screen along: a seventh member arrives for reasons that have nothing to do
    with taste, and reaches this page as a raw token over a list of judgments.
    The Taste screen renders only the kinds it has headings for, so an unlabelled
    kind is worse than an ugly one — the judgments under it are *not drawn*, and
    the curator sees no evidence they exist.
    """
    assert _object_keys("TASTE_KIND_WORDS") == {str(kind) for kind in VocabularyKind}


@pytest.mark.parametrize("name", ["SENTIMENT_WORDS", "SENTIMENT_GLYPHS"])
def test_every_sentiment_has_words_and_a_shape(name):
    """Warmth is exactly the thing a first draft renders as a colour ramp.

    `accessibility-spec.md` binds this surface and colour is never the sole
    carrier of state, so each of the four gets a distinguishable glyph as well as
    a word — and a fifth sentiment added to the enum fails here rather than
    arriving on the page as its own token beside no shape at all.
    """
    assert _object_keys(name) == {str(member) for member in AffinitySentiment}


def test_every_derivation_has_a_sentence_saying_what_the_claim_is():
    """The Taste screen exists to make derivation visible, so a bare token defeats it.

    "inferred" on its own tells a curator nothing about whether the product is
    repeating them or guessing at them — which is precisely the thing they need
    in order to decide whether to overrule the row.
    """
    assert _object_keys("DERIVATION_WORDS") == {str(member) for member in AffinityDerivation}


def test_every_sentiment_shape_is_a_glyph_the_glyph_table_holds():
    """Right keys, and each a real glyph: the hole the keys check above cannot see.

    The shapes are named by meaning from `core/glyphs.js`, which holds each
    glyph once (`tests/unit/test_glyphs_have_one_meaning.py`), so a sentiment
    pointing at a meaning the table lacks would render as "undefined".
    """
    named = dict(re.findall(r"(\w+): GLYPHS\.(\w+)", _literal_body("SENTIMENT_GLYPHS")))
    assert set(named) == {str(member) for member in AffinitySentiment}
    table = (STATIC_DIR / "core" / "glyphs.js").read_text()
    missing = sorted(meaning for meaning in named.values() if not re.search(rf"^\s*{meaning}: \"[^\"]+\",$", table, re.MULTILINE))
    assert not missing, f"SENTIMENT_GLYPHS names {missing}, which core/glyphs.js does not hold"


@pytest.mark.parametrize("name", ["TASTE_KIND_WORDS", "SENTIMENT_WORDS", "DERIVATION_WORDS"])
def test_every_taste_phrase_a_curator_reads_actually_has_words_in_it(name):
    """Right keys, empty value — the hole the keys checks above cannot see."""
    values = _object_values(name)
    assert values, f"`{name}` parsed to no string values at all — this guard would pass vacuously"

    empty = sorted(key for key, phrase in values.items() if not phrase.strip())
    assert not empty, f"`{name}` carries {empty} with no words behind them"


def test_the_three_reactions_are_the_pairs_of_fields_taste_is_held_in():
    """Each reaction writes a `sentiment` and an `open_to_more`, and both are named.

    The two-fields rule is only paid for at the point a control writes them, and
    a reaction table that carried a sentiment alone would default the openness —
    where the default that reads as safe is the one that silently blacklists an
    artist the curator asked to keep hearing about. Read off the client rather
    than agreed to, because nothing else in this repository executes it.
    """
    body = _literal_body("REACTIONS")

    for reaction in ("more like this", "not this", "tell me more"):
        assert f'"{reaction}"' in body, f"the client has no control writing {reaction!r}"
    assert body.count("sentiment:") == body.count("open_to_more:") == 3
    # And the pair that the whole design exists for: cool, and still open.
    assert '"tell me more": { sentiment: "cool", open_to_more: true }' in body


def test_every_reason_a_get_skips_an_item_has_words():
    """A Get reports what it left out; a new reason would otherwise go unsaid.

    `getSentence` counts the skips it has words for, so a reason missing here is
    not shown as its raw token but dropped from the sentence entirely, and the
    curator would read that every ticked work is being got.
    """
    assert _object_keys("SKIP_WORDS") == {str(reason) for reason in SkipReason}


def test_no_screen_replaces_children_except_through_fill():
    """`replaceChildren` writes a null argument as the word "null".

    `render` filtered for it, and twenty-one other calls did not, so an Artist page
    with no description printed "null" above its works. Every call goes through
    `fill` in `core/render.js`, which drops what a condition left empty; this
    refuses a direct call anywhere else, comments excluded.
    """
    direct = []
    for path in CLIENT_PATHS:
        if path.name == "render.js" and path.parent.name == "core":
            continue
        code = re.sub(r"/\*.*?\*/|//[^\n]*", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
        if ".replaceChildren(" in code:
            direct.append(str(path.relative_to(STATIC_DIR)))
    assert CLIENT_PATHS, "no client scripts were read; this guard would pass vacuously"
    assert direct == [], f"call fill() from core/render.js instead of replaceChildren in: {direct}"


def test_every_run_kind_has_a_word():
    """Queue names a run by its kind; a new kind would otherwise be listed as its raw token."""
    assert _object_keys("KIND_WORDS") == {str(kind) for kind in RunKind}


@pytest.mark.parametrize("name", ["LOOK_SOURCE_WORDS", "LOOK_SOURCE_GLYPHS"])
def test_every_state_a_source_can_answer_a_look_with_has_words_and_a_glyph(name):
    """A look's row is a glyph and a word; a state missing here would be drawn as its raw token."""
    assert _object_keys(name) == {str(state) for state in SourceState}
    values = _object_values(name)
    assert all(value.strip() for value in values.values()), f"`{name}` has a state with nothing to show"


def test_every_run_status_has_a_word_for_a_table_cell():
    """Queue's State column said `resolving_images`; a status keyed nowhere here would again."""
    assert _object_keys("STATE_WORDS") == {str(status) for status in RunStatus}
    values = _object_values("STATE_WORDS")
    assert all(value.strip() for value in values.values())


def test_every_reason_a_work_is_not_on_a_wall_has_a_word():
    """Walls' *Not showing* table said `kept_off_every_wall`; a reason keyed nowhere here would again."""
    from arrt.library.readiness import UnplayableReason
    from arrt.programming.manifest.builder import KeptOff

    assert _object_keys("EXCLUSION_WORDS") == {str(reason) for reason in [*UnplayableReason, *KeptOff]}


def test_every_plugin_state_has_a_word():
    from arrt.library.sources.loading import PluginState

    assert _object_keys("PLUGIN_STATE_WORDS") == {str(state) for state in PluginState}


def test_every_built_in_source_has_the_name_a_curator_knows_it_by():
    """A scan "from artic" names a plugin; "from the Art Institute of Chicago" names a museum.

    Keyed on the `PROVIDER` every built-in source module declares, gathered from
    the package rather than listed, so an eleventh source fails here until it has
    a name.
    """
    import importlib
    import pkgutil

    from arrt.library import sources

    providers = set()
    for module in pkgutil.iter_modules(sources.__path__):
        declared = getattr(importlib.import_module(f"{sources.__name__}.{module.name}"), "PROVIDER", None)
        if isinstance(declared, str):
            providers.add(declared)
    assert len(providers) >= 5, "too few sources were found for this guard to mean anything"
    assert _object_keys("MUSEUM_NAMES") == providers


def test_the_client_names_each_museum_as_the_server_does():
    """Two maps, one name each: the server's sentences and the client's labels must agree.

    The server's names are each built-in's own `MUSEUM` (`library/sources/names.py`);
    the client's are `MUSEUM_NAMES` in `core/providers.js`. Read pair by pair,
    so a name changed on one side fails here rather than reading two ways.
    """
    from arrt.library.sources.names import built_in_museums

    body = re.search(r"export const MUSEUM_NAMES = \{(.*?)\n\};", CLIENT, re.DOTALL)
    assert body, "the client has no `MUSEUM_NAMES`"
    client = dict(re.findall(r'^\s*([a-z_]+):\s*"((?:[^"\\]|\\.)*)",?\s*$', body.group(1), re.MULTILINE))
    assert len(client) == len(_object_keys("MUSEUM_NAMES")), "a client entry was not read as a pair"
    assert client == dict(built_in_museums())


def test_both_surfaces_say_the_same_sentence_about_a_work_let_back_on_the_walls():
    """The Work page's *Allow on walls again* and `art_theme(action='allow_again')`, in one wording."""
    from arrt.mcp.bindings import ALLOW_AGAIN_NOTICE

    assert ALLOW_AGAIN_NOTICE in CLIENT
    assert "sync" not in ALLOW_AGAIN_NOTICE
    assert "manifest" not in ALLOW_AGAIN_NOTICE


@pytest.mark.parametrize("name", ["RIGHTS_WORDS", "FETCH_WORDS"])
def test_every_rights_and_fetch_state_has_words(name):
    """The Work page's sources and a review card's scans said `public_domain` and `partial_tiles`."""
    from arrt.persistence.records import FetchStatus, RightsStatus

    enum = {"RIGHTS_WORDS": RightsStatus, "FETCH_WORDS": FetchStatus}[name]
    assert _object_keys(name) == {str(member) for member in enum}


def test_a_topic_card_records_each_topic_kind_as_the_taste_kind_the_server_maps_it_to():
    """Ask's topic cards write a topic's reaction under `TASTE_KIND[kind]`, a copy of the server's `FACET_KINDS`.

    A kind the server adds and the client lacks would get no reactions, and a
    kind mapped differently would record taste under the wrong dimension, so
    the copy is held to its source here, values and all.
    """
    assert _object_values("TASTE_KIND") == {topic.value: str(facet) for topic, facet in FACET_KINDS.items()}
