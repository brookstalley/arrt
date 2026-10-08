"""Get in the client, in a real browser against a real server.

Ruling 3: Get is an action on a selection of works the library does not hold, on
the Artist page's *Their work* and the results page, and on a work's own page.
The page stays where it is and says what started, with a link to the run.

The registry is a fake installed where the entry point builds Wikidata's. `POST
/api/gets` is answered by the test, which records what the client sent: what is
under test here is which items the client asks for, into which theme, and what it
says afterwards. The server side of a Get is `tests/integration/test_get_surface.py`'s
and `tests/integration/test_get_destination.py`'s. Themes are the real server's,
so a theme the control creates is one the catalogue holds.

Every Get names its destination (`build-plan-topics-and-destinations.md` Chunk
02): *Add to*, the default theme first and selected, which sends no `theme_id`;
any other theme, which sends its id; or *New theme…*, created by `POST
/api/themes` before the Get starts. A name that is already a theme joins it.
"""

import json

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the browser suite needs its own dependency group: uv sync --group browser",
)

from fakes import FakeRegistry
from payloads import a_candidate, a_candidate_page, a_card, a_run, a_run_view

from arrt.library.registry import (
    RegistryArtist,
    RegistryCreator,
    RegistryWork,
    RegistryWorkEntry,
    RegistryWorkMatch,
)
from arrt.persistence.discovery_records import ResolutionStatus, RunStatus, WorkProvenance

BRUEGEL = "Q43270"
HUNTERS = "Q500985"
HARVESTERS = "Q1170284"
CORN = "Q1170285"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/Hunters.jpg"
BY = RegistryCreator(qid=BRUEGEL, name="Pieter Brueghel the Elder")
GET_ID = "get-1"


@pytest.fixture
def registry():
    return FakeRegistry(
        works={
            HUNTERS: RegistryWork(qid=HUNTERS, title="The Hunters in the Snow", sitelinks=39, image=COMMONS, creators=(BY,)),
        },
        artists={
            BRUEGEL: RegistryArtist(
                qid=BRUEGEL,
                name="Pieter Brueghel the Elder",
                works=(
                    RegistryWorkEntry(qid=HUNTERS, title="The Hunters in the Snow", sitelinks=39, image=COMMONS),
                    RegistryWorkEntry(qid=HARVESTERS, title="The Harvesters", sitelinks=25),
                    RegistryWorkEntry(qid=CORN, title="The Corn Harvest", sitelinks=12, image=COMMONS),
                ),
                works_total=3,
            ),
        },
        matches={
            "harvest": [
                RegistryWorkMatch(qid=HARVESTERS, title="The Harvesters", sitelinks=25, creator=BY),
                RegistryWorkMatch(qid=CORN, title="The Corn Harvest", sitelinks=12, image=COMMONS, creator=BY),
            ]
        },
    )


@pytest.fixture
def hunters_held(services, service):
    """The Hunters in the Snow in the library, matched to its item."""
    work = service.add_artwork(title="The Hunters in the Snow")
    services.identity.set_work_identity(work.id, HUNTERS)
    return work


@pytest.fixture
def all_works(services):
    """The default theme, named as the owner's catalogue names it."""
    theme = services.display.add_theme(name="All works")
    services.display.make_default(theme.id)
    return theme


@pytest.fixture
def winter(services):
    """A theme that is not the default."""
    return services.display.add_theme(name="Winter")


def theme_names(services) -> list[str]:
    return sorted(placement.theme.name for placement in services.display.survey_themes())


def a_get(skipped=(), *, started=True) -> dict:
    run = a_run(run_id=GET_ID, kind="get", intent=None, status=RunStatus.RESOLVING_IMAGES.value)
    return {"run": run.model_dump(mode="json") if started else None, "skipped": list(skipped)}


