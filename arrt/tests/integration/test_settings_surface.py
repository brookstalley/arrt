"""The household's settings through the real server: the route, the MCP tool, and the label built after a change."""

import dataclasses
import json
from decimal import Decimal

import httpx
import pytest

from arrt.library.discovery.openrouter import KeyStatus
from arrt.library.services.settings import SETTINGS


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    """One MCP tool call over the mounted surface, as an agent would make it."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool, arguments)
    return json.loads(result.content[0].text), bool(result.isError)


def listed(server_url: str) -> dict[str, dict]:
    response = httpx.get(f"{server_url}/api/settings", timeout=30)
    assert response.status_code == 200
    return {setting["key"]: setting for setting in response.json()["settings"]}


def test_every_setting_is_listed_in_order_with_its_default_and_source(server_url):
    response = httpx.get(f"{server_url}/api/settings", timeout=30).json()

    assert [setting["key"] for setting in response["settings"]] == [setting.key for setting in SETTINGS]
    units = listed(server_url)["label_units"]
    assert units["value"] == units["default"] == "imperial"
    assert (units["source"], units["locked"], units["environment_variable"]) == ("default", False, "LABEL_UNITS")
    assert units["choices"] == ["imperial", "metric"]


def test_a_change_from_the_browser_reaches_the_next_label_with_no_restart(server_url, services, seeded_service):
    """Through the facade Programming reads labels from, at metric, which is not the default."""
    work = seeded_service.add_artwork(title="Nighthawks", dimensions="76.5 × 97.3 cm (30 1/8 × 38 1/4 in.)")
    assert services.library.labels([work.id])[work.id]["dimensions"] == "30 × 38 in"

    response = httpx.post(f"{server_url}/api/settings/label_units", json={"value": "metric"}, timeout=30)

    assert response.status_code == 200
    assert (response.json()["value"], response.json()["source"], response.json()["updated_by"]) == ("metric", "stored", "web_ui")
    assert services.library.labels([work.id])[work.id]["dimensions"] == "77 × 97 cm"


def test_a_value_the_setting_cannot_take_is_refused_in_the_services_words(server_url):
    response = httpx.post(f"{server_url}/api/settings/label_units", json={"value": "cubits"}, timeout=30)

    assert response.status_code == 400
    assert "LABEL_UNITS must be imperial or metric, got 'cubits'" in response.json()["error"]
    assert listed(server_url)["label_units"]["value"] == "imperial"


def test_an_unknown_setting_is_refused_naming_the_ones_there_are(server_url):
    response = httpx.post(f"{server_url}/api/settings/units", json={"value": "metric"}, timeout=30)

    assert response.status_code == 400
    assert "The settings are label_units" in response.json()["error"]


async def test_an_agent_changes_a_setting_over_mcp_as_the_browser_does(server_url, services, seeded_service):
    work = seeded_service.add_artwork(title="Nighthawks", dimensions="76.5 × 97.3 cm (30 1/8 × 38 1/4 in.)")

    payload, errored = await call(server_url, "art_settings", action="set", key="label_units", value="metric")

    assert errored is False
    assert (payload["setting"]["value"], payload["setting"]["updated_by"]) == ("metric", "mcp_client")
    assert services.library.labels([work.id])[work.id]["dimensions"] == "77 × 97 cm"
    assert listed(server_url)["label_units"]["updated_by"] == "mcp_client"


async def test_the_tool_lists_settings_in_the_routes_own_fields(server_url):
    payload, errored = await call(server_url, "art_settings", action="list")

    assert errored is False
    assert payload["settings"] == list(listed(server_url).values())


async def test_the_tool_refuses_a_value_the_setting_cannot_take(server_url):
    payload, errored = await call(server_url, "art_settings", action="set", key="label_units", value="cubits")

    assert errored is True
    assert "got 'cubits'" in json.dumps(payload)


def test_unattended_work_reads_as_off_until_chosen_and_the_route_says_why(server_url):
    standing = httpx.get(f"{server_url}/api/unattended", timeout=30).json()

    assert standing == {
        "switched_on": False,
        "allowance_usd": "0.00",
        "spent_usd": "0.00",
        "remaining_usd": "0.00",
        "may_start": False,
        "refusal": "off",
        "sentence": "Unattended work is off, so nothing runs with nobody watching.",
    }


async def test_an_agent_reads_where_unattended_work_stands_in_the_routes_own_fields(server_url):
    async with httpx.AsyncClient(base_url=server_url, timeout=30) as http:
        await http.post("/api/settings/unattended_work", json={"value": "on"})
        await http.post("/api/settings/unattended_allowance_usd", json={"value": "3"})

        payload, errored = await call(server_url, "art_settings", action="unattended")

        assert errored is False
        route = (await http.get("/api/unattended")).json()
    assert {key: payload[key] for key in route} == route
    assert (route["switched_on"], route["allowance_usd"]) == (True, "3.00")


def test_the_model_is_reset_to_the_discovery_model_by_an_empty_value(server_url):
    httpx.post(f"{server_url}/api/settings/unattended_model", json={"value": "anthropic/claude-haiku-5.5"}, timeout=30)

    response = httpx.post(f"{server_url}/api/settings/unattended_model", json={"value": ""}, timeout=30)

    assert response.status_code == 200
    assert response.json()["value"] == ""


def standing(server_url: str) -> dict:
    return httpx.get(f"{server_url}/api/unattended", timeout=30).json()


# -- the deployment's facts reach the allowance through the real wiring -----------


class TestUnderAMonthlyBudget:
    """`MONTHLY_BUDGET_USD` reaches the allowance's bound through the container, not a hand-built `Limits`."""

    @pytest.fixture
    def settings(self, settings):
        return dataclasses.replace(settings, monthly_budget_usd=Decimal(20))

    def test_an_allowance_above_the_budget_is_refused_by_the_running_server(self, server_url):
        response = httpx.post(f"{server_url}/api/settings/unattended_allowance_usd", json={"value": "20.01"}, timeout=30)

        assert response.status_code == 400
        assert "cannot be more than it" in response.json()["error"]
        assert (
            httpx.post(f"{server_url}/api/settings/unattended_allowance_usd", json={"value": "20"}, timeout=30).status_code == 200
        )

    async def test_an_allowance_stored_above_it_is_set_aside_on_the_route_and_the_tool_alike(self, server_url, discovery_store):
        """An allowance chosen under a higher budget, read after `MONTHLY_BUDGET_USD` was lowered to 20 (#417)."""
        from datetime import UTC, datetime

        from arrt.persistence.discovery_records import InitiatedBy, StoredSetting

        discovery_store.put_setting(StoredSetting("unattended_allowance_usd", "25.00", datetime.now(UTC), InitiatedBy.WEB_UI))

        allowance = listed(server_url)["unattended_allowance_usd"]
        assert (allowance["source"], allowance["value"]) == ("set_aside", "0.00")
        assert "$20" in allowance["set_aside_reason"]
        assert "$25.00" in allowance["set_aside_reason"]
        assert listed(server_url)["label_units"]["set_aside_reason"] is None

        body, is_error = await call(server_url, "art_settings", action="list")
        assert not is_error
        [over_mcp] = [setting for setting in body["settings"] if setting["key"] == "unattended_allowance_usd"]
        assert over_mcp == allowance
        assert standing(server_url)["allowance_usd"] == "0.00"


def switched_on_with(server_url: str, allowance: str) -> dict:
    httpx.post(f"{server_url}/api/settings/unattended_work", json={"value": "on"}, timeout=30)
    httpx.post(f"{server_url}/api/settings/unattended_allowance_usd", json={"value": allowance}, timeout=30)
    return httpx.get(f"{server_url}/api/unattended", timeout=30).json()


def test_with_no_model_key_unattended_work_is_refused_for_the_key(server_url):
    """The suite's deployment has no key (`key_status` is None), which the container reads as having none."""
    standing = switched_on_with(server_url, "5")

    assert (standing["refusal"], standing["may_start"]) == ("no_key", False)


class TestWithAModelKey:
    @pytest.fixture
    def key_status(self):
        return lambda: KeyStatus(limit_usd=Decimal(20), usage_usd=Decimal(1), remaining_usd=Decimal(19))

    def test_with_a_key_and_an_allowance_unattended_work_may_start(self, server_url):
        standing = switched_on_with(server_url, "5")

        assert (standing["refusal"], standing["may_start"]) == (None, True)
