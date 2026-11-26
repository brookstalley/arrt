"""The JSON routes' registration order and shape: what FastAPI matches, by what name, answering with what.

FastAPI tries routes in the order they were registered, and the routes are declared in
one module per resource (`arrt.http.routes`) and assembled in `arrt.http.api`. Splitting a router across
files is a move that can silently reorder it, change a handler's name (which is its
operation id) or drop a response model, and every one of those still answers requests.
This table is what the router answered with when it was one file; a route added,
removed or moved is a line changed here, in the same commit.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI

from arrt.http import api

#: (method, path, handler name, response model) in registration order. A handler that
#: answers with a file or a stream names no model.
RECORDED: tuple[tuple[str, str, str, str | None], ...] = (
    ("GET", "/api/works", "list_works", "WorkPageOut"),
    ("POST", "/api/works/archive", "archive_works", "ArchivedWorksOut"),
    ("GET", "/api/works/{artwork_id}", "get_work", "WorkDetailOut"),
    ("POST", "/api/works/{artwork_id}/acquisition/retry", "retry_acquisition", "AcquisitionStateOut"),
    ("GET", "/api/acquisitions", "list_acquisitions", "AcquisitionQueueOut"),
    ("GET", "/api/acquisitions/causes", "list_failure_causes", "FailureCausesOut"),
    ("GET", "/api/acquisitions/causes/works", "list_cause_works", "CauseWorksOut"),
    ("POST", "/api/acquisitions/causes/retry", "retry_failure_cause", "RetryCauseOut"),
    ("POST", "/api/works/{artwork_id}/wikidata", "set_work_identity", "WorkDetailOut"),
    ("GET", "/api/artists", "list_artists", "ArtistListOut"),
    ("GET", "/api/artists/{artist_id}", "get_artist", "HeldArtistOut"),
    ("GET", "/api/artists/{artist_id}/registry", "get_artist_registry", "ArtistRegistryOut"),
    ("GET", "/api/registry/artists/{qid}", "get_registry_artist", "ArtistRegistryOut"),
    ("GET", "/api/registry/search", "search_registry", "RegistrySearchOut"),
    ("GET", "/api/registry/artists/{qid}/similar", "get_similar_artists", "SimilarArtistsOut"),
    ("GET", "/api/registry/works/{qid}", "get_registry_work", "RegistryWorkPageOut"),
    ("GET", "/api/registry/works/{qid}/look", "get_registry_work_look", "LookOut"),
    ("GET", "/api/registry/works/{qid}/look/pictures/{key}", "get_registry_work_look_picture", None),
    ("GET", "/api/topics", "list_topics", "TopicsOut"),
    ("GET", "/api/registry/topics", "search_topics", "TopicSearchOut"),
    ("GET", "/api/topics/{qid}", "get_topic", "TopicPageOut"),
    ("GET", "/api/topics/{qid}/registry", "get_topic_registry", "TopicRegistryOut"),
    ("GET", "/api/topics/{qid}/works", "get_topic_works", None),
    ("GET", "/api/topics/{qid}/artists", "get_topic_artists", "TopicArtistsOut"),
    ("POST", "/api/artists/{artist_id}/wikidata", "set_artist_identity", "ArtistOut"),
    ("POST", "/api/works/{artwork_id}/archive", "archive_work", "WorkDetailOut"),
    ("POST", "/api/works/{artwork_id}/restore", "restore_work", "WorkDetailOut"),
    ("GET", "/api/themes", "list_themes", "ThemeListOut"),
    ("GET", "/api/themes/{theme_id}", "get_theme", "ThemeDetailOut"),
    ("POST", "/api/themes", "create_theme", "ThemeOut"),
    ("POST", "/api/themes/{theme_id}", "edit_theme", "ThemeOut"),
    ("DELETE", "/api/themes/{theme_id}", "delete_theme", "ThemeListOut"),
    ("POST", "/api/themes/{theme_id}/default", "make_default_theme", "ThemeListOut"),
    ("POST", "/api/themes/{theme_id}/works", "add_to_theme", "ThemeDetailOut"),
    ("POST", "/api/themes/{theme_id}/works/bulk", "add_selection_to_theme", "ThemeAdditionOut"),
    ("POST", "/api/themes/{theme_id}/works/remove", "remove_selection_from_theme", "ThemeRemovalOut"),
    ("DELETE", "/api/themes/{theme_id}/works/{artwork_id}", "remove_from_theme", "ThemeDetailOut"),
    ("POST", "/api/themes/{theme_id}/works/{artwork_id}/position", "move_in_theme", "ThemeDetailOut"),
    ("POST", "/api/themes/{theme_id}/activate", "activate_theme", "ManifestOut"),
    ("GET", "/api/walls", "list_walls", "WallListOut"),
    ("POST", "/api/walls", "create_wall", "WallOut"),
    ("POST", "/api/walls/{wall_id}", "rename_wall", "WallOut"),
    ("DELETE", "/api/walls/{wall_id}", "delete_wall", "WallListOut"),
    ("POST", "/api/walls/{wall_id}/client", "assign_wall", "WallAssignmentOut"),
    ("POST", "/api/walls/{wall_id}/display", "assign_display", "WallAssignmentOut"),
    ("GET", "/api/works/{artwork_id}/mat", "get_work_mat", "WorkMatOut"),
    ("POST", "/api/works/{artwork_id}/mat", "set_work_mat", "WorkMatOut"),
    ("PUT", "/api/walls/{wall_id}/mat", "set_mat_mode", "WallOut"),
    ("PUT", "/api/walls/{wall_id}/playback", "set_playback", "WallOut"),
    ("POST", "/api/walls/{wall_id}/labels", "add_label", "LabelAssignmentOut"),
    ("DELETE", "/api/walls/{wall_id}/labels/{label_id}", "remove_label", "WallOut"),
    ("DELETE", "/api/walls/{wall_id}/client", "unassign_wall", "WallOut"),
    ("DELETE", "/api/walls/{wall_id}/theme", "clear_wall", "WallOut"),
    ("POST", "/api/walls/{wall_id}/selection", "hang_selection", "ManifestOut"),
    ("POST", "/api/walls/{wall_id}/not-again", "not_this_one_again", "NotAgainOut"),
    ("GET", "/api/exclusions", "list_exclusions", "ExcludedWorkListOut"),
    ("DELETE", "/api/exclusions/{artwork_id}", "allow_again", "ExcludedWorkListOut"),
    ("GET", "/api/works/{artwork_id}/placements", "work_placements", "WorkPlacementsOut"),
    ("GET", "/api/history", "list_history", "HistoryPageOut"),
    ("GET", "/api/clients", "list_clients", "ClientListOut"),
    ("POST", "/api/clients", "add_client", "ClientOut"),
    ("POST", "/api/clients/{client_id}", "rename_client", "ClientOut"),
    ("DELETE", "/api/clients/{client_id}", "remove_client", "ClientListOut"),
    ("POST", "/api/clients/{client_id}/token", "issue_client_token", "ClientTokenOut"),
    ("POST", "/api/walls/{wall_id}/next", "step_wall", "NextOut"),
    ("GET", "/api/scenes/live", "get_scenes", "ScenesOut"),
    ("POST", "/api/scenes", "draft_scene", "SceneOut"),
    ("PUT", "/api/scenes/{scene_id}/pins/{wall_id}", "pin_scene", "SceneOut"),
    ("DELETE", "/api/scenes/{scene_id}/pins/{wall_id}", "unpin_scene", "SceneOut"),
    ("POST", "/api/scenes/{scene_id}/apply", "apply_scene", "SceneOut"),
    ("POST", "/api/scenes/{scene_id}/release", "release_scene", "SceneOut"),
    ("DELETE", "/api/scenes/{scene_id}", "discard_scene", "ScenesOut"),
    ("GET", "/api/manifest", "get_manifest", "ManifestOut"),
    ("GET", "/api/health", "get_health", "HealthOut"),
    ("GET", "/api/sources", "get_sources", "SourcesOut"),
    ("GET", "/api/sources/yields", "get_source_yields", "SourceYieldsOut"),
    ("GET", "/api/estimate", "get_estimate", "EstimateOut"),
    ("GET", "/api/budget", "get_budget", "BudgetOut"),
    ("POST", "/api/runs", "start_run", "RunOut"),
    ("POST", "/api/gets", "start_get", "GetOut"),
    ("GET", "/api/runs", "list_runs", "RunListOut"),
    ("GET", "/api/runs/{run_id}", "get_run", "RunViewOut"),
    ("POST", "/api/runs/{run_id}/approve", "approve_run", "RunViewOut"),
    ("POST", "/api/runs/{run_id}/decline", "decline_run", "RunViewOut"),
    ("POST", "/api/runs/{run_id}/cancel", "cancel_run", "RunViewOut"),
    ("GET", "/api/spend", "get_spend_history", "SpendHistoryOut"),
    ("GET", "/api/runs/{run_id}/spend", "get_run_spend", "SpendOut"),
    ("POST", "/api/runs/resolve", "start_resolve_run", "RunOut"),
    ("GET", "/api/runs/{run_id}/candidates", "list_candidates", "CandidatePageOut"),
    ("GET", "/api/candidates/{work_id}", "get_candidate", "CandidateCardOut"),
    ("GET", "/api/candidates/{work_id}/images", "list_candidate_images", "InstanceListingOut"),
    ("POST", "/api/candidates/{work_id}/verdict", "set_verdict", "VerdictOut"),
    ("POST", "/api/candidates/{work_id}/want", "want_candidate", "CandidateWorkOut"),
    ("GET", "/api/wanted", "list_wanted", "WantedListingOut"),
    ("GET", "/api/sightings/hosts", "sighting_hosts", "SightingHostsOut"),
    ("GET", "/api/candidates/{work_id}/wikidata-matches", "wikidata_matches", "WorkMatchesOut"),
    ("PUT", "/api/candidates/{work_id}/wikidata-item", "pick_wikidata_item", "CandidateWorkOut"),
    ("POST", "/api/candidate-images/{image_id}/select", "select_candidate_image", "SelectedImageOut"),
    ("POST", "/api/candidate-images/{image_id}/reject", "reject_candidate_image", "CandidateWorkOut"),
    ("GET", "/api/candidate-images/{image_id}/preview", "get_candidate_preview", None),
    ("GET", "/api/works/{artwork_id}/thumbnail", "get_thumbnail", None),
    ("GET", "/api/works/{artwork_id}/wall-preview", "get_wall_preview", None),
    ("GET", "/api/affinities", "list_affinities", "AffinityListOut"),
    ("POST", "/api/affinities", "set_affinity", "AffinityOut"),
    ("DELETE", "/api/affinities/{affinity_id}", "delete_affinity", "AffinityOut"),
    ("GET", "/api/settings", "list_settings", "SettingListOut"),
    ("POST", "/api/settings/{key}", "set_setting", "SettingOut"),
    ("GET", "/api/unattended", "unattended_standing", "UnattendedOut"),
    ("GET", "/api/watches", "list_watches", "WatchListOut"),
    ("GET", "/api/watches/{watch_id}", "get_watch", "WatchOut"),
    ("POST", "/api/watches", "create_watch", "WatchOut"),
    ("POST", "/api/watches/{watch_id}", "update_watch", "WatchOut"),
    ("DELETE", "/api/watches/{watch_id}", "delete_watch", "WatchOut"),
)


def _table(router: Any) -> list[tuple[str, str, str, str | None]]:
    return [
        (
            ", ".join(sorted(route.methods)),
            route.path,
            route.name,
            route.response_model.__name__ if isinstance(route.response_model, type) else None,
        )
        for route in router.routes
    ]


def _first_difference(found: list[tuple[str, str, str, str | None]]) -> str:
    for place, (want, got) in enumerate(zip(RECORDED, found, strict=False)):
        if want != got:
            return f"at place {place} the table has {want} and the router has {got}"
    return f"the table has {len(RECORDED)} routes and the router has {len(found)}"


def test_the_router_registers_the_recorded_routes_in_the_recorded_order():
    found = _table(api.router)

    assert found == list(RECORDED), _first_difference(found)


def test_the_openapi_document_describes_each_recorded_route_once_with_its_model():
    app = FastAPI()
    app.include_router(api.router)
    paths = app.openapi()["paths"]

    described = [(method.upper(), path) for path, operations in paths.items() for method in operations]
    assert sorted(described) == sorted(
        (method, path) for method, path, _, _ in RECORDED
    ), "a route is missing from, or extra in, the document"
    operation_ids = [operation["operationId"] for operations in paths.values() for operation in operations.values()]
    assert len(set(operation_ids)) == len(operation_ids), "two operations share an id"
    for method, path, name, model in RECORDED:
        operation = paths[path][method.lower()]
        assert operation["operationId"].startswith(name + "_"), f"{method} {path} is no longer the handler {name}"
        if model is not None:
            schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
            assert schema["$ref"].endswith("/" + model), f"{method} {path} answers with something other than {model}"


def test_a_route_is_registered_only_from_a_resource_module():
    for route in api.router.routes:
        assert route.endpoint.__module__.startswith("arrt.http.routes."), f"{route.name} is defined outside the resource modules"


def test_the_router_keeps_the_prefix_the_application_reads():
    assert api.router.prefix == "/api"
    assert all(route.path.startswith("/api/") for route in api.router.routes)


def test_a_route_with_no_place_in_the_registration_order_refuses_the_start(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "_REGISTRATION_ORDER", tuple(name for name in api._REGISTRATION_ORDER if name != "get_run"))

    with pytest.raises(RuntimeError, match="get_run"):
        api._assembled()


def test_a_place_in_the_registration_order_with_no_route_refuses_the_start(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "_REGISTRATION_ORDER", (*api._REGISTRATION_ORDER, "a_route_nobody_wrote"))

    with pytest.raises(RuntimeError, match="a_route_nobody_wrote"):
        api._assembled()


def test_a_route_placed_twice_in_the_registration_order_refuses_the_start(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api, "_REGISTRATION_ORDER", (*api._REGISTRATION_ORDER, "get_run"))

    with pytest.raises(RuntimeError, match="twice"):
        api._assembled()


def test_two_resource_modules_naming_a_route_alike_refuse_the_start(monkeypatch: pytest.MonkeyPatch):
    twin = APIRouter()
    twin.add_api_route("/api/another", lambda: None, name="get_run")
    monkeypatch.setattr(api, "_RESOURCES", (*api._RESOURCES, SimpleNamespace(router=twin)))

    with pytest.raises(RuntimeError, match="get_run"):
        api._assembled()
