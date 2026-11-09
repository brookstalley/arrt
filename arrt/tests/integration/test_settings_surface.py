"""The household's settings through the real server: the route, the MCP tool, and the label built after a change."""

import json

import httpx

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