def answer_gets(ui, answer) -> list[list[str]]:
    """Answer every Get with `answer`, and return what each one asked for."""
    sent: list[list[str]] = []

    def handler(route):
        sent.append(json.loads(route.request.post_data)["qids"])
        route.fulfill(status=200, content_type="application/json", body=json.dumps(answer))

    ui.page.route("**/api/gets", handler)
    return sent


def record_gets(ui, answer) -> list[dict]:
    """Answer every Get with `answer`, and return each request's whole body."""
    bodies: list[dict] = []

    def handler(route):
        bodies.append(json.loads(route.request.post_data))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(answer))

    ui.page.route("**/api/gets", handler)
    return bodies


def record_writes(ui) -> list[str]:
    """Every POST the page makes, by path, in the order it made them."""
    writes: list[str] = []
    ui.page.on("request", lambda request: writes.append(request.url.split("/", 3)[3]) if request.method == "POST" else None)
    return writes


def themes_read(ui, scope="#view") -> None:
    """Wait for *Add to* to hold the themes rather than say it is reading them."""
    ui.page.wait_for_selector(f"{scope} .get-into option[value='new']", state="attached")


def select_mode(ui):
    """Turn *Select* on. A list's ticks and its Get live in the selection model
    every list shares (`core/selecting.js`), shown only in *Select* mode, so a
    tick is reached the way a curator reaches it."""
    ui.page.click("#view button.select-toggle")
    ui.page.wait_for_selector("#view .selection", state="visible")


def add_to(ui, scope="#view"):
    return ui.page.locator(scope).get_by_label("Add to", exact=True)


def tick_the_harvesters_and_get(ui):
    ui.open(f"#artist/{BRUEGEL}")
    select_mode(ui)
    ui.page.locator("section table tr:has-text('The Harvesters') input[type='checkbox']").check()
    themes_read(ui)


def status_text(ui) -> str:
    return " ".join(ui.page.locator("#view .get-status").inner_text().split())


# -- the Artist page ---------------------------------------------------------------


def test_their_work_gets_exactly_the_ticked_works_the_library_does_not_hold(ui, hunters_held, all_works):
    sent = answer_gets(ui, a_get())
    ui.open(f"#artist/{BRUEGEL}")
    select_mode(ui)
    table = ui.page.locator("section table")
    table.wait_for()

    assert table.locator("tr:has-text('The Hunters in the Snow') input[type='checkbox']").count() == 0, "a held row has no box"
    button = ui.page.locator("#view .get-control button.action")
    assert (button.inner_text(), button.is_disabled()) == ("Get", True)
    table.locator("tr:has-text('The Harvesters') input[type='checkbox']").check()
    table.locator("tr:has-text('The Corn Harvest') input[type='checkbox']").check()
    assert button.inner_text() == "Get 2 works"
    button.click()

    ui.page.wait_for_selector("#view .get-status a:text-is('Open the Get')")
    assert sent == [[HARVESTERS, CORN]]
    assert status_text(ui) == "Getting 2 works into All works. Open the Get"
    assert table.locator("input[type='checkbox']:checked").count() == 0, "the ticks are cleared once got"
    assert button.is_disabled()


def test_unticking_the_last_work_disables_get_again(ui):
    ui.open(f"#artist/{BRUEGEL}")
    select_mode(ui)
    box = ui.page.locator("section table tr:has-text('The Harvesters') input[type='checkbox']")
    box.wait_for()
    button = ui.page.locator("#view .get-control button.action")

    box.check()
    box.uncheck()

    assert (button.inner_text(), button.is_disabled()) == ("Get", True)


