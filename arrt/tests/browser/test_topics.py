"""Library › Topics and the Topic page, in a real browser against a real server.

The index lists the topics the
library's works are in, by kind, with counts; a Topic page draws the topic and
*In your library* at once and fills *Representative works* and *Artists* after,
each saying when Wikidata did not answer, as the Artist page's *Their work* does.
A Get from a topic goes, by default, into a new theme named after it.

The registry is a fake installed where the entry point builds Wikidata's, and
the facet rows are written by the real topic sweep, run here by hand, so the
library's half is the server's own answer rather than a stub. `POST /api/gets`
is answered by the test, as in `test_getting.py`: the server side of a Get is
not what is under test here.
"""

import json
import re

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry
from payloads import a_run
from playwright.sync_api import expect
from scripted_model import ScriptedModel

from arrt.library.registry import (
    CommonsFile,
    ItemId,
    RegistryCreator,
    RegistrySimilar,
    RegistryText,
    RegistryTopic,
    RegistryTopicRef,
    RegistryTopicWork,
    TopicKind,
)
from arrt.persistence.discovery_records import RunStatus

SIXTEENTH = "Q7017"
WINTER = "Q1311"
BRUEGEL = "Q43270"
HUNTERS = "Q500985"
HARVESTERS = "Q1170284"
CORN = "Q1170285"
FLAMMARION = "Q1060878"
NAMELESS = "Q99999999"
IMPRESSIONISM = "Q40415"
BAROQUE = "Q37853"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/Hunters.jpg"
BY_BRUEGEL = RegistryCreator(qid=ItemId(BRUEGEL), name=RegistryText("Pieter Bruegel the Elder"))

WORKS = "section[aria-labelledby='representative-works']"
#: The selection's acts in the page's toolbar (`core/selecting.js`), where a Get from the topic's
#: works lives since every list shares one selection model.
BAR = "#view .selection"
ARTISTS = "section[aria-labelledby='topic-artists']"
HELD = "section[aria-labelledby='in-your-library']"
LISTBOX = "#search-suggestions"


def ref(qid: str, label: str, kind: TopicKind) -> RegistryTopicRef:
    return RegistryTopicRef(qid=ItemId(qid), label=RegistryText(label), kind=kind)


def topic(qid: str, label: str, *kinds: TopicKind, **fields) -> RegistryTopic:
    return RegistryTopic(qid=ItemId(qid), label=RegistryText(label), kinds=kinds, **fields)


@pytest.fixture
def ask_model():
    """A server with a key: the dropdown offers Ask only where Ask can answer."""
    return ScriptedModel(replies=[])


@pytest.fixture
def registry():
    century = ref(SIXTEENTH, "16th century", TopicKind.PERIOD)
    return FakeRegistry(
        work_topics={HUNTERS: [century, ref(WINTER, "winter", TopicKind.SUBJECT)], CORN: [century]},
        topics={
            SIXTEENTH: topic(
                SIXTEENTH,
                "16th century",
                TopicKind.PERIOD,
                description=RegistryText('century <img src=x onerror="window.pwned=1">'),
                start=1501,
                end=1600,
            ),
            # A subject: its works are not matched by date, so it claims no years.
            WINTER: topic(WINTER, "winter", TopicKind.SUBJECT, description=RegistryText("season")),
            # A movement first and a period second, with years: its works are
            # its artists', found by the movement, so the years claim nothing.
            BAROQUE: topic(BAROQUE, "Baroque", TopicKind.MOVEMENT, TopicKind.PERIOD, start=1600, end=1750),
            # Known to Wikidata and in none of your works.
            IMPRESSIONISM: topic(IMPRESSIONISM, "Impressionism", TopicKind.MOVEMENT, description=RegistryText("art movement")),
        },
        topic_works={
            SIXTEENTH: [
                RegistryTopicWork(
                    qid=ItemId(HUNTERS),
                    title=RegistryText("The Hunters in the Snow"),
                    sitelinks=39,
                    year=1565,
                    image=CommonsFile(COMMONS),
                    creators=(BY_BRUEGEL,),
                ),
                RegistryTopicWork(
                    qid=ItemId(HARVESTERS),
                    title=RegistryText("The Harvesters"),
                    sitelinks=25,
                    year=1565,
                    image=CommonsFile(COMMONS),
                    creators=(BY_BRUEGEL,),
                ),
                # Somebody made it and nobody knows who; and Wikidata has no picture of it.
                RegistryTopicWork(
                    qid=ItemId(FLAMMARION), title=RegistryText("Flammarion engraving"), sitelinks=20, creator_unknown=True
                ),
                # The label service's answer for an item with no English label.
                RegistryTopicWork(qid=ItemId(NAMELESS), title=RegistryText(NAMELESS), sitelinks=2, year=1520),
            ],
            WINTER: [
                RegistryTopicWork(
                    qid=ItemId(HUNTERS), title=RegistryText("The Hunters in the Snow"), sitelinks=39, creators=(BY_BRUEGEL,)
                )
            ],
            BAROQUE: [RegistryTopicWork(qid=ItemId("Q219831"), title=RegistryText("The Night Watch"), sitelinks=80)],
        },
        topic_artists={
            SIXTEENTH: [
                RegistrySimilar(
                    qid=ItemId(BRUEGEL),
                    name=RegistryText("Pieter Bruegel the Elder"),
                    sitelinks=90,
                    born=1525,
                    died=1569,
                    images=40,
                ),
                RegistrySimilar(
                    qid=ItemId("Q5598"), name=RegistryText("Rembrandt"), sitelinks=150, born=1606, died=1669, images=1
                ),
            ]
        },
        topics_found={
            "16th": [topic(SIXTEENTH, "16th century", TopicKind.PERIOD, start=1501, end=1600)],
            # The library's 16th century by a name the library's own label does not hold.
            "cinquecento": [topic(SIXTEENTH, "16th century", TopicKind.PERIOD, description=RegistryText("Italian 1500s"))],
            "impressionism": [
                topic(IMPRESSIONISM, "Impressionism", TopicKind.MOVEMENT, description=RegistryText("art movement")),
                topic(ItemId("Q1145287"), "Impressionism", TopicKind.MOVEMENT, description=RegistryText("music movement")),
            ],
        },
    )


