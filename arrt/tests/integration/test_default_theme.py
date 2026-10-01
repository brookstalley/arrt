"""The default theme: what the curator accepts lands somewhere it can be hung.

The owner's ruling 8 (`ia-proposal.md` § Rulings): "There should be a default
'all works' theme." Acceptance is the Library's and themes are Programming's, so
the join is a Programming subscriber to the Library's `work.accepted` event,
caught up at startup for an announcement a crash lost. These drive it through
the surfaces a curator and an agent accept on, because the claim is about what an
acceptance does, and a service-level test would pass with the subscription never
wired.

**Each work is offered once** (`data-model.md` § DefaultThemeOffer). The same
event announces a restored work, and startup reconciliation offers every work
with no offer recorded, so the traps are a restore and a restart putting back a
work the curator took out.
"""

import json

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from arrt.persistence.errors import StorageError
from arrt.services.errors import ServiceError


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
    return json.loads("".join(block.text for block in result.content if block.type == "text")), bool(result.isError)


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def themes(services, seeded_service):
    """*All works*, the default, already holding one work; and *Winter*, which must gain nothing.

    The existing member is what makes "at the end of its order" checkable: a
    join that inserted at the front would pass against an empty theme.
    """
    display = services.display
    all_works = display.add_theme(name="All works")
    winter = display.add_theme(name="Winter")
    first = next(entry.artwork for entry in seeded_service.list_artworks().entries if entry.artwork.title == "Nighthawks")
    display.add_to_theme(theme_id=all_works.id, artwork_id=first.id)
    display.make_default(all_works.id)
    return all_works, winter


@pytest.fixture
def reviewable(propose, add_image):
    def _reviewable(title: str):
        work = propose(title, dedup_key=title.lower(), proposed_artist="Salvador Dalí")
        add_image(work, url=f"https://artic.edu/{title.lower().replace(' ', '-')}", confidence=0.9)
        return work

    return _reviewable


def members(services, theme_id: str) -> list[str]:
    return list(services.display.theme_work_ids(theme_id))


class TestAnAcceptanceJoinsTheDefault:
    def test_through_the_verdict_route(self, http, services, themes, reviewable):
        all_works, winter = themes
        before = members(services, all_works.id)
        work = reviewable("The Elephants")

        verdict = http.post(f"/api/candidates/{work.id}/verdict", json={"verdict": "accepted"}).raise_for_status().json()

        assert members(services, all_works.id) == [*before, verdict["artwork_id"]]
        assert members(services, winter.id) == []

    async def test_through_the_verdict_tool(self, server_url, services, themes, reviewable):
        all_works, winter = themes
        before = members(services, all_works.id)
        work = reviewable("The Elephants")

        accepted, errored = await call(server_url, "art_review", action="set_verdict", work_id=work.id, verdict="accepted")

        assert errored is False
        assert members(services, all_works.id) == [*before, accepted["artwork_id"]]
        assert members(services, winter.id) == []

    def test_a_rejection_joins_nothing(self, http, services, themes, reviewable):
        all_works, _winter = themes
        before = members(services, all_works.id)
        work = reviewable("The Elephants")

        http.post(f"/api/candidates/{work.id}/verdict", json={"verdict": "rejected"}).raise_for_status()

        assert members(services, all_works.id) == before

    def test_with_no_default_an_acceptance_still_succeeds_and_joins_nothing(self, http, services, reviewable):
        winter = services.display.add_theme(name="Winter")
        work = reviewable("The Elephants")

        verdict = http.post(f"/api/candidates/{work.id}/verdict", json={"verdict": "accepted"}).raise_for_status().json()

        assert verdict["artwork_id"] is not None
        assert members(services, winter.id) == []


