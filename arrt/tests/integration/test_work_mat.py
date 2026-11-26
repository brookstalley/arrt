"""The Work page's mat control, over HTTP (#91).

`GET /api/works/{id}/mat` answers the current mat, the one-press presets, and
what re-deriving would give, recording nothing. `POST` records a preset as the
curator's (`manual`) or the derivation as `derived`, keeps the previous colour,
and answers the same shape, so the control repaints from what was recorded.

Against a real uvicorn server, per the suite's standing rule.
"""

import ast
import inspect

import httpx
import pytest

from arrt.http import api as http_api
from arrt.library.acquisition.mat import MAT_PRESETS, derive
from arrt.mcp import bindings
from arrt.mcp.server import dispatch
from arrt.persistence.records import (
    AcquisitionMethod,
    FetchStatus,
    MatMethod,
    RightsStatus,
    SourceClass,
)


@pytest.fixture
def http(server_url):
    with httpx.Client(base_url=server_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def held(service, settings, decodable_jpeg):
    """A work with its master on disk and a mat the vision model chose."""
    artwork = service.add_artwork(title="Nighthawks", date_created="1942")
    source = service.add_source(
        artwork_id=artwork.id,
        url=f"https://museum.example/{artwork.id}",
        provider="artic",
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )
    relative = f"raw/{artwork.id}.jpg"
    decodable_jpeg(settings.art_root / relative, width=1600, height=1200, color=(150, 110, 60))
    service.record_original(
        artwork_id=artwork.id,
        source_id=source.id,
        path=relative,
        width=1600,
        height=1200,
        byte_size=(settings.art_root / relative).stat().st_size,
        content_hash=f"hash-{artwork.id}",
        fetch_status=FetchStatus.OK,
    )
    service.record_mat_color(artwork_id=artwork.id, hex_rgb="#27285b", method=MatMethod.VISION_MODEL)
    return artwork, settings.art_root / relative


def test_the_control_reads_the_mat_the_presets_and_the_derivation(http, service, held):
    work, master = held

    answer = http.get(f"/api/works/{work.id}/mat")

    assert answer.status_code == 200
    body = answer.json()
    assert body["current"]["hex_rgb"] == "#27285b"
    assert body["current"]["method"] == "vision_model"
    assert body["presets"] == [{"key": p.key, "label": p.label, "hex_rgb": p.hex_rgb} for p in MAT_PRESETS]
    assert body["derived_hex_rgb"] == derive(master).hex_rgb
    # Worked out, not recorded.
    assert len(service.mat_color_history(work.id)) == 1


@pytest.mark.parametrize("preset", MAT_PRESETS[1:] + MAT_PRESETS[:1], ids=lambda p: p.key)
def test_a_preset_is_recorded_as_the_curators_and_the_old_mat_kept(http, service, held, preset):
    work, _ = held

    answer = http.post(f"/api/works/{work.id}/mat", json={"preset": preset.key})

    assert answer.status_code == 200
    assert answer.json()["current"]["hex_rgb"] == preset.hex_rgb
    assert answer.json()["current"]["method"] == "manual"
    mats = service.mat_color_history(work.id)
    assert {(m.hex_rgb, m.is_current) for m in mats} == {(preset.hex_rgb, True), ("#27285b", False)}


def test_re_deriving_records_the_works_own_colour_as_derived(http, service, held):
    work, master = held

    answer = http.post(f"/api/works/{work.id}/mat", json={"derive": True})

    assert answer.status_code == 200
    current = answer.json()["current"]
    assert current["hex_rgb"] == derive(master).hex_rgb
    assert current["method"] == "derived"
    assert "curator's request" in current["reason"]
    assert service.current_mat_color(work.id).method is MatMethod.DERIVED


@pytest.mark.parametrize(
    ("body", "refusal"),
    [
        ({"preset": "dark", "derive": True}, "MORE_THAN_ONE_MAT"),
        ({}, "NO_MAT_NAMED"),
        ({"derive": False}, "NO_MAT_NAMED"),
    ],
    ids=["both", "neither", "derive-false"],
)
def test_a_choice_must_be_exactly_one(http, service, held, body, refusal):
    """In the service's words: the handler refuses nothing itself, and asking for no mat never reaches the paid model."""
    from arrt.library.acquisition import preparation

    work, _ = held

    answer = http.post(f"/api/works/{work.id}/mat", json=body)

    assert answer.status_code == 400
    assert answer.json()["error"] == getattr(preparation, refusal)
    assert service.current_mat_color(work.id).hex_rgb == "#27285b"
    assert len(service.mat_color_history(work.id)) == 1


#: Every way to name more than one mat, as each surface spells it.
_MORE_THAN_ONE = {
    "HTTP, a preset and derive": ("http", {"preset": "dark", "derive": True}),
    "MCP, a colour and a preset": ("mcp", {"hex_rgb": "#f4efe6", "preset": "dark"}),
    "MCP, a colour and the derived mat": ("mcp", {"hex_rgb": "#f4efe6", "preset": "derived"}),
}


def _refusal(http, services, work_id: str, surface: str, choice: dict) -> str:
    if surface == "http":
        answer = http.post(f"/api/works/{work_id}/mat", json=choice)
        assert answer.status_code == 400, answer.text
        return answer.json()["error"]
    payload = dispatch(services, "art_catalogue", {"action": "set_mat_color", "artwork_id": work_id, **choice})
    assert payload["success"] is False, payload
    return payload["error"]


def test_more_than_one_mat_is_refused_in_the_same_words_on_both_surfaces(http, services, held):
    """One act, one refusal: the sentence is the service's, whichever surface was asked and however it spells the choice.

    Before, HTTP refused a preset beside derive in its handler's words and MCP
    a colour beside a preset in its binding's, two validators for one act.
    """
    work, _ = held

    said = {name: _refusal(http, services, work.id, *case) for name, case in _MORE_THAN_ONE.items()}

    assert len(set(said.values())) == 1, said
    from arrt.library.acquisition.preparation import MORE_THAN_ONE_MAT

    assert set(said.values()) == {MORE_THAN_ONE_MAT}
    assert services.catalogue.current_mat_color(work.id).hex_rgb == "#27285b"


def _body(function) -> ast.FunctionDef:
    [node] = ast.parse(inspect.getsource(function).strip()).body
    assert isinstance(node, ast.FunctionDef)
    return node


@pytest.mark.parametrize("binding", [http_api.set_work_mat, bindings._set_mat_color], ids=lambda f: f.__module__)
def test_neither_binding_judges_the_mat_choice_itself(binding):
    """Each binding maps its arguments onto the one act and refuses nothing of its own (the thin-binding norm).

    Read from the source: no raise and no assert in the binding, and of
    preparation it calls only the one act, `set_work_mat`.
    """
    body = _body(binding)
    judged = [type(node).__name__ for node in ast.walk(body) if isinstance(node, (ast.Raise, ast.Assert))]
    called = {
        node.func.attr
        for node in ast.walk(body)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "preparation"
    }

    assert judged == [], f"{binding.__name__} judges the choice itself: {judged}"
    assert called == {"set_work_mat"}, f"{binding.__name__} calls preparation's {sorted(called)}"


def test_the_http_binding_cannot_ask_the_paid_model():
    """HTTP cannot ask the model: its choice is built with no fallback, so naming nothing is refused."""
    body = _body(http_api.set_work_mat)
    named = [
        node
        for node in ast.walk(body)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "named"
    ]

    assert len(named) == 1, "set_work_mat builds its choice once, through MatRequest.named"
    assert "otherwise" not in {keyword.arg for keyword in named[0].keywords}
    assert "MODEL" not in inspect.getsource(http_api.set_work_mat)


def test_an_unknown_preset_is_refused_by_name(http, service, held):
    work, _ = held

    answer = http.post(f"/api/works/{work.id}/mat", json={"preset": "off-white"})

    assert answer.status_code == 400
    assert "'off-white'" in answer.json()["error"]
    assert service.current_mat_color(work.id).hex_rgb == "#27285b"


def test_a_work_with_no_master_on_disk_offers_no_derivation(http, held):
    work, master = held
    master.unlink()

    body = http.get(f"/api/works/{work.id}/mat").json()

    assert body["derived_hex_rgb"] is None
    assert body["presets"]
    refused = http.post(f"/api/works/{work.id}/mat", json={"derive": True})
    assert refused.status_code == 400
    assert "not on disk" in refused.json()["error"]


def test_an_unknown_work_is_refused_by_name(http):
    """As every work route refuses one: 404, naming the id. Without the check, the
    read would answer an empty control for a work that does not exist."""
    for answer in (http.get("/api/works/no-such-work/mat"), http.post("/api/works/no-such-work/mat", json={"preset": "dark"})):
        assert answer.status_code == 404
        assert "no-such-work" in answer.json()["error"]


def test_a_colour_under_the_floor_is_refused_in_the_stores_words(http, service, held, monkeypatch):
    """No shipped preset is under the floor and the derivation lifts to it, so the
    state is built: a preset table holding a near-black, as one edited by hand
    might. The store's refusal must reach the curator as itself, and change nothing."""
    from arrt.library.acquisition import mat, preparation

    too_dark = mat.MatPreset(key="black", label="Black", hex_rgb="#111111")
    monkeypatch.setattr(preparation, "MAT_PRESETS", (*mat.MAT_PRESETS, too_dark))
    work, _ = held

    answer = http.post(f"/api/works/{work.id}/mat", json={"preset": "black"})

    assert answer.status_code == 400
    assert f"{mat.MAT_LIGHTNESS_FLOOR:g}" in answer.json()["error"]
    assert service.current_mat_color(work.id).hex_rgb == "#27285b"