@pytest.fixture
def held(services, service, give_a_master):
    """Bruegel and two works of his in the library, identified, with their topics swept.

    Two works in the 16th century, so its count is not the 1 every topic would
    show by default; one of them, *The Hunters*, is also among the works
    Wikidata lists, which is the case that marks it held, and holds a master, so
    its row has a picture to draw (`pictured_artwork_id`); *The Corn Harvest*
    holds none.
    """
    bruegel = service.add_artist(name="Pieter Bruegel the Elder", born=1525, died=1569)
    services.identity.set_artist_identity(bruegel.id, BRUEGEL)
    hunters = service.add_artwork(
        title="The Hunters in the Snow", artist_id=bruegel.id, date_created="1565", wikidata_qid=HUNTERS
    )
    corn = service.add_artwork(title="The Corn Harvest", artist_id=bruegel.id, date_created="1565", wikidata_qid=CORN)
    give_a_master(hunters)
    services.topic_sweep.run()
    return bruegel, hunters, corn


@pytest.fixture
def all_works(services):
    theme = services.display.add_theme(name="All works")
    services.display.make_default(theme.id)
    return theme


def open_topic(ui, qid=SIXTEENTH):
    ui.open(f"#topic/{qid}")
    ui.page.wait_for_selector(f"{HELD} h2")


def works_answered(ui):
    ui.page.wait_for_selector(f"{WORKS} table, {WORKS} p.note, {WORKS} p.muted:not([aria-live])")


def _whole(text):
    """A pattern for a cell whose words are `text` and nothing else, set in any whitespace."""
    return re.compile(rf"^\s*{re.escape(text)}\s*$")


def work_row(ui, title):
    """The row of *Representative works* whose title link says `title`.

    By the link's whole words rather than the row's text, which holds the state
    and the maker as well, so "The Harvesters" is not taken for a longer title.
    A title that is not listed matches no row, and what is asserted of it fails.
    """
    link = ui.page.locator("td.work-title a.row-title", has_text=_whole(title))
    return ui.page.locator(f"{WORKS} tbody tr").filter(has=link)


def mark(ui, title):
    """A work's state cell: the fifth, after Get, title, maker and year."""
    return work_row(ui, title).locator("td").nth(4)


def record_gets(ui) -> list[dict]:
    bodies: list[dict] = []
    answer = {
        "run": a_run(run_id="get-1", kind="get", intent=None, status=RunStatus.RESOLVING_IMAGES.value).model_dump(mode="json"),
        "skipped": [],
    }

    def handler(route):
        bodies.append(json.loads(route.request.post_data))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(answer))

    ui.page.route("**/api/gets", handler)
    return bodies


# -- Library › Topics -------------------------------------------------------------


