"""A Get's destination: where its accepted works go, driven over real HTTP and MCP.

The owner's ruling of 2026-10-02 (`build-plan-topics-and-destinations.md`): a Get
names the theme its accepted works join, *All works* (the default) when it names
none. The Library records the theme on the run as an opaque id; Programming asks
the facade for it when a work is accepted and again at every start, so a lost
announcement and a delivered one land the work in the same theme.

Driven through the surfaces a curator and an agent use, because the claim is
about what an acceptance does: a service-level test would pass with the
subscription unwired or the binding dropping `theme_id` on the floor.
"""

import json
import logging

import httpx
import pytest
from fakes import FakeFinder, FakeRegistry, a_roster, an_image
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.library.registry import CommonsFile, ItemId, RegistryCreator, RegistryText, RegistryWork
from arrt.persistence.errors import StorageError
from arrt.services.container import Services

DALI = RegistryCreator(qid=ItemId("Q5577"), name=RegistryText("Salvador Dalí"))
ELEPHANTS = ItemId("Q1003")
SWANS = ItemId("Q1004")


def a_registry_work(qid: str, title: str) -> RegistryWork:
    return RegistryWork(
        qid=ItemId(qid),
        title=RegistryText(title),
        sitelinks=10,
        image=CommonsFile(f"https://commons.wikimedia.org/wiki/Special:FilePath/{qid}.jpg"),
        creators=(DALI,),
    )


@pytest.fixture
def registry() -> FakeRegistry:
    return FakeRegistry(
        works={
            ELEPHANTS: a_registry_work(ELEPHANTS, "The Elephants"),
            SWANS: a_registry_work(SWANS, "Swans Reflecting Elephants"),
        }
    )


@pytest.fixture
def museum() -> FakeFinder:
    return FakeFinder(
        holdings={
            "The Elephants": (an_image("The Elephants"),),
            "Swans Reflecting Elephants": (an_image("Swans Reflecting Elephants"),),
        }
    )


@pytest.fixture
def services(store, discovery_store, wall_settings, thumbnail_settings, settings, engine, registry, museum):
    """The plane with an image source and a registry, so a Get can find and accept works."""
    bound = Services.bind(
        catalogue=store,
        discovery=discovery_store,
        display_settings=wall_settings,
        thumbnails=thumbnail_settings,
        artwork_box=settings.tv_artwork_box,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        sources=a_roster(museum),
        registry=registry,
    )
    # Phase 2 on the request's own thread, so a Get has found its image by the
    # time the response arrives and each test reads as the curator's steps.
    bound.runner._spawn = lambda work: work()
    return bound


@pytest.fixture
def themes(services, seeded_service):
    """*All works*, the default, holding one work; *Winter*, a destination; and *Spare*, which gains nothing.

    The default's existing member is what makes "not in the default" a claim
    about this acceptance rather than about an empty theme.
    """
    display = services.display
    all_works = display.add_theme(name="All works")
    winter = display.add_theme(name="Winter")
    spare = display.add_theme(name="Spare")
    first = next(entry.artwork for entry in seeded_service.list_artworks().entries if entry.artwork.title == "Nighthawks")
    display.add_to_theme(theme_id=all_works.id, artwork_id=first.id)
    display.make_default(all_works.id)
    return all_works, winter, spare


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool, arguments)
    return json.loads("".join(block.text for block in result.content if block.type == "text")), bool(result.isError)


def members(services, theme_id: str) -> list[str]:
    return list(services.display.theme_work_ids(theme_id))


def the_only_work(http, run_id: str) -> str:
    (card,) = http.get(f"/api/runs/{run_id}/candidates").raise_for_status().json()["works"]
    return card["work"]["work_id"]


def get(http, qid: str, theme_id: str | None = None) -> dict:
    body = {"qids": [qid]} if theme_id is None else {"qids": [qid], "theme_id": theme_id}
    return http.post("/api/gets", json=body).raise_for_status().json()["run"]


def accept(http, work_id: str) -> str:
    verdict = http.post(f"/api/candidates/{work_id}/verdict", json={"verdict": "accepted"}).raise_for_status().json()
    return verdict["artwork_id"]


def get_and_accept(http, qid: str, theme_id: str | None = None) -> str:
    return accept(http, the_only_work(http, get(http, qid, theme_id)["run_id"]))