class TestTheCuratorsRemovalStands:
    def test_a_restart_does_not_put_it_back(self, http, services, themes, reviewable):
        all_works, _winter = themes
        work = reviewable("The Elephants")
        artwork_id = http.post(f"/api/candidates/{work.id}/verdict", json={"verdict": "accepted"}).json()["artwork_id"]
        http.delete(f"/api/themes/{all_works.id}/works/{artwork_id}").raise_for_status()

        services.reconcile()

        assert artwork_id not in members(services, all_works.id)

    def test_a_restore_does_not_put_it_back(self, http, services, themes, reviewable):
        all_works, _winter = themes
        work = reviewable("The Elephants")
        artwork_id = http.post(f"/api/candidates/{work.id}/verdict", json={"verdict": "accepted"}).json()["artwork_id"]
        http.delete(f"/api/themes/{all_works.id}/works/{artwork_id}").raise_for_status()

        http.post(f"/api/works/{artwork_id}/archive").raise_for_status()
        http.post(f"/api/works/{artwork_id}/restore").raise_for_status()

        assert artwork_id not in members(services, all_works.id)

    def test_a_restored_work_still_in_the_default_stays_once(self, http, services, themes, reviewable):
        """Archiving leaves memberships alone, so the restore must not add a second row."""
        all_works, _winter = themes
        work = reviewable("The Elephants")
        artwork_id = http.post(f"/api/candidates/{work.id}/verdict", json={"verdict": "accepted"}).json()["artwork_id"]

        http.post(f"/api/works/{artwork_id}/archive").raise_for_status()
        http.post(f"/api/works/{artwork_id}/restore").raise_for_status()

        assert members(services, all_works.id).count(artwork_id) == 1


class TestALostAnnouncementIsCaughtUpAtStart:
    def test_a_work_the_subscriber_never_heard_of_joins_at_the_next_start(self, services, themes, seeded_service, monkeypatch):
        """A crash between the Library's commit and the handler, staged as a handler that raises."""
        all_works, _winter = themes

        def fails(event):
            raise StorageError("the disk went away")

        monkeypatch.setattr(services.display, "offer_to_default", fails)
        added = seeded_service.add_artwork(title="Blue Poles")
        monkeypatch.undo()
        assert added.id not in members(services, all_works.id), "the staged crash did not stop the join"

        services.reconcile()

        assert members(services, all_works.id)[-1] == added.id

    def test_a_work_the_curator_already_placed_is_left_where_they_put_it(self, services, themes, seeded_service, monkeypatch):
        """The announcement was lost, and the curator added the work by hand before the restart."""
        all_works, _winter = themes
        monkeypatch.setattr(services.display, "offer_to_default", lambda work_ids: [])
        added = seeded_service.add_artwork(title="Blue Poles")
        monkeypatch.undo()
        services.display.add_to_theme(theme_id=all_works.id, artwork_id=added.id, position=0)

        services.reconcile()

        assert members(services, all_works.id)[0] == added.id
        assert members(services, all_works.id).count(added.id) == 1

    def test_a_work_offered_while_there_was_no_default_is_not_swept_in_later(self, services, seeded_service):
        """Marking a default is not a request to fill it with everything accepted before."""
        early = seeded_service.add_artwork(title="Blue Poles")
        later_default = services.display.add_theme(name="Everything")

        services.display.make_default(later_default.id)
        services.reconcile()

        assert early.id not in members(services, later_default.id)


class TestTheMark:
    def test_there_is_at_most_one_and_making_another_moves_it(self, http, services, themes):
        all_works, winter = themes

        listing = http.post(f"/api/themes/{winter.id}/default").raise_for_status().json()

        marked = {placement["theme"]["name"]: placement["theme"]["is_default"] for placement in listing["themes"]}
        assert marked == {"All works": False, "Winter": True}

    async def test_an_agent_can_make_a_theme_the_default(self, server_url, services, themes):
        _all_works, winter = themes

        made, errored = await call(server_url, "art_theme", action="make_default", theme_id=winter.id)

        assert errored is False
        assert made["theme"]["is_default"] is True
        listed, _ = await call(server_url, "art_theme", action="list")
        assert [entry["name"] for entry in listed["themes"] if entry["is_default"]] == ["Winter"]

    def test_deleting_the_default_is_refused_with_the_reason(self, http, themes):
        all_works, _winter = themes

        refused = http.delete(f"/api/themes/{all_works.id}")

        assert refused.status_code == 400
        assert "default" in refused.json()["error"]
        assert "Make another theme the default" in refused.json()["error"]

    def test_deleting_another_theme_is_not_refused_for_it(self, http, themes):
        _all_works, winter = themes

        http.delete(f"/api/themes/{winter.id}").raise_for_status()

    def test_renaming_the_default_keeps_it_the_default(self, http, services, themes):
        all_works, _winter = themes

        renamed = http.post(f"/api/themes/{all_works.id}", json={"name": "Everything I hold"}).raise_for_status().json()

        assert renamed["is_default"] is True
        assert services.display.default_theme().id == all_works.id

    def test_an_unknown_theme_cannot_be_made_the_default(self, services):
        with pytest.raises(ServiceError, match="No theme"):
            services.display.make_default("not-a-theme")