def test_the_announcement_opens_the_run(ui):
    answer_gets(ui, a_get())
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(a_run(run_id=GET_ID, kind="get", intent=None)))
    ui.open(f"#artist/{BRUEGEL}")
    select_mode(ui)
    ui.page.locator("section table tr:has-text('The Harvesters') input[type='checkbox']").check()
    ui.page.click("#view .get-control button.action")

    ui.page.click("#view .get-status a:text-is('Open the Get')")

    ui.page.wait_for_function(f"() => window.location.hash.startsWith('#get/{GET_ID}')")


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        pytest.param(
            a_get([{"qid": CORN, "reason": "being_got"}]),
            "Getting 1 work into All works. Left out: 1 is already being got. Open the Get",
            id="one left out",
        ),
        pytest.param(
            a_get([{"qid": HARVESTERS, "reason": "not_found"}, {"qid": CORN, "reason": "not_found"}], started=False),
            "Nothing was started. Left out: 2 are not works Wikidata has.",
            id="everything left out",
        ),
    ],
)
def test_what_a_get_left_out_is_said(ui, answer, said, all_works):
    answer_gets(ui, answer)
    ui.open(f"#artist/{BRUEGEL}")
    select_mode(ui)
    table = ui.page.locator("section table")
    table.locator("tr:has-text('The Harvesters') input[type='checkbox']").check()
    table.locator("tr:has-text('The Corn Harvest') input[type='checkbox']").check()

    ui.page.click("#view .get-control button.action")

    ui.page.wait_for_function("() => document.querySelector('#view .get-status').textContent.length > 0")
    assert status_text(ui) == said


def test_a_refused_get_is_said_beside_get_and_keeps_the_ticks(ui):
    """The refusal sits after the Get it refused, naming the act, and the ticks
    and the button stay so that trying again is one press (`core/acting.js`)."""
    ui.serve(
        "**/api/gets", (400, {"error": "A Get names its works by their Wikidata items, and this deployment has no registry."})
    )
    ui.open(f"#artist/{BRUEGEL}")
    select_mode(ui)
    box = ui.page.locator("section table tr:has-text('The Harvesters') input[type='checkbox']")
    box.check()
    get = ui.page.locator("#view .get-control button.action")

    get.click()

    assert ui.said_beside(get) == (
        "Couldn't get 1 work: A Get names its works by their Wikidata items, and this deployment has no registry. "
        "Nothing was changed."
    )
    assert box.is_checked()
    assert not get.is_disabled()


# -- the results page ----------------------------------------------------------------


def test_the_results_page_gets_the_ticked_wikidata_works(ui):
    sent = answer_gets(ui, a_get())
    ui.open("#search?q=harvest")
    select_mode(ui)
    box = ui.page.locator("#view .results-list li:has-text('The Corn Harvest') input[type='checkbox']")
    box.wait_for()

    box.check()
    ui.page.click("#view .get-control button.action")

    ui.page.wait_for_selector("#view .get-status a:text-is('Open the Get')")
    assert sent == [[CORN]]


# -- one work's page -----------------------------------------------------------------


def test_a_work_not_held_is_got_from_its_own_page(ui, all_works):
    sent = answer_gets(ui, a_get())
    ui.open(f"#work/{HUNTERS}")
    button = ui.page.locator("#view button:text-is('Get this work')")

    button.click()

    ui.page.wait_for_selector("#view .get-status a:text-is('Open the Get')")
    assert sent == [[HUNTERS]]
    assert status_text(ui) == "Getting 1 work into All works. Open the Get"
    assert button.is_disabled(), "got once, a second press would only be left out"
    assert ui.page.locator("#view button:has-text('Search museums'), #view :is(a, button):has-text('Ask about')").count() == 0


# -- where the works go: Add to ----------------------------------------------------


def test_add_to_is_a_labelled_select_with_the_default_first_and_selected(ui, winter, all_works):
    """The default first whatever order the themes were made in, then the others, then New theme…."""
    tick_the_harvesters_and_get(ui)

    picker = add_to(ui)
    assert picker.evaluate("node => node.tagName") == "SELECT"
    assert [text.strip() for text in picker.locator("option").all_inner_texts()] == ["All works", "Winter", "New theme…"]
    assert picker.evaluate("node => node.selectedOptions[0].textContent") == "All works"
    assert not ui.page.locator("#view").get_by_label("New theme's name").is_visible(), "no name is asked for until New theme… is"