class TestTheIndex:
    def test_it_lists_every_kind_and_each_topic_with_its_count(self, ui, held):
        ui.open("#topics")
        ui.page.wait_for_selector("#view h1:text-is('Topics')")

        expect(ui.page.locator("#view section h2")).to_have_text(
            ["Periods", "Movements", "Subjects", "Media"], use_inner_text=True
        )
        expect(ui.page.locator("section[aria-labelledby='topics-period'] ul.topic-held li")).to_have_text(
            ["16th century · 2 works"], use_inner_text=True
        )
        expect(ui.page.locator("section[aria-labelledby='topics-subject'] li")).to_have_text(
            ["Winter · 1 work"], use_inner_text=True
        )  # a name on its own starts with a capital (`topicName`)
        expect(ui.page.locator("section[aria-labelledby='topics-movement'] p")).to_have_text(
            "None of your works is in a movement.", use_inner_text=True
        )

    @staticmethod
    def thirty_subjects(ui):
        subjects = [{"qid": f"Q{1000 + n}", "label": f"subject number {n:02d}", "works": n % 4 + 1} for n in range(30)]
        ui.serve(
            "**/api/topics",
            {
                "state": "known",
                "note": None,
                "kinds": [
                    {"kind": "period", "topics": []},
                    {"kind": "movement", "topics": []},
                    {"kind": "subject", "topics": subjects},
                    {"kind": "medium", "topics": []},
                ],
            },
        )

    def test_a_kind_of_thirty_takes_a_third_of_the_height_it_would_in_one_column(self, ui):
        """The owner's ruling on #175: columns, by name, so a long kind uses the width."""
        self.thirty_subjects(ui)
        ui.page.set_viewport_size({"width": 1280, "height": 900})
        ui.open("#topics")
        ui.page.wait_for_selector("section[aria-labelledby='topics-subject'] li")

        heights = ui.page.evaluate("""() => {
            const list = document.querySelector("section[aria-labelledby='topics-subject'] ul");
            const columned = list.getBoundingClientRect().height;
            list.style.columns = "auto";
            const single = list.getBoundingClientRect().height;
            list.style.columns = "";
            return { columned, single };
        }""")
        assert heights["columned"] <= heights["single"] / 3
        # Each count stays beside its name.
        expect(ui.page.locator("section[aria-labelledby='topics-subject'] li").first).to_have_text(
            "Subject number 00 · 1 work", use_inner_text=True
        )

    def test_on_a_phone_a_kind_is_one_column(self, ui):
        self.thirty_subjects(ui)
        ui.page.set_viewport_size({"width": 390, "height": 844})
        ui.open("#topics")
        ui.page.wait_for_selector("section[aria-labelledby='topics-subject'] li")

        lefts = ui.page.evaluate(
            "() => [...document.querySelectorAll(\"section[aria-labelledby='topics-subject'] li\")]"
            ".map((li) => Math.round(li.getBoundingClientRect().left))"
        )
        assert len(set(lefts)) == 1

    def test_a_topic_opens_its_page(self, ui, held):
        ui.open("#topics")
        ui.page.click("section[aria-labelledby='topics-period'] a:text-is('16th century')")

        ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#topic/${qid}`", arg=SIXTEENTH)
        ui.page.wait_for_selector(f"{HELD} h2")
        expect(ui.page.locator("#view a", has_text="←").first).to_have_text("← Topics", use_inner_text=True)

    def test_the_sidebar_offers_topics_under_artworks_after_themes(self, ui, held):
        ui.open("#collection")
        ui.page.wait_for_selector("#view h1")

        ui.page.get_by_role("link", name="Topics").click()
        ui.page.wait_for_selector("#view h1:text-is('Topics')")

    def test_find_a_topic_asks_wikidata_and_tells_like_names_apart(self, ui, held):
        ui.open("#topics")
        ui.page.get_by_label("Find a topic", exact=True).fill("impressionism")
        ui.page.click("#view button:text-is('Find')")

        ui.page.wait_for_selector("section[aria-labelledby='topic-search'] ul")
        assert "find=impressionism" in ui.page.evaluate("() => window.location.hash")
        # Not the top bar's `q`: its box would then claim the artworks were searched.
        expect(ui.page.locator("#search")).to_have_value("")
        expect(ui.page.locator("section[aria-labelledby='topic-search'] li")).to_have_text(
            ["Impressionism — movement art movement", "Impressionism — movement music movement"], use_inner_text=True
        )
        ui.page.click("section[aria-labelledby='topic-search'] li:has-text('art movement') a")
        ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#topic/${qid}`", arg=IMPRESSIONISM)

    def test_a_search_finding_nothing_says_so(self, ui, held):
        ui.open("#topics?find=nothing")

        ui.page.wait_for_selector("section[aria-labelledby='topic-search'] p.muted:not([aria-live])")
        expect(ui.view).to_contain_text(
            "Wikidata has no period, movement, subject or medium called “nothing”.", use_inner_text=True
        )


# -- one topic ---------------------------------------------------------------------