class TestAnAcceptedWorkGoesWhereItsGetSaid:
    def test_a_get_with_a_theme_puts_it_in_that_theme_and_not_the_default(self, http, services, themes):
        all_works, winter, spare = themes
        before = members(services, all_works.id)

        run = get(http, ELEPHANTS, winter.id)
        artwork_id = accept(http, the_only_work(http, run["run_id"]))

        assert run["destination_theme_id"] == winter.id
        assert members(services, winter.id) == [artwork_id]
        assert members(services, all_works.id) == before
        assert members(services, spare.id) == []

    def test_a_get_without_a_theme_puts_it_in_the_default(self, http, services, themes):
        all_works, winter, _spare = themes
        before = members(services, all_works.id)

        run = get(http, ELEPHANTS)
        artwork_id = accept(http, the_only_work(http, run["run_id"]))

        assert run["destination_theme_id"] is None
        assert members(services, all_works.id) == [*before, artwork_id]
        assert members(services, winter.id) == []

    async def test_an_agent_can_send_a_get_to_a_theme(self, server_url, http, services, themes):
        all_works, winter, _spare = themes
        before = members(services, all_works.id)

        started, errored = await call(server_url, "art_discovery", action="get", qids=[ELEPHANTS], theme_id=winter.id)
        assert errored is False, started
        work_id = the_only_work(http, started["run_id"])
        accepted, errored = await call(server_url, "art_review", action="set_verdict", work_id=work_id, verdict="accepted")

        assert errored is False, accepted
        assert started["destination_theme_id"] == winter.id
        assert members(services, winter.id) == [accepted["artwork_id"]]
        assert members(services, all_works.id) == before

    def test_two_gets_into_two_places_each_land_where_they_were_sent(self, http, services, themes):
        """Keyed per work: a join that read one run's destination for every work would put both in one place."""
        all_works, winter, _spare = themes
        before = members(services, all_works.id)

        to_winter = get_and_accept(http, ELEPHANTS, winter.id)
        to_default = get_and_accept(http, SWANS)

        assert members(services, winter.id) == [to_winter]
        assert members(services, all_works.id) == [*before, to_default]


class TestALostAnnouncementLandsWhereADeliveredOneWould:
    def test_the_next_start_puts_it_in_its_theme_and_not_the_default(self, http, services, themes, monkeypatch):
        """A crash between the Library's commit and the handler, staged as a handler that raises."""
        all_works, winter, _spare = themes
        before = members(services, all_works.id)

        def fails(work_ids):
            raise StorageError("the disk went away")

        monkeypatch.setattr(services.display, "offer_destinations", fails)
        artwork_id = get_and_accept(http, ELEPHANTS, winter.id)
        monkeypatch.undo()
        assert members(services, winter.id) == [], "the staged crash did not stop the join"

        services.reconcile()

        assert members(services, winter.id) == [artwork_id]
        assert members(services, all_works.id) == before


class TestADeletedDestination:
    def test_the_work_joins_no_theme_and_the_next_start_leaves_it_out_of_the_default(self, http, services, themes, store, caplog):
        all_works, _winter, spare = themes
        before = members(services, all_works.id)
        run = get(http, ELEPHANTS, spare.id)
        http.delete(f"/api/themes/{spare.id}").raise_for_status()

        with caplog.at_level(logging.WARNING, logger="arrt"):
            artwork_id = accept(http, the_only_work(http, run["run_id"]))
        services.reconcile()

        assert members(services, all_works.id) == before
        assert all(artwork_id not in members(services, theme.id) for theme in services.display.list_themes())
        assert artwork_id in store.offered_work_ids(), "recorded as offered, so no start sweeps it anywhere"
        assert any(artwork_id in record.getMessage() and spare.id in record.getMessage() for record in caplog.records)

    def test_the_run_still_names_the_theme_it_was_sent_to(self, http, themes):
        """The record of where the curator asked the works to go outlives the theme."""
        _all_works, _winter, spare = themes
        run = get(http, ELEPHANTS, spare.id)
        http.delete(f"/api/themes/{spare.id}").raise_for_status()

        again = http.get(f"/api/runs/{run['run_id']}").raise_for_status().json()["run"]

        assert again["destination_theme_id"] == spare.id


class TestAnUnknownThemeRefusesTheGet:
    def test_over_http(self, http, services, themes):
        before = len(services.discovery.list_runs())

        response = http.post("/api/gets", json={"qids": [ELEPHANTS], "theme_id": "no-such-theme"})

        assert 400 <= response.status_code < 500, response.text
        assert "No theme with id 'no-such-theme'" in response.text
        assert len(services.discovery.list_runs()) == before

    async def test_over_mcp(self, server_url, services, themes):
        before = len(services.discovery.list_runs())

        refused, errored = await call(server_url, "art_discovery", action="get", qids=[ELEPHANTS], theme_id="no-such-theme")

        assert errored is True, refused
        assert "No theme with id 'no-such-theme'" in json.dumps(refused)
        assert len(services.discovery.list_runs()) == before


class TestARestoredWorkIsOfferedNothing:
    def test_a_work_taken_out_of_its_destination_stays_out_after_a_restore(self, http, services, themes):
        all_works, winter, _spare = themes
        before = members(services, all_works.id)
        artwork_id = get_and_accept(http, ELEPHANTS, winter.id)
        http.delete(f"/api/themes/{winter.id}/works/{artwork_id}").raise_for_status()

        http.post(f"/api/works/{artwork_id}/archive").raise_for_status()
        http.post(f"/api/works/{artwork_id}/restore").raise_for_status()
        services.reconcile()

        assert members(services, winter.id) == []
        assert members(services, all_works.id) == before