def test_the_default_sends_no_theme_id_and_the_confirmation_names_it(ui, winter, all_works):
    bodies = record_gets(ui, a_get())
    tick_the_harvesters_and_get(ui)

    ui.page.click("#view .get-control button.action")

    ui.page.wait_for_selector("#view .get-status a:text-is('Open the Get')")
    assert bodies == [{"qids": [HARVESTERS]}], "the default is the absence of a theme_id, never a null or the default's id"
    assert status_text(ui) == "Getting 1 work into All works. Open the Get"


def test_picking_a_theme_sends_its_id_and_the_confirmation_names_it(ui, winter, all_works):
    bodies = record_gets(ui, a_get())
    tick_the_harvesters_and_get(ui)

    add_to(ui).select_option(label="Winter")
    ui.page.click("#view .get-control button.action")

    ui.page.wait_for_selector("#view .get-status a:text-is('Open the Get')")
    assert bodies == [{"qids": [HARVESTERS], "theme_id": winter.id}]
    assert status_text(ui) == "Getting 1 work into Winter. Open the Get"


def test_a_new_name_creates_the_theme_first_and_sends_its_id(ui, services, all_works):
    bodies = record_gets(ui, a_get())
    writes = record_writes(ui)
    tick_the_harvesters_and_get(ui)

    add_to(ui).select_option(label="New theme…")
    name = ui.page.locator("#view").get_by_label("New theme's name")
    name.fill("16th century")
    ui.page.click("#view .get-control button.action")

    ui.page.wait_for_selector("#view .get-status a:text-is('Open the Get')")
    created = next(p.theme for p in services.display.survey_themes() if p.theme.name == "16th century")
    assert writes == ["api/themes", "api/gets"], "the theme exists before the Get that names it starts"
    assert bodies == [{"qids": [HARVESTERS], "theme_id": created.id}]
    assert status_text(ui) == "Getting 1 work into 16th century. Open the Get"
    assert add_to(ui).evaluate("node => node.selectedOptions[0].textContent") == "16th century", "the new theme stays chosen"
    assert not name.is_visible()


def test_a_second_get_into_a_new_theme_joins_it_rather_than_making_another(ui, services, all_works):
    bodies = record_gets(ui, a_get())
    tick_the_harvesters_and_get(ui)
    add_to(ui).select_option(label="New theme…")
    ui.page.locator("#view").get_by_label("New theme's name").fill("16th century")
    ui.page.click("#view .get-control button.action")
    ui.page.wait_for_selector("#view .get-status a:text-is('Open the Get')")

    ui.page.locator("section table tr:has-text('The Corn Harvest') input[type='checkbox']").check()
    with ui.page.expect_response("**/api/gets"):
        ui.page.click("#view .get-control button.action")

    assert theme_names(services) == ["16th century", "All works"]
    assert len(bodies) == 2
    assert bodies[0]["theme_id"] == bodies[1]["theme_id"]


def test_a_typed_name_that_is_already_a_theme_joins_it(ui, services, winter, all_works):
    """The owner's ruling, a taken name joins, holds for a typed name as for a given one."""
    bodies = record_gets(ui, a_get())
    writes = record_writes(ui)
    tick_the_harvesters_and_get(ui)

    add_to(ui).select_option(label="New theme…")
    ui.page.locator("#view").get_by_label("New theme's name").fill(" winter ")
    ui.page.click("#view .get-control button.action")

    ui.page.wait_for_selector("#view .get-status a:text-is('Open the Get')")
    assert writes == ["api/gets"]
    assert bodies == [{"qids": [HARVESTERS], "theme_id": winter.id}]
    assert theme_names(services) == ["All works", "Winter"]
    assert status_text(ui) == "Getting 1 work into Winter. Open the Get"