class TestTheTopicPage:
    def test_the_library_half_is_drawn_before_wikidata_answers(self, ui, held):
        """*Representative works* and *Artists* are asked after the page, and hold nothing back."""
        _bruegel, hunters, corn = held
        waiting = []
        for section in ("works", "artists"):
            ui.page.route(
                f"**/api/topics/{SIXTEENTH}/{section}",
                lambda route: waiting.append(route),  # noqa: PLW0108 -- Playwright passes a builtin method two arguments
            )
        open_topic(ui)

        expect(ui.page.locator(f"{HELD} h2")).to_have_text("In your library (2)", use_inner_text=True)
        # The two as a set, since the order they are listed in is not the claim:
        # two cards, and each title is one of them.
        cards = ui.page.locator(f"{HELD} .card-title")
        expect(cards).to_have_count(2)
        for held_title in (hunters.title, corn.title):
            expect(cards.filter(has_text=_whole(held_title))).to_have_count(1)
        expect(ui.page.locator(f"{WORKS} [aria-live]")).to_have_text("Asking Wikidata…", use_inner_text=True)
        expect(ui.page.locator(f"{ARTISTS} [aria-live]")).to_have_text("Asking Wikidata…", use_inner_text=True)
        # The head is Wikidata's too, and is not held back by the slow sections.
        ui.page.wait_for_selector("#view h1:text-is('16th century')")
        expect(ui.page.locator("#view dl.facts dd")).to_have_text("period", use_inner_text=True)

        # A poll on the list the handlers fill, which only this loop's pauses let Playwright's events reach.
        while len(waiting) < 2:
            ui.page.wait_for_timeout(50)  # sleep: pumps events until both routes arrive; the loop ends on that
        for route in waiting:
            route.continue_()
        works_answered(ui)
        ui.page.wait_for_selector(f"{ARTISTS} ul")
        expect(ui.page.locator(f"{WORKS} tbody tr")).to_have_count(4)

    def test_a_periods_works_are_headed_with_its_years(self, ui, held):
        open_topic(ui)
        works_answered(ui)

        expect(ui.page.locator(f"{WORKS} h2")).to_have_text("Works from 1501–1600", use_inner_text=True)

    @pytest.mark.parametrize("qid", [WINTER, BAROQUE], ids=["a subject", "a movement that is also a period"])
    def test_works_found_by_anything_but_a_period_claim_no_years(self, ui, held, qid):
        open_topic(ui, qid)
        works_answered(ui)

        expect(ui.page.locator(f"{WORKS} h2")).to_have_text("Representative works", use_inner_text=True)

    def test_each_work_carries_its_state_as_glyph_and_word(self, ui, held):
        open_topic(ui)
        works_answered(ui)

        # Exactly these four works, each with its state, whitespace-normalised as the join over `split()` was.
        expect(ui.page.locator(f"{WORKS} tbody tr")).to_have_count(4)
        for title, state in {
            "The Hunters in the Snow": "● Held",
            "The Harvesters": "◐ Not held · Image found",
            "Flammarion engraving": "○ No image known",
            f"No English title ({NAMELESS})": "○ No image known",
        }.items():
            expect(mark(ui, title)).to_have_text(state, use_inner_text=True)
        # No glyph is read out: none lacks the attribute. The states above are the badges having painted.
        expect(ui.page.locator(f"{WORKS} .badge .glyph:not([aria-hidden='true'])")).to_have_count(0)

    def test_on_a_phone_each_picture_shows_and_the_list_fits(self, ui, held, pictures_load):
        """The Topic page's list has a *By* column the Artist page's lacks, so it is the likeliest to run wide."""
        ui.page.set_viewport_size({"width": 390, "height": 900})
        open_topic(ui)
        works_answered(ui)

        for style in ("held", "not-held"):
            expect(ui.page.locator(f"{WORKS} .work-pic-{style}").first, f"the {style} picture is not drawn").to_be_visible()
            box = ui.page.locator(
                f"{WORKS} .work-pic-{style}"
            ).first.bounding_box()  # one-shot: geometry, measured once it is visible
            assert box is not None, f"the {style} picture is not drawn"
            assert min(box["width"], box["height"]) >= 48
        fits = ui.page.evaluate(
            "(s) => { const c = document.querySelector(`${s} .artist-works`); return c.scrollWidth <= c.clientWidth; }", WORKS
        )
        assert fits, "the list scrolls sideways"
        # Titles can break anywhere, so the table would squeeze them first; they keep a readable width.
        title_cell = ui.page.locator(f"{WORKS} td.work-title").first
        expect(title_cell).to_be_visible()
        assert title_cell.bounding_box()["width"] >= 112  # one-shot: geometry, measured once the cell is visible
        # Who made it folds under the title rather than being lost.
        flammarion = ui.page.locator(f"{WORKS} tbody tr", has_text="Flammarion engraving")
        expect(flammarion.locator(".by-under")).to_have_text("Unknown maker", use_inner_text=True)
        expect(flammarion.locator("td.by-col")).to_be_hidden()
        harvesters = ui.page.locator(f"{WORKS} tbody tr", has_text="The Harvesters")
        harvesters.locator(".by-under a:text-is('Pieter Bruegel the Elder')").click()
        ui.page.wait_for_selector("#view h1:has-text('Pieter Bruegel the Elder')")

    def test_held_wanted_and_not_held_each_draw_their_picture_in_their_own_style(self, ui, held, want_item, pictures_load):
        """The owner's ruling on #172: held and image found were told apart by a picture only one of them had.

        Held draws the library's own thumbnail; not held draws Wikidata's, plain
        and marked by its badge; wanted (here with no picture known) says so in
        glyph and word. The not-held style is on the not-held picture only.
        """
        want_item(NAMELESS, "An untitled work")
        open_topic(ui)
        works_answered(ui)

        hunters = mark(ui, "The Hunters in the Snow")
        expect(hunters.locator(".work-pic-held img")).to_have_attribute("src", re.compile(r"^/api/works/"))
        expect(hunters).to_have_text("● Held", use_inner_text=True)
        harvesters = mark(ui, "The Harvesters")
        expect(harvesters.locator(".work-pic-not-held img")).to_have_attribute(
            "src", re.compile(r"^https://commons\.wikimedia\.org/")
        )
        nameless = mark(ui, f"No English title ({NAMELESS})")
        expect(nameless).to_have_text("◑ Wanted", use_inner_text=True)
        expect(nameless.locator(".work-pic")).to_have_count(0)
        expect(mark(ui, "Flammarion engraving").locator(".work-pic")).to_have_count(0)
        expect(ui.page.locator(f"{WORKS} .work-pic-not-held")).to_have_count(1)
        expect(ui.page.locator(f"{WORKS} .work-pic-held")).to_have_count(1)

    def test_a_not_held_preview_is_a_real_picture_marked_by_its_badge(self, ui, held, pictures_load):
        """Ruling 7: legible at a glance, whole, and not hatched over; the badge says not held.

        Measured against the held picture in the same list, so a rule that
        shrank or hatched every picture alike would fail here too.
        """
        open_topic(ui)
        works_answered(ui)
        # The state is worded first, which is the badge having painted; the frames are measured after it.
        expect(mark(ui, "The Harvesters")).to_contain_text("Image found", use_inner_text=True)
        expect(mark(ui, "The Hunters in the Snow")).to_contain_text("Held", use_inner_text=True)
        style = (
            "(f) => { const img = f.querySelector('img'); const after = getComputedStyle(f, '::after');"
            " return { after: after.content, background: after.backgroundImage, fit: getComputedStyle(img).objectFit,"
            " edge: f.getBoundingClientRect().width }; }"
        )
        found = mark(ui, "The Harvesters").locator(".work-pic-not-held").evaluate(style)
        assert found["after"] in ("none", "normal"), "the preview is still hatched"
        assert found["background"] == "none", "the preview is still hatched"
        assert found["fit"] == "contain", "the preview is cropped to a square"
        assert found["edge"] >= 64, "the preview is too small to judge before spending"
        held_pic = mark(ui, "The Hunters in the Snow").locator(".work-pic-held").evaluate(style)
        assert held_pic["fit"] == "contain"
        assert held_pic["edge"] == found["edge"]

    def test_a_wanted_work_with_a_picture_draws_it_wanted_not_as_not_held(self, ui, held, want_item, pictures_load):
        want_item(HARVESTERS, "The Harvesters")
        open_topic(ui)
        works_answered(ui)
        harvesters = mark(ui, "The Harvesters")

        expect(harvesters).to_have_text("◑ Wanted", use_inner_text=True)
        expect(harvesters.locator(".work-pic-wanted img")).to_have_count(1)
        expect(harvesters.locator(".work-pic-not-held")).to_have_count(0)

    def test_a_held_work_that_is_also_wanted_reads_held(self, ui, held, want_item, pictures_load):
        """A wanted work since acquired: the server reports both, and held wins on the page."""
        want_item(HUNTERS, "The Hunters in the Snow")
        open_topic(ui)
        works_answered(ui)
        hunters = mark(ui, "The Hunters in the Snow")

        expect(hunters).to_have_text("● Held", use_inner_text=True)
        expect(hunters.locator(".work-pic-held")).to_have_count(1)
        expect(hunters.locator(".work-pic-wanted")).to_have_count(0)

    @pytest.mark.parametrize("width", [1280, 390], ids=["desktop", "phone"])
    def test_with_every_picture_failing_the_states_still_read_apart(self, ui, held, want_item, width):
        """Glyph and word carry the state; the picture is a second signal (`accessibility-spec.md`)."""
        ui.page.set_viewport_size({"width": width, "height": 900})
        want_item(NAMELESS, "An untitled work")
        ui.page.route("**/thumbnail*", lambda route: route.abort())
        ui.page.route("https://commons.wikimedia.org/**", lambda route: route.abort())
        open_topic(ui)
        works_answered(ui)
        # A picture that fails takes its frame with it: no broken-image icon in a styled box.
        ui.page.wait_for_function("(section) => document.querySelectorAll(`${section} .work-pic`).length === 0", arg=WORKS)

        expect(ui.page.locator(f"{WORKS} tbody tr")).to_have_count(4)
        for title, state in {
            "The Hunters in the Snow": "● Held",
            "The Harvesters": "◐ Not held · Image found",
            "Flammarion engraving": "○ No image known",
            f"No English title ({NAMELESS})": "◑ Wanted",
        }.items():
            expect(mark(ui, title)).to_have_text(state, use_inner_text=True)

    def test_makers_are_named_and_an_unknown_one_is_said(self, ui, held):
        open_topic(ui)
        works_answered(ui)

        expect(work_row(ui, "Flammarion engraving").locator("td").nth(2)).to_have_text("Unknown maker", use_inner_text=True)
        expect(work_row(ui, f"No English title ({NAMELESS})").locator("td").nth(2)).to_have_text("—", use_inner_text=True)
        # The By column's own link: the row also carries a copy under the title, shown only on a phone.
        ui.page.click(f"{WORKS} tr:has-text('The Harvesters') td.by-col a:text-is('Pieter Bruegel the Elder')")
        ui.page.wait_for_selector("#view h1:has-text('Pieter Bruegel the Elder')")

    def test_a_held_work_offers_no_tick_box(self, ui, held):
        open_topic(ui)
        works_answered(ui)

        expect(ui.page.locator(f"{WORKS} tbody tr")).to_have_count(4)
        for title in ("The Harvesters", "Flammarion engraving", f"No English title ({NAMELESS})"):
            expect(work_row(ui, title).locator("input[type='checkbox']")).to_have_count(1)
        # The held one, once the others show the boxes have been drawn, and its row is there.
        expect(work_row(ui, "The Hunters in the Snow")).to_have_count(1)
        expect(work_row(ui, "The Hunters in the Snow").locator("input[type='checkbox']")).to_have_count(0)

    def test_artists_are_listed_and_open_their_page(self, ui, held):
        bruegel, _hunters, _corn = held
        open_topic(ui)
        ui.page.wait_for_selector(f"{ARTISTS} ul")

        expect(ui.page.locator(f"{ARTISTS} li")).to_have_text(
            [
                "Pieter Bruegel the Elder 1525–1569 · 40 works with an image ● In your library",
                "Rembrandt 1606–1669 · 1 work with an image ○ Not held",
            ],
            use_inner_text=True,
        )
        ui.page.click(f"{ARTISTS} a:text-is('Pieter Bruegel the Elder')")
        ui.page.wait_for_function("(id) => window.location.hash.startsWith(`#artist/${id}`)", arg=bruegel.id)

    def test_registry_text_arrives_as_words_and_the_link_is_built_from_the_qid(self, ui, held):
        open_topic(ui)
        ui.page.wait_for_selector("#view h1:text-is('16th century')")
        # The heading can paint before the description does, so the description
        # is waited for in its own right before it is counted.
        escaped = ui.page.get_by_text('century <img src=x onerror="window.pwned=1">')
        escaped.wait_for()

        expect(escaped).to_have_count(1)
        assert ui.page.evaluate("() => window.pwned") is None
        # Worded, with the item as the link's target (#359: no bare item on the page).
        link = ui.page.locator("#view a:text-is('On Wikidata')")
        expect(link).to_have_attribute("href", f"https://www.wikidata.org/wiki/{SIXTEENTH}")

    def test_an_outage_leaves_the_library_half_standing(self, ui, held, registry):
        _bruegel, _hunters, _corn = held
        registry.failing = True
        open_topic(ui)
        works_answered(ui)
        ui.page.wait_for_selector(f"{ARTISTS} p.note")

        expect(ui.page.locator(f"{WORKS} p.note")).to_contain_text("could not be asked", use_inner_text=True)
        expect(ui.page.locator(f"{ARTISTS} p.note")).to_contain_text("could not be asked", use_inner_text=True)
        expect(ui.page.locator(f"{HELD} .card-title")).to_have_count(2)

    def test_a_topic_none_of_your_works_is_in_still_has_its_page_named_by_wikidata(self, ui, held):
        """The facets hold no name for it, so the head's name is Wikidata's, written in once it answers."""
        open_topic(ui, IMPRESSIONISM)

        expect(ui.page.locator(f"{HELD} p")).to_have_text(
            "None of your works in circulation is in this topic.", use_inner_text=True
        )
        ui.page.wait_for_selector("#view h1:text-is('Impressionism')")
        expect(ui.page.locator("#view dl.facts dd")).to_have_text("movement", use_inner_text=True)

    def test_an_address_that_is_not_a_qid_says_so(self, ui):
        ui.open("#topic/nonsense")
        ui.page.wait_for_selector('#view h1:text-is("That is not a topic\'s address")')
        ui.page.click("#view .not-found a:text-is('Topics')")
        ui.page.wait_for_selector("#view h1:text-is('Topics')")


