"""The Work page's mat control, over HTTP (#91).

`GET /api/works/{id}/mat` answers the current mat, the one-press presets, and
what re-deriving would give, recording nothing. `POST` records a preset as the
curator's (`manual`) or the derivation as `derived`, keeps the previous colour,
and answers the same shape, so the control repaints from what was recorded.

Against a real uvicorn server, per the suite's standing rule.
"""

import httpx
import pytest

from arrt.library.acquisition.mat import MAT_PRESETS, derive
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
    "body",
    [{"preset": "dark", "derive": True}, {}, {"derive": False}],
    ids=["both", "neither", "derive-false"],
)
def test_a_choice_must_be_exactly_one(http, service, held, body):
    work, _ = held

    answer = http.post(f"/api/works/{work.id}/mat", json=body)

    assert answer.status_code == 400
    assert "not both" in answer.json()["error"]
    assert service.current_mat_color(work.id).hex_rgb == "#27285b"


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
    """As every work route refuses one: 400, naming the id. Without the check, the
    read would answer an empty control for a work that does not exist."""
    for answer in (http.get("/api/works/no-such-work/mat"), http.post("/api/works/no-such-work/mat", json={"preset": "dark"})):
        assert answer.status_code == 400
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