def test_with_no_default_the_first_choice_says_the_works_join_no_theme(ui, winter):
    bodies = record_gets(ui, a_get())
    tick_the_harvesters_and_get(ui)

    assert add_to(ui).evaluate("node => node.selectedOptions[0].textContent") == "No theme (none is the default)"
    ui.page.click("#view .get-control button.action")

    ui.page.wait_for_selector("#view .get-status a:text-is('Open the Get')")
    assert bodies == [{"qids": [HARVESTERS]}]
    assert status_text(ui) == "Getting 1 work into no theme. Open the Get"


def test_themes_that_cannot_be_read_start_nothing_and_say_why(ui, all_works):
    """A Get must not quietly go to the default because the choice could not be offered."""
    bodies = record_gets(ui, a_get())
    ui.serve("**/api/themes", (500, {"error": "The theme listing failed."}))
    ui.open(f"#artist/{BRUEGEL}")
    select_mode(ui)
    ui.page.locator("section table tr:has-text('The Harvesters') input[type='checkbox']").check()
    ui.page.wait_for_selector("#view .get-into option:text-is('The themes could not be read')", state="attached")

    ui.page.click("#view .get-control button.action")

    ui.page.wait_for_selector("text=The theme listing failed.")
    assert bodies == []


# -- a caller's default name ---------------------------------------------------------
#
# A Topic page passes its topic's name (`test_topics.py`). These mount the control
# themselves, from the module every screen imports it from, so each case is one
# the Topic page's fixtures need not be arranged to reach.


def mount_with_a_default_name(ui, default_name: str) -> None:
    ui.open("#queue")
    ui.page.evaluate(
        """async ([name, qid]) => {
            const { getSelection } = await import("/static/core/getting.js");
            const getting = getSelection({ defaultName: name });
            const host = document.createElement("section");
            host.id = "harness";
            host.append(getting.box(qid, "The Harvesters"), getting.node);
            document.body.append(host);
        }""",
        [default_name, HARVESTERS],
    )
    themes_read(ui, "#harness")
    ui.page.check("#harness input[type='checkbox']")


def harness_get(ui) -> str:
    ui.page.click("#harness .get-control button.action")
    ui.page.wait_for_selector("#harness .get-status a:text-is('Open the Get')")
    return " ".join(ui.page.locator("#harness .get-status").inner_text().split())


def test_a_default_name_that_is_already_a_theme_selects_it_rather_than_creating_a_second(ui, services, winter, all_works):
    bodies = record_gets(ui, a_get())
    writes = record_writes(ui)
    mount_with_a_default_name(ui, "WINTER")

    assert [text.strip() for text in add_to(ui, "#harness").locator("option").all_inner_texts()] == [
        "All works",
        "Winter",
        "New theme…",
    ], "a name that is a theme is not offered again as a new one"
    assert add_to(ui, "#harness").evaluate("node => node.selectedOptions[0].textContent") == "Winter"
    assert not ui.page.locator("#harness").get_by_label("New theme's name").is_visible()
    said = harness_get(ui)

    assert writes == ["api/gets"]
    assert bodies == [{"qids": [HARVESTERS], "theme_id": winter.id}]
    assert theme_names(services) == ["All works", "Winter"]
    assert said == "Getting 1 work into Winter. Open the Get"


def test_a_default_name_that_is_the_default_theme_sends_no_theme_id(ui, all_works):
    bodies = record_gets(ui, a_get())
    mount_with_a_default_name(ui, "All works")

    assert [text.strip() for text in add_to(ui, "#harness").locator("option").all_inner_texts()] == ["All works", "New theme…"]
    harness_get(ui)

    assert bodies == [{"qids": [HARVESTERS]}]