# -- Get, into a theme named after the topic ---------------------------------------


def test_get_from_a_topic_defaults_to_a_new_theme_named_after_it(ui, services, held, all_works):
    """The default reads as the topic's name, with no field to fill, and Get makes the theme.

    The owner's review of the screens, on the *winter* page with no theme named *winter*."""
    bodies = record_gets(ui)
    open_topic(ui)
    works_answered(ui)
    ui.page.click("#view button.select-toggle")
    ui.page.check(f"{WORKS} tr:has-text('The Harvesters') input[type='checkbox']")
    # *Add to* is in the dialog *Get…* opens (ruling 1 of 2026-10-27).
    ui.page.click(f"{BAR} button.get-open")
    ui.page.wait_for_selector("dialog .get-into option[value='new']", state="attached")

    picker = ui.page.locator("dialog").get_by_label("Add to", exact=True)
    expect(picker).to_be_visible()
    assert picker.evaluate("node => node.selectedOptions[0].textContent") == "16th century (new theme)"
    expect(ui.page.locator("dialog").get_by_label("New theme's name")).to_be_hidden()
    ui.page.click("dialog button.get-confirm")

    ui.page.wait_for_selector(f"{BAR} .get-status a:text-is('Open the Get')")
    created = next(p.theme for p in services.display.survey_themes() if p.theme.name == "16th century")
    assert bodies == [{"qids": [HARVESTERS], "theme_id": created.id}]
    expect(ui.page.locator(f"{BAR} .get-status")).to_have_text(
        "Getting 1 work into 16th century. Open the Get", use_inner_text=True
    )


