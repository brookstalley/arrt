"""Get, driven over real HTTP and a real MCP client, on the threaded path.

A Get is a selection of Wikidata items becoming one run over the image sources.
What only a booted server can show is that the run advances behind the handle a
client holds, that each surface reports what it skipped, and that accepting a
work it found records the item on the new artwork, so the library holds it
wherever the registry shows it.
"""

import json
from decimal import Decimal

import httpx
import pytest
from fakes import FakeImageSearch, FakeRegistry, a_collection_holding, an_image

from arrt.library.discovery.images import FoundImage, ImageQuery
from arrt.library.registry import CommonsFile, ItemId, RegistryCreator, RegistryText, RegistryWork
from arrt.library.services.discovery import ChosenWork
from arrt.library.services.get import MAX_ITEMS_PER_GET
from arrt.library.services.previews import PreviewSettings
from arrt.persistence.discovery_records import InitiatedBy, ResolutionStatus, RunKind, RunStatus
from arrt.persistence.records import IdentitySetBy
from arrt.services.container import Services
from arrt.services.errors import ServiceError

DALI = RegistryCreator(qid=ItemId("Q5577"), name=RegistryText("Salvador Dalí"))

#: Items as the fake registry knows them. The QIDs are labels for this module's
#: fixtures; only the first two have anything any source can find.
ELEPHANTS = ItemId("Q1003")
SWANS = ItemId("Q1004")
NOWHERE = ItemId("Q1005")
UNKNOWN = ItemId("Q1999")


def a_registry_work(qid: str, title: str) -> RegistryWork:
    return RegistryWork(
        qid=ItemId(qid),
        title=RegistryText(title),
        sitelinks=10,
        image=CommonsFile(f"https://commons.wikimedia.org/wiki/Special:FilePath/{qid}.jpg"),
        creators=(DALI,),
    )


class ItemSource:
    """An image source that answers only by Wikidata item, as Commons does."""

    def __init__(self, holdings: dict[str, FoundImage]) -> None:
        self.holdings = holdings
        self.asked: list[str | None] = []

    @property
    def provider(self) -> str:
        return "commons"

    def find_images(self, query: ImageQuery):
        self.asked.append(query.qid)
        found = self.holdings.get(query.qid or "")
        return () if found is None else (found,)

    def fetch_preview(self, url: str) -> bytes | None:
        return b"\xff\xd8\xff\xe0 jpeg"

    def tile_url(self, url: str) -> str:
        return url


def commons_image(title: str, *, width: int = 3840, height: int = 4640) -> FoundImage:
    return an_image(title, width=width, height=height, provider="commons", url=f"https://commons.example/{title}/{width}")


@pytest.fixture
def registry() -> FakeRegistry:
    return FakeRegistry(
        works={
            ELEPHANTS: a_registry_work(ELEPHANTS, "The Elephants"),
            SWANS: a_registry_work(SWANS, "Swans Reflecting Elephants"),
            NOWHERE: a_registry_work(NOWHERE, "A Painting Nobody Has"),
        }
    )


@pytest.fixture
def commons() -> ItemSource:
    return ItemSource({ELEPHANTS: commons_image("The Elephants"), SWANS: commons_image("Swans Reflecting Elephants")})


@pytest.fixture
def museum() -> FakeImageSearch:
    return FakeImageSearch()


@pytest.fixture
def services(store, discovery_store, wall_settings, thumbnail_settings, settings, engine, registry, commons, museum):
    """The plane with Commons and the Art Institute wired, and a registry."""
    return Services.bind(
        catalogue=store,
        discovery=discovery_store,
        display_settings=wall_settings,
        thumbnails=thumbnail_settings,
        artwork_box=settings.tv_artwork_box,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        image_sources=[commons, museum],
        previews=PreviewSettings(art_root=settings.art_root, directory=settings.previews_path),
        registry=registry,
        # A collection holding the chosen works' artist, so a Get that left a work
        # unresolved would reach the supplement if nothing stopped it there.
        collection=a_collection_holding(**{"Salvador Dalí": ["Sleep"]}),
    )


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