def test_a_default_name_that_is_no_theme_yet_is_offered_as_a_new_one(ui, services, winter, all_works):
    """The name is its own option, chosen, and Get makes the theme before the Get that names it.

    The owner's review (`build-plan-topics-and-destinations.md` Chunk 06): the
    default reads as the name, and no field is shown while nothing needs typing.
    *Winter* is here so the option's place, after every theme and before *New
    theme…*, is an order three themes could get wrong."""
    bodies = record_gets(ui, a_get())
    writes = record_writes(ui)
    mount_with_a_default_name(ui, "16th century")

    picker = add_to(ui, "#harness")
    assert [text.strip() for text in picker.locator("option").all_inner_texts()] == [
        "All works",
        "Winter",
        "16th century (new theme)",
        "New theme…",
    ]
    assert picker.evaluate("node => node.selectedOptions[0].textContent") == "16th century (new theme)"
    assert not ui.page.locator("#harness").get_by_label("New theme's name").is_visible(), "nothing is typed, so nothing is asked"
    assert theme_names(services) == ["All works", "Winter"], "offering the name makes no theme"
    said = harness_get(ui)

    created = next(p.theme for p in services.display.survey_themes() if p.theme.name == "16th century")
    assert writes == ["api/themes", "api/gets"], "the theme exists before the Get that names it starts"
    assert bodies == [{"qids": [HARVESTERS], "theme_id": created.id}]
    assert said == "Getting 1 work into 16th century. Open the Get"
    assert [text.strip() for text in picker.locator("option").all_inner_texts()] == [
        "All works",
        "Winter",
        "16th century",
        "New theme…",
    ], "made, the name is a theme like any other and is no longer offered as new"
    assert picker.evaluate("node => node.selectedOptions[0].textContent") == "16th century"


def test_a_second_get_from_a_default_name_joins_the_theme_the_first_made(ui, services, all_works):
    bodies = record_gets(ui, a_get())
    writes = record_writes(ui)
    mount_with_a_default_name(ui, "16th century")
    harness_get(ui)

    ui.page.check("#harness input[type='checkbox']")
    with ui.page.expect_response("**/api/gets"):
        ui.page.click("#harness .get-control button.action")

    assert theme_names(services) == ["16th century", "All works"]
    assert writes == ["api/themes", "api/gets", "api/gets"]
    assert len(bodies) == 2
    assert bodies[0]["theme_id"] == bodies[1]["theme_id"]


def test_new_theme_beside_a_default_name_asks_for_a_name_of_its_own(ui, services, all_works):
    """*New theme…* is for a name other than the one offered, so its field starts empty,
    and it goes again when the offered name is chosen back."""
    bodies = record_gets(ui, a_get())
    mount_with_a_default_name(ui, "16th century")
    picker = add_to(ui, "#harness")
    name = ui.page.locator("#harness").get_by_label("New theme's name")

    picker.select_option(label="New theme…")
    assert name.is_visible()
    assert name.input_value() == ""

    picker.select_option(label="16th century (new theme)")
    assert not name.is_visible()

    picker.select_option(label="New theme…")
    name.fill("Snow")
    said = harness_get(ui)

    created = next(p.theme for p in services.display.survey_themes() if p.theme.name == "Snow")
    assert bodies == [{"qids": [HARVESTERS], "theme_id": created.id}]
    assert theme_names(services) == ["All works", "Snow"], "the offered name is made only when it is the one chosen"
    assert said == "Getting 1 work into Snow. Open the Get"


# -- the run, in Queue and on its own screen ------------------------------------------


def test_queue_lists_a_get_as_one(ui):
    ui.serve(
        "**/api/runs",
        {
            "runs": [a_run(run_id=GET_ID, kind="get", intent=None).model_dump(mode="json")],
            "count": 1,
            "total": 1,
            "truncated": False,
        },
    )
    ui.open("#queue")
    ui.page.wait_for_selector("#view table")

    row = " ".join(ui.page.locator("#view tbody tr").first.inner_text().split())
    assert row.startswith("Works you chose Get "), row