def test_get_from_a_topic_whose_name_is_a_theme_joins_it(ui, services, held, all_works):
    theme = services.display.add_theme(name="16th Century")
    bodies = record_gets(ui)
    open_topic(ui)
    works_answered(ui)
    ui.page.click("#view button.select-toggle")
    ui.page.check(f"{WORKS} tr:has-text('The Harvesters') input[type='checkbox']")
    ui.page.click(f"{BAR} button.get-open")
    ui.page.wait_for_selector("dialog .get-into option[value='new']", state="attached")
    ui.page.click("dialog button.get-confirm")

    ui.page.wait_for_selector(f"{BAR} .get-status a:text-is('Open the Get')")
    assert bodies == [{"qids": [HARVESTERS], "theme_id": theme.id}]


# -- the top bar's dropdown --------------------------------------------------------


def _type(ui, words):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h1")
    ui.page.click("#search")
    ui.page.keyboard.type(words)
    # The answer to all the words, not to where typing paused on a loaded machine.
    ui.page.wait_for_selector(f"{LISTBOX}:not([hidden]) [role='option']:text-is('All results for “{words}”')")


def _expect_options(ui, group, options):
    """The listbox's `group` offers `options`, in order, whitespace-normalised."""
    listbox = ui.page.get_by_role("listbox", name="Suggestions")
    expect(listbox.get_by_role("group", name=group, exact=True).get_by_role("option")).to_have_text(options, use_inner_text=True)