async def finished(server_url: str, run_id: str) -> dict:
    """Poll the surface's own long-poll until the run stops moving."""
    for _ in range(8):
        payload, _errored = await call(server_url, "art_discovery", action="status", run_id=run_id)
        if RunStatus(payload["status"]).is_terminal:
            return payload
    raise AssertionError(f"run {run_id} never finished: {payload}")


def candidates(server_url: str, run_id: str) -> list[dict]:
    page = httpx.get(f"{server_url}/api/runs/{run_id}/candidates", timeout=10).json()
    return [card["work"] for card in page["works"]]


# -- over HTTP ---------------------------------------------------------------------


async def test_a_get_starts_one_run_with_a_work_per_item_and_spends_nothing(server_url, commons):
    response = httpx.post(f"{server_url}/api/gets", json={"qids": [ELEPHANTS, SWANS]}, timeout=10)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["run"]["kind"], body["skipped"]) == ("get", [])
    payload = await finished(server_url, body["run"]["run_id"])
    assert payload["status"] == "completed"

    works = candidates(server_url, body["run"]["run_id"])
    assert sorted((work["title"], work["provenance"], work["wikidata_qid"]) for work in works) == [
        ("Swans Reflecting Elephants", "chosen", SWANS),
        ("The Elephants", "chosen", ELEPHANTS),
    ]
    assert sorted(commons.asked) == sorted([ELEPHANTS, SWANS]), "each source is asked by the item"
    spend = httpx.get(f"{server_url}/api/runs/{body['run']['run_id']}/spend", timeout=10).json()
    assert Decimal(spend["cost_usd"]) == 0, spend


async def test_items_that_cannot_be_got_are_skipped_and_named(server_url, services, seeded_service):
    held = seeded_service.list_artworks().entries[0].artwork
    services.identity.set_work_identity(held.id, ELEPHANTS)
    services.discovery.start_get_run(
        works=[ChosenWork(qid=SWANS, title="Swans Reflecting Elephants")], initiated_by=InitiatedBy.MCP_CLIENT
    )

    response = httpx.post(f"{server_url}/api/gets", json={"qids": [ELEPHANTS, SWANS, UNKNOWN, NOWHERE]}, timeout=10)

    body = response.json()
    assert body["skipped"] == [
        {"qid": ELEPHANTS, "reason": "held"},
        {"qid": SWANS, "reason": "being_got"},
        {"qid": UNKNOWN, "reason": "not_found"},
    ]
    assert [work["wikidata_qid"] for work in candidates(server_url, body["run"]["run_id"])] == [NOWHERE]


async def test_a_selection_of_only_held_items_starts_nothing(server_url, services, seeded_service):
    held = seeded_service.list_artworks().entries[0].artwork
    services.identity.set_work_identity(held.id, ELEPHANTS)
    before = len(services.discovery.list_runs())

    body = httpx.post(f"{server_url}/api/gets", json={"qids": [ELEPHANTS]}, timeout=10).json()

    assert body == {"run": None, "skipped": [{"qid": ELEPHANTS, "reason": "held"}]}
    assert len(services.discovery.list_runs()) == before


async def test_accepting_a_work_a_get_found_records_its_item_on_the_new_artwork(server_url, services):
    body = httpx.post(f"{server_url}/api/gets", json={"qids": [ELEPHANTS]}, timeout=10).json()
    await finished(server_url, body["run"]["run_id"])
    (work,) = candidates(server_url, body["run"]["run_id"])

    verdict = httpx.post(f"{server_url}/api/candidates/{work['work_id']}/verdict", json={"verdict": "accepted"}, timeout=10)

    assert verdict.status_code == 200, verdict.text
    artwork = services.catalogue.get_artwork(services.discovery.get_candidate_work(work["work_id"]).artwork_id).artwork
    assert (artwork.wikidata_qid, artwork.wikidata_qid_set_by) == (ELEPHANTS, IdentitySetBy.CURATOR)
    again = httpx.post(f"{server_url}/api/gets", json={"qids": [ELEPHANTS]}, timeout=10).json()
    assert again["skipped"] == [{"qid": ELEPHANTS, "reason": "held"}], "the library now holds it"