@pytest.mark.parametrize(
    ("status", "said"),
    [
        pytest.param(RunStatus.RESOLVING_IMAGES.value, "Looking for images of the 2 works you chose.", id="running"),
        pytest.param(RunStatus.COMPLETED.value, "This Get finished: 1 of the 2 works you chose has an image.", id="finished"),
    ],
)
def test_the_run_screen_words_a_get_as_one(ui, status, said):
    works = [
        a_candidate(work_id="w1", provenance=WorkProvenance.CHOSEN.value, wikidata_qid=HARVESTERS),
        a_candidate(
            work_id="w2",
            provenance=WorkProvenance.CHOSEN.value,
            wikidata_qid=CORN,
            resolution_status=ResolutionStatus.UNRESOLVED.value,
            unresolved_reason="not_held",
        ),
    ]
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(a_run(run_id=GET_ID, kind="get", intent=None, status=status), works))
    ui.serve(f"**/api/runs/{GET_ID}/spend*", {"scope": "run", "cost_usd": "0", "run_id": GET_ID, "year": None, "month": None})
    ui.open(f"#get/{GET_ID}")
    ui.page.wait_for_selector("#view h1:text-is('Get')")

    text = " ".join(ui.text().split())
    assert said in text
    assert "2 works you chose." in text
    assert "asked for" not in text


def test_a_chosen_work_in_review_links_the_item_it_was_got_by(ui):
    card = a_card(work=a_candidate(provenance=WorkProvenance.CHOSEN.value, wikidata_qid=HUNTERS))
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", a_candidate_page([card], run=a_run(run_id=GET_ID, kind="get", intent=None)))
    ui.open(f"#review/{GET_ID}")
    ui.page.wait_for_selector("li.card")

    assert ui.page.locator("#view h1").first.inner_text() == "Get"
    assert ui.page.locator("#view a:text-is('← Get')").count() == 1
    ui.page.click(f"li.card .card-meta a:text-is('{HUNTERS}')")

    ui.page.wait_for_function(f"() => window.location.hash.startsWith('#work/{HUNTERS}')")


# -- where a run's works go, in Queue, on the run's page and in Review ---------------

GONE = "a-theme-id-nothing-holds"


@pytest.fixture
def destinations(winter, all_works):
    """Each case: the run's `destination_theme_id`, the Queue cell, and the sentence."""
    return {
        "named": (winter.id, "Winter", "Works you accept from this Get join Winter."),
        "default": (None, "All works", "Works you accept from this Get join All works."),
        "deleted": (
            GONE,
            "a theme that has been deleted",
            "Works you accept from this Get were to join a theme that has been deleted, so they join no theme.",
        ),
    }


CASES = ["named", "default", "deleted"]


def a_get_into(theme_id, **overrides):
    return a_run(run_id=GET_ID, kind="get", intent=None, destination_theme_id=theme_id, **overrides)


@pytest.mark.parametrize("case", CASES)
def test_queue_says_where_a_gets_works_go(ui, destinations, case):
    theme_id, cell, _ = destinations[case]
    ui.serve(
        "**/api/runs",
        {"runs": [a_get_into(theme_id).model_dump(mode="json")], "count": 1, "total": 1, "truncated": False},
    )
    ui.open("#queue")
    ui.page.wait_for_selector("#view table")

    headings = ui.page.locator("#view thead th").all_text_contents()
    cells = ui.page.locator("#view tbody tr").first.locator("td").all_text_contents()
    assert cells[headings.index("Into")].strip() == cell


@pytest.mark.parametrize("case", CASES)
def test_the_run_page_says_where_a_gets_works_go(ui, destinations, case):
    theme_id, _, sentence = destinations[case]
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(a_get_into(theme_id)))
    ui.open(f"#get/{GET_ID}")
    ui.page.wait_for_selector("#view h1:text-is('Get')")

    assert ui.page.locator("#view .run-destination").inner_text() == sentence