def _announced(ui):
    ui.page.wait_for_function(
        "() => document.querySelector('#search-suggestions + [aria-live]').textContent.startsWith('Wikidata')"
    )


def test_the_dropdown_has_a_topics_group_after_works(ui, service, held):
    service.add_artwork(title="A 16th-century copy")
    _type(ui, "16th")
    _announced(ui)

    _expect_options(ui, "Held: topics", ["16th century — period"])
    # Wikidata's 16th century is the library's, already shown, so not offered twice.
    expect(ui.page.locator(f"{LISTBOX} [aria-labelledby='suggestions-registry-topics']")).to_have_count(0)
    expect(ui.page.locator(f"{LISTBOX} .search-suggestions-label")).to_have_text(["Held: works", "Held: topics", "Ask", "Search"])

    ui.page.click(f"{LISTBOX} [role='option']:has-text('16th century — period')")
    ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#topic/${qid}`", arg=SIXTEENTH)


def test_the_dropdown_offers_wikidatas_topics_with_their_descriptions(ui, held):
    _type(ui, "impressionism")
    _announced(ui)

    _expect_options(
        ui,
        "Not held: topics",
        ["Impressionism — movement · art movement", "Impressionism — movement · music movement"],
    )
    # The last three of the group labels, whatever stands before them.
    labels = ui.page.locator(f"{LISTBOX} .search-suggestions-label")
    expect(labels.nth(-3)).to_have_text("Not held: topics")
    expect(labels.nth(-2)).to_have_text("Ask")
    expect(labels.nth(-1)).to_have_text("Search")
    ui.page.click(f"{LISTBOX} [role='option']:has-text('art movement')")
    ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#topic/${qid}`", arg=IMPRESSIONISM)


