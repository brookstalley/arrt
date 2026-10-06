"""Library › Topics and the Topic page, in a real browser against a real server.

`build-plan-topics-and-destinations.md` Chunk 05. The index lists the topics the
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

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry
from payloads import a_run

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
ARTISTS = "section[aria-labelledby='topic-artists']"
HELD = "section[aria-labelledby='in-your-library']"
LISTBOX = "#search-suggestions"


def ref(qid: str, label: str, kind: TopicKind) -> RegistryTopicRef:
    return RegistryTopicRef(qid=ItemId(qid), label=RegistryText(label), kind=kind)


def topic(qid: str, label: str, *kinds: TopicKind, **fields) -> RegistryTopic:
    return RegistryTopic(qid=ItemId(qid), label=RegistryText(label), kinds=kinds, **fields)


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
def held(services, service):
    """Bruegel and two works of his in the library, identified, with their topics swept.

    Two works in the 16th century, so its count is not the 1 every topic would
    show by default; one of them, *The Hunters*, is also among the works
    Wikidata lists, which is the case that marks it held.
    """
    bruegel = service.add_artist(name="Pieter Bruegel the Elder", born=1525, died=1569)
    services.identity.set_artist_identity(bruegel.id, BRUEGEL)
    hunters = service.add_artwork(
        title="The Hunters in the Snow", artist_id=bruegel.id, date_created="1565", wikidata_qid=HUNTERS
    )
    corn = service.add_artwork(title="The Corn Harvest", artist_id=bruegel.id, date_created="1565", wikidata_qid=CORN)
    services.topic_sweep.run()
    return bruegel, hunters, corn


@pytest.fixture
def all_works(services):
    theme = services.display.add_theme(name="All works")
    services.display.make_default(theme.id)
    return theme


def open_topic(ui, qid=SIXTEENTH):
    ui.open(f"#topic/{qid}")
    ui.page.wait_for_selector(f"{HELD} h3")


def works_answered(ui):
    ui.page.wait_for_selector(f"{WORKS} table, {WORKS} p.note, {WORKS} p.muted:not([aria-live])")


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
        ui.page.wait_for_selector("#view h2:text-is('Topics')")

        headings = ui.page.locator("#view section h3").all_inner_texts()
        assert headings == ["Periods", "Movements", "Subjects", "Media"]
        periods = ui.page.locator("section[aria-labelledby='topics-period'] li").all_inner_texts()
        assert [" ".join(row.split()) for row in periods] == ["16th century · 2 works"]
        subjects = ui.page.locator("section[aria-labelledby='topics-subject'] li").all_inner_texts()
        assert [" ".join(row.split()) for row in subjects] == ["winter · 1 work"]
        assert (
            ui.page.locator("section[aria-labelledby='topics-movement'] p").inner_text() == "None of your works is in a movement."
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
        first = ui.page.locator("section[aria-labelledby='topics-subject'] li").first.inner_text()
        assert " ".join(first.split()) == "subject number 00 · 1 work"

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
        ui.page.click("section[aria-labelledby='topics-period'] button:text-is('16th century')")

        ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#topic/${qid}`", arg=SIXTEENTH)
        ui.page.wait_for_selector(f"{HELD} h3")
        assert ui.page.locator("#view button", has_text="←").first.inner_text() == "← Topics"

    def test_the_sidebar_offers_topics_under_artworks_after_themes(self, ui, held):
        ui.open("#collection")
        ui.page.wait_for_selector("#view h2")

        ui.page.get_by_role("link", name="Topics").click()
        ui.page.wait_for_selector("#view h2:text-is('Topics')")

    def test_find_a_topic_asks_wikidata_and_tells_like_names_apart(self, ui, held):
        ui.open("#topics")
        ui.page.get_by_label("Find a topic", exact=True).fill("impressionism")
        ui.page.click("#view button:text-is('Find')")

        ui.page.wait_for_selector("section[aria-labelledby='topic-search'] ul")
        assert "find=impressionism" in ui.page.evaluate("() => window.location.hash")
        # Not the top bar's `q`: its box would then claim the artworks were searched.
        assert ui.page.input_value("#search") == ""
        rows = [" ".join(t.split()) for t in ui.page.locator("section[aria-labelledby='topic-search'] li").all_inner_texts()]
        assert rows == ["Impressionism — movement art movement", "Impressionism — movement music movement"]
        ui.page.click("section[aria-labelledby='topic-search'] li:has-text('art movement') button")
        ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#topic/${qid}`", arg=IMPRESSIONISM)

    def test_a_search_finding_nothing_says_so(self, ui, held):
        ui.open("#topics?find=nothing")

        ui.page.wait_for_selector("section[aria-labelledby='topic-search'] p.muted:not([aria-live])")
        assert "Wikidata has no period, movement, subject or medium called “nothing”." in ui.text()


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

        assert ui.page.locator(f"{HELD} h3").inner_text() == "In your library (2)"
        assert sorted(ui.page.locator(f"{HELD} .card-title").all_inner_texts()) == sorted([hunters.title, corn.title])
        assert ui.page.locator(f"{WORKS} [aria-live]").inner_text() == "Asking Wikidata…"
        assert ui.page.locator(f"{ARTISTS} [aria-live]").inner_text() == "Asking Wikidata…"
        # The head is Wikidata's too, and is not held back by the slow sections.
        ui.page.wait_for_selector("#view h2:text-is('16th century')")
        assert ui.page.locator("#view dl.facts dd").inner_text() == "period"

        while len(waiting) < 2:
            ui.page.wait_for_timeout(50)
        for route in waiting:
            route.continue_()
        works_answered(ui)
        ui.page.wait_for_selector(f"{ARTISTS} ul")
        assert ui.page.locator(f"{WORKS} tbody tr").count() == 4

    def test_a_periods_works_are_headed_with_its_years(self, ui, held):
        open_topic(ui)
        works_answered(ui)

        assert ui.page.locator(f"{WORKS} h3").inner_text() == "Works from 1501–1600"

    @pytest.mark.parametrize("qid", [WINTER, BAROQUE], ids=["a subject", "a movement that is also a period"])
    def test_works_found_by_anything_but_a_period_claim_no_years(self, ui, held, qid):
        open_topic(ui, qid)
        works_answered(ui)

        assert ui.page.locator(f"{WORKS} h3").inner_text() == "Representative works"

    def test_each_work_carries_its_state_as_glyph_and_word(self, ui, held):
        open_topic(ui)
        works_answered(ui)

        states = {
            row.locator("td").nth(1).inner_text(): " ".join(row.locator("td").nth(4).inner_text().split())
            for row in ui.page.locator(f"{WORKS} tbody tr").all()
        }
        assert states == {
            "The Hunters in the Snow": "● Held",
            "The Harvesters": "◐ Not held · Image found",
            "Flammarion engraving": "○ No image known",
            f"No English title ({NAMELESS})": "○ No image known",
        }
        for glyph in ui.page.locator(f"{WORKS} .badge .glyph").all():
            assert glyph.get_attribute("aria-hidden") == "true"

    def test_on_a_phone_each_picture_shows_and_the_list_fits(self, ui, held, pictures_load):
        """The Topic page's list has a *By* column the Artist page's lacks, so it is the likeliest to run wide."""
        ui.page.set_viewport_size({"width": 390, "height": 900})
        open_topic(ui)
        works_answered(ui)

        for style in ("held", "not-held"):
            box = ui.page.locator(f"{WORKS} .work-pic-{style}").first.bounding_box()
            assert box is not None, f"the {style} picture is not drawn"
            assert min(box["width"], box["height"]) >= 48
        fits = ui.page.evaluate(
            "(s) => { const c = document.querySelector(`${s} .artist-works`); return c.scrollWidth <= c.clientWidth; }", WORKS
        )
        assert fits, "the list scrolls sideways"
        # Titles can break anywhere, so the table would squeeze them first; they keep a readable width.
        assert ui.page.locator(f"{WORKS} td.work-title").first.bounding_box()["width"] >= 112
        # Who made it folds under the title rather than being lost.
        flammarion = ui.page.locator(f"{WORKS} tbody tr", has_text="Flammarion engraving")
        assert flammarion.locator(".by-under").inner_text() == "Unknown maker"
        assert not flammarion.locator("td.by-col").is_visible()
        harvesters = ui.page.locator(f"{WORKS} tbody tr", has_text="The Harvesters")
        harvesters.locator(".by-under button:text-is('Pieter Bruegel the Elder')").click()
        ui.page.wait_for_selector("#view h2:has-text('Pieter Bruegel the Elder')")

    def _marks(self, ui):
        # Keyed by the title's own button: on a phone the cell also holds the year.
        return {
            row.locator("td.work-title button.row-title").inner_text(): row.locator("td").nth(4)
            for row in ui.page.locator(f"{WORKS} tbody tr").all()
        }

    def test_held_wanted_and_not_held_each_draw_their_picture_in_their_own_style(self, ui, held, want_item, pictures_load):
        """The owner's ruling on #172: held and image found were told apart by a picture only one of them had.

        Held draws the library's own thumbnail; not held draws Wikidata's under
        hatching; wanted (here with no picture known) says so in glyph and word.
        The hatching is on the not-held picture only.
        """
        want_item(NAMELESS, "An untitled work")
        open_topic(ui)
        works_answered(ui)
        marks = self._marks(ui)

        hunters = marks["The Hunters in the Snow"]
        assert hunters.locator(".work-pic-held img").get_attribute("src").startswith("/api/works/")
        assert " ".join(hunters.inner_text().split()) == "● Held"
        harvesters = marks["The Harvesters"]
        assert harvesters.locator(".work-pic-not-held img").get_attribute("src").startswith("https://commons.wikimedia.org/")
        nameless = marks[f"No English title ({NAMELESS})"]
        assert " ".join(nameless.inner_text().split()) == "◑ Wanted"
        assert nameless.locator(".work-pic").count() == 0
        assert marks["Flammarion engraving"].locator(".work-pic").count() == 0
        assert ui.page.locator(f"{WORKS} .work-pic-not-held").count() == 1
        assert ui.page.locator(f"{WORKS} .work-pic-held").count() == 1

    def test_a_wanted_work_with_a_picture_draws_it_wanted_not_hatched(self, ui, held, want_item, pictures_load):
        want_item(HARVESTERS, "The Harvesters")
        open_topic(ui)
        works_answered(ui)
        harvesters = self._marks(ui)["The Harvesters"]

        assert " ".join(harvesters.inner_text().split()) == "◑ Wanted"
        assert harvesters.locator(".work-pic-wanted img").count() == 1
        assert harvesters.locator(".work-pic-not-held").count() == 0

    def test_a_held_work_that_is_also_wanted_reads_held(self, ui, held, want_item, pictures_load):
        """A wanted work since acquired: the server reports both, and held wins on the page."""
        want_item(HUNTERS, "The Hunters in the Snow")
        open_topic(ui)
        works_answered(ui)
        hunters = self._marks(ui)["The Hunters in the Snow"]

        assert " ".join(hunters.inner_text().split()) == "● Held"
        assert hunters.locator(".work-pic-held").count() == 1
        assert hunters.locator(".work-pic-wanted").count() == 0

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

        assert {title: " ".join(mark.inner_text().split()) for title, mark in self._marks(ui).items()} == {
            "The Hunters in the Snow": "● Held",
            "The Harvesters": "◐ Not held · Image found",
            "Flammarion engraving": "○ No image known",
            f"No English title ({NAMELESS})": "◑ Wanted",
        }

    def test_makers_are_named_and_an_unknown_one_is_said(self, ui, held):
        open_topic(ui)
        works_answered(ui)

        makers = {
            row.locator("td").nth(1).inner_text(): row.locator("td").nth(2).inner_text()
            for row in ui.page.locator(f"{WORKS} tbody tr").all()
        }
        assert makers["Flammarion engraving"] == "Unknown maker"
        assert makers[f"No English title ({NAMELESS})"] == "—"
        # The By column's own link: the row also carries a copy under the title, shown only on a phone.
        ui.page.click(f"{WORKS} tr:has-text('The Harvesters') td.by-col button:text-is('Pieter Bruegel the Elder')")
        ui.page.wait_for_selector("#view h2:has-text('Pieter Bruegel the Elder')")

    def test_a_held_work_offers_no_tick_box(self, ui, held):
        open_topic(ui)
        works_answered(ui)

        boxes = {
            row.locator("td").nth(1).inner_text(): row.locator("input[type='checkbox']").count()
            for row in ui.page.locator(f"{WORKS} tbody tr").all()
        }
        assert boxes == {
            "The Hunters in the Snow": 0,
            "The Harvesters": 1,
            "Flammarion engraving": 1,
            f"No English title ({NAMELESS})": 1,
        }

    def test_artists_are_listed_and_open_their_page(self, ui, held):
        bruegel, _hunters, _corn = held
        open_topic(ui)
        ui.page.wait_for_selector(f"{ARTISTS} ul")

        rows = [" ".join(t.split()) for t in ui.page.locator(f"{ARTISTS} li").all_inner_texts()]
        assert rows == [
            "Pieter Bruegel the Elder 1525–1569 · 40 works with an image ● In your library",
            "Rembrandt 1606–1669 · 1 work with an image ○ Not held",
        ]
        ui.page.click(f"{ARTISTS} button:text-is('Pieter Bruegel the Elder')")
        ui.page.wait_for_function("(id) => window.location.hash.startsWith(`#artist/${id}`)", arg=bruegel.id)

    def test_registry_text_arrives_as_words_and_the_link_is_built_from_the_qid(self, ui, held):
        open_topic(ui)
        ui.page.wait_for_selector("#view h2:text-is('16th century')")
        # The heading can paint before the description does, so the description
        # is waited for in its own right before it is counted.
        escaped = ui.page.get_by_text('century <img src=x onerror="window.pwned=1">')
        escaped.wait_for()

        assert escaped.count() == 1
        assert ui.page.evaluate("() => window.pwned") is None
        link = ui.page.locator("#view a:text-is('Wikidata Q7017')")
        assert link.get_attribute("href") == f"https://www.wikidata.org/wiki/{SIXTEENTH}"

    def test_an_outage_leaves_the_library_half_standing(self, ui, held, registry):
        _bruegel, _hunters, _corn = held
        registry.failing = True
        open_topic(ui)
        works_answered(ui)
        ui.page.wait_for_selector(f"{ARTISTS} p.note")

        assert "could not be asked" in ui.page.locator(f"{WORKS} p.note").inner_text()
        assert "could not be asked" in ui.page.locator(f"{ARTISTS} p.note").inner_text()
        assert ui.page.locator(f"{HELD} .card-title").count() == 2

    def test_a_topic_none_of_your_works_is_in_still_has_its_page_named_by_wikidata(self, ui, held):
        """The facets hold no name for it, so the head's name is Wikidata's, written in once it answers."""
        open_topic(ui, IMPRESSIONISM)

        assert ui.page.locator(f"{HELD} p").inner_text() == "None of your works in circulation is in this topic."
        ui.page.wait_for_selector("#view h2:text-is('Impressionism')")
        assert ui.page.locator("#view dl.facts dd").inner_text() == "movement"

    def test_an_address_that_is_not_a_qid_says_so(self, ui):
        ui.open("#topic/nonsense")
        ui.page.wait_for_selector('#view h2:text-is("That is not a topic\'s address")')
        ui.page.click("#view button:text-is('All topics')")
        ui.page.wait_for_selector("#view h2:text-is('Topics')")


# -- Get, into a theme named after the topic ---------------------------------------


def test_get_from_a_topic_defaults_to_a_new_theme_named_after_it(ui, services, held, all_works):
    """The default reads as the topic's name, with no field to fill, and Get makes the theme.

    The owner's review of the screens (`build-plan-topics-and-destinations.md`
    Chunk 06), on the *winter* page with no theme named *winter*."""
    bodies = record_gets(ui)
    open_topic(ui)
    works_answered(ui)
    ui.page.wait_for_selector(f"{WORKS} .get-into option[value='new']", state="attached")

    picker = ui.page.locator(WORKS).get_by_label("Add to", exact=True)
    assert picker.evaluate("node => node.selectedOptions[0].textContent") == "16th century (new theme)"
    assert not ui.page.locator(WORKS).get_by_label("New theme's name").is_visible()
    ui.page.check(f"{WORKS} tr:has-text('The Harvesters') input[type='checkbox']")
    ui.page.click(f"{WORKS} .get-control button.action")

    ui.page.wait_for_selector(f"{WORKS} .get-status button:text-is('Open the Get')")
    created = next(p.theme for p in services.display.survey_themes() if p.theme.name == "16th century")
    assert bodies == [{"qids": [HARVESTERS], "theme_id": created.id}]
    assert (
        " ".join(ui.page.locator(f"{WORKS} .get-status").inner_text().split()) == "Getting 1 work into 16th century. Open the Get"
    )


def test_get_from_a_topic_whose_name_is_a_theme_joins_it(ui, services, held, all_works):
    theme = services.display.add_theme(name="16th Century")
    bodies = record_gets(ui)
    open_topic(ui)
    works_answered(ui)
    ui.page.wait_for_selector(f"{WORKS} .get-into option[value='new']", state="attached")

    ui.page.check(f"{WORKS} tr:has-text('The Harvesters') input[type='checkbox']")
    ui.page.click(f"{WORKS} .get-control button.action")

    ui.page.wait_for_selector(f"{WORKS} .get-status button:text-is('Open the Get')")
    assert bodies == [{"qids": [HARVESTERS], "theme_id": theme.id}]


# -- the top bar's dropdown --------------------------------------------------------


def _type(ui, words):
    ui.open("#walls")
    ui.page.wait_for_selector("#view h2")
    ui.page.click("#search")
    ui.page.keyboard.type(words)
    ui.page.wait_for_selector(f"{LISTBOX}:not([hidden]) [role='option']")


def _options(ui, group):
    listbox = ui.page.get_by_role("listbox", name="Suggestions")
    return [
        " ".join(t.split()) for t in listbox.get_by_role("group", name=group, exact=True).get_by_role("option").all_inner_texts()
    ]


def _announced(ui):
    ui.page.wait_for_function(
        "() => document.querySelector('#search-suggestions + [aria-live]').textContent.startsWith('Wikidata')"
    )


def test_the_dropdown_has_a_topics_group_after_works(ui, service, held):
    service.add_artwork(title="A 16th-century copy")
    _type(ui, "16th")
    _announced(ui)

    assert _options(ui, "Held: topics") == ["16th century — period"]
    # Wikidata's 16th century is the library's, already shown, so not offered twice.
    assert ui.page.locator(f"{LISTBOX} [aria-labelledby='suggestions-registry-topics']").count() == 0
    assert ui.page.locator(f"{LISTBOX} .search-suggestions-label").all_text_contents() == [
        "Held: works",
        "Held: topics",
        "Ask",
        "Search",
    ]

    ui.page.click(f"{LISTBOX} [role='option']:has-text('16th century — period')")
    ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#topic/${qid}`", arg=SIXTEENTH)


def test_the_dropdown_offers_wikidatas_topics_with_their_descriptions(ui, held):
    _type(ui, "impressionism")
    _announced(ui)

    assert _options(ui, "Not held: topics") == [
        "Impressionism — movement · art movement",
        "Impressionism — movement · music movement",
    ]
    labels = ui.page.locator(f"{LISTBOX} .search-suggestions-label").all_text_contents()
    assert labels[-3:] == ["Not held: topics", "Ask", "Search"]
    ui.page.click(f"{LISTBOX} [role='option']:has-text('art movement')")
    ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#topic/${qid}`", arg=IMPRESSIONISM)


def test_wikidatas_topic_the_library_is_in_is_held_though_its_name_differs(ui, held):
    """Held is what your works are in, whatever the words matched it by."""
    _type(ui, "cinquecento")
    _announced(ui)

    assert _options(ui, "Held: topics") == ["16th century — period · Italian 1500s"]
    assert ui.page.locator(f"{LISTBOX} [aria-labelledby='suggestions-registry-topics']").count() == 0


# -- the search results page ---------------------------------------------------------


def _results(ui, query):
    ui.open(f"#search?q={query}")
    # The Not held group's own note, and only once it is drawn: read before the
    # page is, a bare `#view p[aria-live]` is null, or the page before's.
    ui.page.wait_for_function(
        "() => { const note = document.querySelector(\"section[aria-labelledby='results-not-held'] p[aria-live]\");"
        " return note !== null && !note.textContent.startsWith('Asking'); }"
    )


def _result_rows(ui, half):
    return [
        " ".join(t.split()) for t in ui.page.locator(f"section[aria-labelledby='results-{half}-topics'] li").all_inner_texts()
    ]


def test_the_results_page_lists_the_librarys_topic_under_held_once(ui, held):
    _results(ui, "16th")

    assert _result_rows(ui, "held") == ["16th century — period"]
    assert _result_rows(ui, "not-held") == []
    ui.page.click("section[aria-labelledby='results-held-topics'] button:has-text('16th century')")
    ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#topic/${qid}`", arg=SIXTEENTH)


def test_the_results_page_lists_wikidatas_topics_under_not_held(ui, held):
    _results(ui, "impressionism")

    assert _result_rows(ui, "not-held") == [
        "Impressionism — movement · art movement",
        "Impressionism — movement · music movement",
    ]
    assert ui.page.locator("#view .results-none").inner_text() == "Nothing you hold matches."
    ui.page.click("section[aria-labelledby='results-not-held-topics'] li:has-text('art movement') button")
    ui.page.wait_for_function("(qid) => window.location.hash.split('?')[0] === `#topic/${qid}`", arg=IMPRESSIONISM)


def test_the_results_page_puts_a_topic_the_library_is_in_under_held(ui, held):
    _results(ui, "cinquecento")

    assert _result_rows(ui, "held") == ["16th century — period · Italian 1500s"]
    assert _result_rows(ui, "not-held") == []
    assert ui.page.locator("#view .results-none").is_hidden()


# -- with no User-Agent ------------------------------------------------------------


class TestWithNoRegistryConfigured:
    @pytest.fixture
    def registry(self):
        return None

    def test_library_topics_says_topics_need_it_and_offers_no_search(self, ui):
        ui.open("#topics")
        ui.page.wait_for_selector("#view h2:text-is('Topics')")

        assert "WIKIDATA_USER_AGENT" in ui.page.locator("#view p.note").first.inner_text()
        assert ui.page.locator("#view").get_by_label("Find a topic", exact=True).count() == 0

    def test_a_topic_page_says_topics_need_it(self, ui):
        open_topic(ui)
        works_answered(ui)
        ui.page.wait_for_selector(f"{ARTISTS} p.note")

        # The head is the first panel, and says it in its own words, not a section's.
        head = ui.page.locator("#view .panel").first
        assert head.locator("h2").inner_text() == f"Wikidata {SIXTEENTH}"
        assert "WIKIDATA_USER_AGENT" in head.locator("p.note").inner_text()
        for where in (WORKS, ARTISTS):
            assert "WIKIDATA_USER_AGENT" in ui.page.locator(f"{where} p.note").inner_text()