@pytest.mark.parametrize("case", CASES)
def test_review_names_the_destination(ui, destinations, case):
    theme_id, _, sentence = destinations[case]
    card = a_card(work=a_candidate(provenance=WorkProvenance.CHOSEN.value, wikidata_qid=HUNTERS))
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", a_candidate_page([card], run=a_get_into(theme_id)))
    ui.open(f"#review/{GET_ID}")
    ui.page.wait_for_selector("li.card")

    assert ui.page.locator("#view .run-destination").inner_text() == sentence


def test_a_run_page_that_could_not_name_the_theme_tries_again_at_the_next_poll(ui):
    """The run is unchanged, so a page recorded as painted would keep the failure on screen."""
    listing = {
        "themes": [
            {
                "theme": {
                    "theme_id": "t-all",
                    "name": "All works",
                    "description": None,
                    "rotation_interval_seconds": None,
                    "shuffle": None,
                    "created_at": "2026-10-02T10:00:00+00:00",
                    "is_default": True,
                },
                "hanging_on": [],
            }
        ]
    }
    ui.serve("**/api/themes", [(500, {"error": "The theme listing failed."}), listing])
    running = a_get_into(None, status=RunStatus.RESOLVING_IMAGES.value)
    ui.serve(f"**/api/runs/{GET_ID}", a_run_view(running))
    ui.open(f"#get/{GET_ID}")
    sentence = ui.page.locator("#view .run-destination")
    sentence.wait_for()
    assert sentence.inner_text() == "Which theme works you accept from this Get join could not be looked up just now."

    ui.page.wait_for_selector("#view .run-destination:text-is('Works you accept from this Get join All works.')")


def test_a_re_search_defers_to_the_run_it_re_searches(ui, winter, all_works):
    """A re-search's works are its parent's candidates, so they go where the parent sends them.

    Its own destination is always null, and reading that null as the default
    would tell a curator re-searching a Get into Winter that its works join All works.
    """
    re_search = a_run(run_id="r-again", kind="resolve", intent=None, parent_run_id=GET_ID, destination_theme_id=None)
    ui.serve("**/api/runs", {"runs": [re_search.model_dump(mode="json")], "count": 1, "total": 1, "truncated": False})
    ui.serve("**/api/runs/r-again", a_run_view(re_search))
    ui.open("#queue")
    ui.page.wait_for_selector("#view table")
    headings = ui.page.locator("#view thead th").all_text_contents()
    cells = ui.page.locator("#view tbody tr").first.locator("td").all_text_contents()
    assert cells[headings.index("Into")].strip() == "the same theme as the earlier Get"

    ui.open("#get/r-again")
    ui.page.wait_for_selector("#view .run-destination")
    assert ui.page.locator("#view .run-destination").inner_text() == (
        "Works you accept from this Get join the theme the earlier Get they came from sends its works to."
    )


def test_review_with_no_default_says_accepted_works_join_no_theme(ui, winter):
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", a_candidate_page([a_card()], run=a_get_into(None)))
    ui.open(f"#review/{GET_ID}")
    ui.page.wait_for_selector("li.card")

    assert ui.page.locator("#view .run-destination").inner_text() == (
        "Works you accept from this Get join no theme, because no theme is the default."
    )


def test_review_still_opens_when_the_themes_cannot_be_read(ui):
    ui.serve("**/api/themes", (500, {"error": "The theme listing failed."}))
    ui.serve_image("**/api/candidate-images/*/preview")
    ui.serve(f"**/api/runs/{GET_ID}/candidates*", a_candidate_page([a_card()], run=a_get_into(GONE)))
    ui.open(f"#review/{GET_ID}")
    ui.page.wait_for_selector("li.card")

    assert ui.page.locator("#view .run-destination").inner_text() == (
        "Which theme works you accept from this Get join could not be looked up just now."
    )


def test_an_artist_with_no_description_shows_nothing_in_its_place(ui):
    """An absent description was passed to the page as `null` and printed as the word."""
    ui.open(f"#artist/{BRUEGEL}")
    ui.page.locator("section table").wait_for()

    assert "null" not in ui.text()