def test_wikidatas_topic_the_library_is_in_is_held_though_its_name_differs(ui, held):
    """Held is what your works are in, whatever the words matched it by."""
    _type(ui, "cinquecento")
    _announced(ui)

    _expect_options(ui, "Held: topics", ["16th century — period · Italian 1500s"])
    expect(ui.page.locator(f"{LISTBOX} [aria-labelledby='suggestions-registry-topics']")).to_have_count(0)


# -- the search results page ---------------------------------------------------------


def _results(ui, query):
    ui.open(f"#search?q={query}")
    # The Not held group's own note, and only once it is drawn: read before the
    # page is, a bare `#view p[aria-live]` is null, or the page before's.
    ui.page.wait_for_function(
        "() => { const note = document.querySelector(\"section[aria-labelledby='results-not-held'] p[aria-live]\");"
        " return note !== null && !note.textContent.startsWith('Asking'); }"
    )


def _expect_result_rows(ui, half, rows):
    """The results' `half` topics list holds `rows`, in order, whitespace-normalised; no list is no rows."""
    items = ui.page.locator(f"section[aria-labelledby='results-{half}-topics'] li")
    if rows:
        expect(items).to_have_text(rows, use_inner_text=True)
    else:
        expect(items).to_have_count(0)


def test_the_results_page_lists_the_librarys_topic_under_held_once(ui, held):
    _results(ui, "16th")

    _expect_result_rows(ui, "held", ["16th century — period"])
    _expect_result_rows(ui, "not-held", [])
    ui.page.click("section[aria-labelledby='results-held-topics'] a:has-text('16th century')")
    ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#topic/${qid}`", arg=SIXTEENTH)


def test_the_results_page_lists_wikidatas_topics_under_not_held(ui, held):
    _results(ui, "impressionism")

    _expect_result_rows(
        ui,
        "not-held",
        ["Impressionism — movement · art movement", "Impressionism — movement · music movement"],
    )
    expect(ui.page.locator("#view .results-none")).to_have_text("Nothing you hold matches.", use_inner_text=True)
    ui.page.click("section[aria-labelledby='results-not-held-topics'] li:has-text('art movement') a")
    ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#topic/${qid}`", arg=IMPRESSIONISM)


def test_the_results_page_puts_a_topic_the_library_is_in_under_held(ui, held):
    _results(ui, "cinquecento")

    _expect_result_rows(ui, "held", ["16th century — period · Italian 1500s"])
    _expect_result_rows(ui, "not-held", [])
    expect(ui.page.locator("#view .results-none")).to_be_hidden()


# -- with no User-Agent ------------------------------------------------------------


class TestWithNoRegistryConfigured:
    @pytest.fixture
    def registry(self):
        return None

    def test_library_topics_says_topics_need_it_and_offers_no_search(self, ui):
        ui.open("#topics")
        ui.page.wait_for_selector("#view h1:text-is('Topics')")

        note = ui.page.locator("#view p.note").first
        expect(note).to_contain_text("not set up", use_inner_text=True)
        expect(note).not_to_contain_text("WIKIDATA_USER_AGENT", use_inner_text=True)
        expect(ui.page.locator("#view").get_by_label("Find a topic", exact=True)).to_have_count(0)

    def test_a_topic_page_says_topics_need_it(self, ui):
        open_topic(ui)
        works_answered(ui)
        ui.page.wait_for_selector(f"{ARTISTS} p.note")

        # The head is the first panel, and says it in its own words, not a section's.
        head = ui.page.locator("#view .panel").first
        # No name to give it, so the route's own word, never the bare item (#359).
        expect(head.locator("h1")).to_have_text("Topic", use_inner_text=True)
        expect(head.locator("p.note")).to_contain_text("not set up", use_inner_text=True)
        expect(head.locator("p.note")).not_to_contain_text("WIKIDATA_USER_AGENT", use_inner_text=True)
        for where in (WORKS, ARTISTS):
            expect(ui.page.locator(f"{where} p.note")).to_contain_text("not set up", use_inner_text=True)
            expect(ui.page.locator(f"{where} p.note")).not_to_contain_text("WIKIDATA_USER_AGENT", use_inner_text=True)