async def test_a_get_that_finds_nothing_completes_rather_than_failing(server_url):
    """A Get is never supplemented, so an unresolved work in it must not reach the offer path."""
    body = httpx.post(f"{server_url}/api/gets", json={"qids": [NOWHERE]}, timeout=10).json()

    payload = await finished(server_url, body["run"]["run_id"])

    assert payload["status"] == "completed", payload
    (work,) = candidates(server_url, body["run"]["run_id"])
    assert work["resolution_status"] == "unresolved"


# -- over MCP ----------------------------------------------------------------------


async def test_an_agent_can_get_works_and_follow_the_run(server_url, commons):
    started, errored = await call(server_url, "art_discovery", action="get", qids=[ELEPHANTS, UNKNOWN])

    assert errored is False, started
    assert started["skipped"] == [{"qid": UNKNOWN, "reason": "not_found"}]
    payload = await finished(server_url, started["run_id"])
    assert payload["status"] == "completed"
    assert commons.asked == [ELEPHANTS]


async def test_a_finished_get_reports_its_works_as_the_ones_chosen(server_url):
    """Neither proposed nor offered: a Get's status counts and words the works the curator chose."""
    started, _ = await call(server_url, "art_discovery", action="get", qids=[ELEPHANTS, SWANS, NOWHERE])

    payload = await finished(server_url, started["run_id"])

    numbers = payload["works"]
    assert (numbers["chosen"], numbers["proposed"], numbers["offered"], numbers["resolved"]) == (3, 0, 0, 2)
    assert payload["notice"].startswith("This Get finished: 2 of the 3 works you chose have an image."), payload["notice"]
    view = httpx.get(f"{server_url}/api/runs/{started['run_id']}", timeout=10).json()
    assert (view["tally"]["chosen"], view["tally"]["proposed"]) == (3, 0)


async def test_an_agent_told_every_item_was_skipped_gets_no_run(server_url, services, seeded_service):
    held = seeded_service.list_artworks().entries[0].artwork
    services.identity.set_work_identity(held.id, ELEPHANTS)

    started, errored = await call(server_url, "art_discovery", action="get", qids=[ELEPHANTS])

    assert errored is False, started
    assert (started["run_id"], started["skipped"]) == (None, [{"qid": ELEPHANTS, "reason": "held"}])


# -- which image wins --------------------------------------------------------------


@pytest.mark.parametrize(
    ("museum_size", "winner"),
    [
        pytest.param((2000, 2417), "commons", id="a smaller museum scan loses to the Commons image"),
        pytest.param((6949, 8400), "artic", id="a larger museum scan beats the Commons image"),
    ],
)
def test_a_get_selects_the_better_image_whichever_source_found_it(services, museum, museum_size, winner):
    """Through the runner, with the item carried to the sources: resolution decides."""
    museum.holdings = {"The Elephants": (an_image("The Elephants", width=museum_size[0], height=museum_size[1]),)}
    services.runner._spawn = lambda work: work()  # noqa: SLF001 - run phase 2 on this thread

    outcome = services.get.start([ELEPHANTS], initiated_by=InitiatedBy.MCP_CLIENT)

    (work,) = services.discovery.list_candidate_works(outcome.run.id)
    assert work.resolution_status is ResolutionStatus.RESOLVED
    selected = [image for image in services.discovery.list_candidate_images(work.id) if image.is_selected]
    assert [image.provider for image in selected] == [winner]


# -- refusals ------------------------------------------------------------------------


