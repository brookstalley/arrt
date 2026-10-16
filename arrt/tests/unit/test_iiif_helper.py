"""The IIIF parsers a plugin may use (interface 1.3), against answers three museums gave.

Every file under `tests/fixtures/iiif/` was answered on 2026-10-07
(`linked-art-findings.md`): Yale's image service speaks Image API 2 and declares no
limit, Getty's speaks 3 and declares 30,000 pixels a side, and the Rijksmuseum's
speaks 3 and declares an area of 17,550,000 pixels, smaller than its originals.
"""

import json
from pathlib import Path

import pytest

from arrt.library.sources import (
    CanvasImage,
    FetchLocator,
    ImageSearchFailure,
    ImageService,
    manifest_images,
    manifest_metadata,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "iiif"

YALE_NIGHT_CAFE = "https://images.collections.yale.edu/iiif/2/yuag:3b072179-2fc7-42bc-87cc-9ee4d782b270"
GETTY_IRISES = "https://media.getty.edu/iiif/image/8c255d80-7382-46db-9fa8-892c0d37247e"
DORT_RECTO = "https://images.collections.yale.edu/iiif/2/ycba:4f227f08-7842-46cc-b05a-e3c6a4614cc1"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# -- an image service's info.json ------------------------------------------------------


def test_a_version_2_service_states_the_original_and_no_limit():
    service = ImageService.from_info(fixture("info_v2_yale_night_cafe.json"))

    assert service == ImageService(id=YALE_NIGHT_CAFE, version=2, width=7408, height=5848)
    assert service.serves_original
    assert service.full_url == f"{YALE_NIGHT_CAFE}/full/full/0/default.jpg"
    assert service.info_url == f"{YALE_NIGHT_CAFE}/info.json"


def test_a_version_3_service_states_its_declared_limits_and_asks_for_max():
    service = ImageService.from_info(fixture("info_v3_getty_irises.json"))

    assert (service.id, service.version, service.width, service.height) == (GETTY_IRISES, 3, 9021, 7122)
    assert (service.max_width, service.max_height, service.max_area) == (30000, 30000, None)
    assert service.serves_original
    assert service.full_url == f"{GETTY_IRISES}/full/max/0/default.jpg"


def test_an_original_within_the_callers_side_and_every_declared_limit_is_one_request():
    service = ImageService.from_info(fixture("info_v3_getty_irises.json"))

    assert service.locator(direct_max_side=16384) == FetchLocator.direct(f"{GETTY_IRISES}/full/max/0/default.jpg")


def test_a_declared_area_smaller_than_the_original_is_the_tiles():
    """The Rijksmuseum's 14,645 × 12,158 original against its 17,550,000-pixel `maxArea`."""
    service = ImageService.from_info(fixture("info_v3_rijksmuseum_night_watch.json"))

    assert (service.width, service.height, service.max_area) == (14645, 12158, 17_550_000)
    assert not service.serves_original
    assert service.locator(direct_max_side=100_000) == FetchLocator.tiles("https://iiif.micr.io/PJEZO/info.json")


def test_a_declared_width_below_the_original_is_the_tiles_and_limits_the_height_too():
    info = {**fixture("info_v3_getty_irises.json"), "maxWidth": 9000}
    info.pop("maxHeight")

    service = ImageService.from_info(info)

    assert (service.max_width, service.max_height) == (9000, 9000)
    assert service.locator(direct_max_side=100_000) == FetchLocator.tiles(f"{GETTY_IRISES}/info.json")


def test_a_declared_height_alone_below_the_original_is_the_tiles():
    info = {**fixture("info_v3_getty_irises.json"), "maxHeight": 7000}
    info.pop("maxWidth")

    assert ImageService.from_info(info).locator(direct_max_side=100_000).url == f"{GETTY_IRISES}/info.json"


def test_a_version_2_limit_is_read_from_the_profile():
    info = fixture("info_v2_yale_night_cafe.json")
    info["profile"][1]["maxWidth"] = 4000

    service = ImageService.from_info(info)

    assert (service.max_width, service.max_height) == (4000, 4000)
    assert not service.serves_original


def test_a_limit_stated_twice_keeps_the_smaller():
    info = fixture("info_v2_yale_night_cafe.json")
    info["profile"] += [{"maxWidth": 9000}, {"maxWidth": 4000}, {"maxArea": 50_000_000}, {"maxArea": 30_000_000}]

    service = ImageService.from_info(info)

    assert (service.max_width, service.max_area) == (4000, 30_000_000)


def test_a_long_side_above_the_callers_bound_is_the_tiles_and_one_at_it_is_one_request():
    """Yale declares no limit, and answered HTTP 500 for this 46,800-pixel original asked in one request."""
    service = ImageService.from_info(fixture("info_v2_yale_46800_radiograph.json"))

    assert service.serves_original
    assert service.locator(direct_max_side=46799).url == f"{service.id}/info.json"
    assert service.locator(direct_max_side=46800).url == f"{service.id}/full/full/0/default.jpg"


def test_a_preview_asks_for_a_rendering_bounded_on_both_edges():
    service = ImageService.from_info(fixture("info_v2_yale_night_cafe.json"))

    assert service.preview_url(400) == f"{YALE_NIGHT_CAFE}/full/!400,400/0/default.jpg"


@pytest.mark.parametrize(
    "info",
    [
        [],
        {"@context": "http://iiif.io/api/image/1/context.json", "@id": YALE_NIGHT_CAFE, "width": 1, "height": 1},
        {"@context": "http://iiif.io/api/image/2/context.json", "id": YALE_NIGHT_CAFE, "width": 1, "height": 1},
        {"@context": "http://iiif.io/api/image/3/context.json", "id": GETTY_IRISES, "width": 0, "height": 1},
        {"@context": "http://iiif.io/api/image/3/context.json", "id": GETTY_IRISES, "width": True, "height": 1},
        {"@context": "http://iiif.io/api/image/3/context.json", "id": "file:///etc/passwd", "width": 1, "height": 1},
        {
            "@context": ["http://iiif.io/api/image/2/context.json", "http://iiif.io/api/image/3/context.json"],
            "@id": GETTY_IRISES,
            "id": GETTY_IRISES,
            "width": 1,
            "height": 1,
        },
    ],
    ids=["not-an-object", "version-1", "v2-spelled-as-v3", "zero-width", "boolean-width", "not-http", "two-versions"],
)
def test_a_body_that_is_not_an_image_service_could_not_be_asked(info):
    with pytest.raises(ImageSearchFailure):
        ImageService.from_info(info)


# -- a manifest's canvases -------------------------------------------------------------


def test_a_version_3_manifest_gives_each_canvas_its_service_size_label_and_metadata():
    images = manifest_images(fixture("manifest_v3_ycba_34_dort.json"))

    assert len(images) == 5
    first = images[0]
    assert (first.service, first.width, first.height) == (DORT_RECTO, 14484, 9741)
    assert first.image == f"{DORT_RECTO}/full/full/0/default.jpg"
    assert first.label == ("recto, cropped to image",)
    assert first.metadata["Image Use Rights"][0].startswith("No Copyright: You can copy")


def test_a_version_2_manifest_gives_the_same_canvases():
    v2 = manifest_images(fixture("manifest_v2_ycba_34_dort.json"))
    v3 = manifest_images(fixture("manifest_v3_ycba_34_dort.json"))

    assert [(c.service, c.width, c.height) for c in v2] == [(c.service, c.width, c.height) for c in v3]


def test_another_museums_manifest_names_its_own_services():
    images = manifest_images(fixture("manifest_v3_getty_irises.json"))

    assert images[0] == CanvasImage(
        service=GETTY_IRISES,
        image=f"{GETTY_IRISES}/full/max/0/default.jpg",
        width=9021,
        height=7122,
        label=images[0].label,
        metadata=images[0].metadata,
    )
    assert len({c.service for c in images}) == 3


def test_a_canvas_whose_image_names_no_iiif_service_has_none():
    manifest = fixture("manifest_v3_ycba_34_dort.json")
    del manifest["items"][0]["items"][0]["items"][0]["body"]["service"]

    first = manifest_images(manifest)[0]

    assert first.service is None
    assert first.image == f"{DORT_RECTO}/full/full/0/default.jpg"


def test_a_service_of_another_kind_is_not_an_image_service():
    manifest = fixture("manifest_v3_ycba_34_dort.json")
    body = manifest["items"][0]["items"][0]["items"][0]["body"]
    body["service"] = [{"id": "https://example.org/auth", "type": "AuthCookieService1", "profile": "login"}]

    assert manifest_images(manifest)[0].service is None


def test_a_manifest_with_no_canvases_has_no_images_and_a_canvas_with_no_image_is_left_out():
    manifest = fixture("manifest_v3_ycba_34_dort.json")
    empty = {**manifest, "items": []}
    manifest["items"][0]["items"] = []

    assert manifest_images(empty) == ()
    after_the_first = manifest_images(fixture("manifest_v3_ycba_34_dort.json"))[1:]
    assert [c.service for c in manifest_images(manifest)] == [c.service for c in after_the_first]


@pytest.mark.parametrize(
    "manifest",
    [
        [],
        {"@context": "http://iiif.io/api/presentation/3/context.json", "type": "Collection", "items": []},
        {"@context": "http://iiif.io/api/presentation/2/context.json", "@type": "sc:Collection"},
        {"@context": "http://iiif.io/api/image/2/context.json", "@id": YALE_NIGHT_CAFE},
        {"@context": "http://iiif.io/api/presentation/3/context.json", "type": "Manifest", "items": "none"},
        {"@context": "http://iiif.io/api/presentation/3/context.json", "type": "Manifest", "items": ["canvas"]},
    ],
    ids=["not-an-object", "v3-collection", "v2-collection", "an-image-service", "items-not-a-list", "canvas-not-an-object"],
)
def test_a_body_that_is_not_a_manifest_could_not_be_asked(manifest):
    with pytest.raises(ImageSearchFailure):
        manifest_images(manifest)


def test_a_manifests_metadata_keeps_every_value_of_every_label_in_order():
    metadata = manifest_metadata(fixture("manifest_v3_ycba_34_dort.json"))

    assert metadata["Title"] == ("Dort, or Dordrecht: The Dort Packet-Boat from Rotterdam Becalmed",)
    assert metadata["Creator"][0].startswith("Joseph Mallord William Turner, born in London")


def test_a_version_2_manifests_metadata_reads_the_same():
    v2 = manifest_metadata(fixture("manifest_v2_ycba_34_dort.json"))

    assert v2["Title"] == manifest_metadata(fixture("manifest_v3_ycba_34_dort.json"))["Title"]


def test_metadata_in_several_languages_and_written_twice_keeps_them_all():
    manifest = {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "type": "Manifest",
        "items": [],
        "metadata": [
            {"label": {"en": ["Title"]}, "value": {"en": ["The Bridge"], "fr": ["Le Pont"]}},
            {"label": {"en": ["Title"]}, "value": {"none": ["Pont"]}},
            {"label": {"en": ["Blank"]}, "value": {"en": ["  "]}},
        ],
    }

    assert manifest_metadata(manifest) == {"Title": ("The Bridge", "Le Pont", "Pont"), "Blank": ()}