def test_a_get_with_no_registry_is_refused_and_starts_nothing(
    store, discovery_store, wall_settings, thumbnail_settings, settings, engine, commons
):
    bound = Services.bind(
        catalogue=store,
        discovery=discovery_store,
        display_settings=wall_settings,
        thumbnails=thumbnail_settings,
        artwork_box=settings.tv_artwork_box,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        image_sources=[commons],
        previews=PreviewSettings(art_root=settings.art_root, directory=settings.previews_path),
    )

    with pytest.raises(ServiceError, match="WIKIDATA_USER_AGENT"):
        bound.get.start([ELEPHANTS], initiated_by=InitiatedBy.MCP_CLIENT)
    assert bound.discovery.list_runs(kind=RunKind.GET) == []


def test_a_get_with_no_image_source_is_refused_and_starts_nothing(
    store, discovery_store, wall_settings, thumbnail_settings, settings, engine, registry
):
    bound = Services.bind(
        catalogue=store,
        discovery=discovery_store,
        display_settings=wall_settings,
        thumbnails=thumbnail_settings,
        artwork_box=settings.tv_artwork_box,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        registry=registry,
    )

    with pytest.raises(ServiceError, match="no image source"):
        bound.get.start([ELEPHANTS], initiated_by=InitiatedBy.MCP_CLIENT)
    assert bound.discovery.list_runs(kind=RunKind.GET) == []


async def test_an_item_whose_get_has_ended_can_be_got_again(server_url):
    """Only a Get still under way holds its items; one that found nothing frees them."""
    first = httpx.post(f"{server_url}/api/gets", json={"qids": [NOWHERE]}, timeout=10).json()
    await finished(server_url, first["run"]["run_id"])

    again = httpx.post(f"{server_url}/api/gets", json={"qids": [NOWHERE]}, timeout=10).json()

    assert (again["skipped"], again["run"] is not None) == ([], True)


async def test_a_work_whose_item_the_library_came_to_hold_meanwhile_is_still_accepted(
    server_url, services, seeded_service, store
):
    """Works may share an item (shown as *Held ×2*), so acceptance refuses nothing."""
    body = httpx.post(f"{server_url}/api/gets", json={"qids": [ELEPHANTS]}, timeout=10).json()
    await finished(server_url, body["run"]["run_id"])
    (work,) = candidates(server_url, body["run"]["run_id"])
    held = seeded_service.list_artworks().entries[0].artwork
    services.identity.set_work_identity(held.id, ELEPHANTS)

    verdict = httpx.post(f"{server_url}/api/candidates/{work['work_id']}/verdict", json={"verdict": "accepted"}, timeout=10)

    assert verdict.status_code == 200, verdict.text
    assert sorted(store.circulating_ids_by_qid()[ELEPHANTS]) == sorted(
        [held.id, services.discovery.get_candidate_work(work["work_id"]).artwork_id]
    )


@pytest.mark.parametrize(
    "qids",
    [
        pytest.param([], id="no items"),
        pytest.param(["not-an-item"], id="a malformed item"),
        pytest.param([f"Q{n}" for n in range(1, MAX_ITEMS_PER_GET + 2)], id="more items than one Get asks for"),
    ],
)
def test_a_get_that_cannot_be_asked_is_refused_and_starts_nothing(server_url, services, qids):
    before = len(services.discovery.list_runs())

    response = httpx.post(f"{server_url}/api/gets", json={"qids": qids}, timeout=10)

    assert 400 <= response.status_code < 500, response.text
    assert len(services.discovery.list_runs()) == before


def test_a_get_whose_registry_cannot_be_asked_is_refused_and_starts_nothing(server_url, services, registry):
    registry.failing = True
    before = len(services.discovery.list_runs())

    response = httpx.post(f"{server_url}/api/gets", json={"qids": [ELEPHANTS]}, timeout=10)

    assert 400 <= response.status_code < 500 and "Try again" in response.text, response.text
    assert len(services.discovery.list_runs()) == before
