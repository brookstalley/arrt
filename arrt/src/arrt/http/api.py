"""The JSON surface the browser client reads, and the shaping that feeds it.

A handler unpacks the request, composes service calls, and formats the result,
and it never branches on a service call's answer to decide what happens next —
that decision belongs to the service layer, which the MCP tools call too
(`architecture.md` § Direction, as the owner amended it on 2026-10-05). Reading
back what a write produced, or joining two reads for one page, is composition and
conforms; so are the transport's own shapes: a conditional request answered with
`304`, and a service's "no such thing" mapped to `404`. A composition the MCP
surface needs too lives in a service, or is pinned by a test both surfaces run.
This is the same rule `mcp/bindings.py` states, and it is stated twice on purpose:
it is the only thing keeping an agent and a click from disagreeing about the same
catalogue.

**Handlers are synchronous `def`, deliberately.** The service layer is
synchronous and its work is real — sqlite reads, `fsync` on write, and a JPEG
downscale that can take a tenth of a second. Starlette runs a sync handler in a
worker thread, so none of that sits on the event loop, where it would stall the
MCP session manager sharing this process. The catalogue's one connection is
opened `check_same_thread=False` behind a re-entrant lock, which is what makes
that safe.

**The routes are one module per resource, in `arrt.http.routes`, and this module
assembles them.** FastAPI tries routes in the order they were registered. No two
routes of one method overlap today, so the order changes no answer, but a fixed
path added beside a parameter path would answer as it was placed, so the order
stays as it was. The resource modules cannot state it between them, because it
runs across resources: it is `_REGISTRATION_ORDER` here, and a route a module
declares without a place in it, or a place with no route, refuses the
application's start.
"""

from fastapi import APIRouter
from starlette.routing import BaseRoute

from arrt.http.routes import (
    acquisitions,
    affinities,
    artists,
    candidates,
    clients,
    exclusions,
    health,
    history,
    manifest,
    registry,
    runs,
    scenes,
    settings,
    sources,
    themes,
    topics,
    walls,
    watches,
    works,
)
from arrt.http.routes.acquisitions import _acquisition
from arrt.http.routes.candidates import _candidate_card, _verdict_notice
from arrt.http.routes.clients import _player_state
from arrt.http.routes.common import API_PREFIX, service_error_response
from arrt.http.routes.health import _failed_fetches, _health, _pictures
from arrt.http.routes.registry import LOOK_AGAIN, _look
from arrt.http.routes.runs import _spend, _spend_history
from arrt.http.routes.sources import _source_plugin
from arrt.http.routes.walls import _display_state, _last_shown, _wall, _wall_wait, _walls
from arrt.http.routes.watches import _watch
from arrt.http.routes.works import list_works, set_work_mat

#: The resource modules, each holding the routes of one resource.
_RESOURCES = (
    acquisitions,
    affinities,
    artists,
    candidates,
    clients,
    exclusions,
    health,
    history,
    manifest,
    registry,
    runs,
    scenes,
    settings,
    sources,
    themes,
    topics,
    walls,
    watches,
    works,
)

#: Every route's handler, in the order FastAPI tries them.
_REGISTRATION_ORDER: tuple[str, ...] = (
    "list_works",
    "archive_works",
    "get_work",
    "retry_acquisition",
    "list_acquisitions",
    "list_failure_causes",
    "list_cause_works",
    "retry_failure_cause",
    "set_work_identity",
    "list_artists",
    "get_artist",
    "get_artist_registry",
    "get_registry_artist",
    "search_registry",
    "get_similar_artists",
    "get_registry_work",
    "get_registry_work_look",
    "get_registry_work_look_picture",
    "list_topics",
    "search_topics",
    "get_topic",
    "get_topic_registry",
    "get_topic_works",
    "get_topic_artists",
    "set_artist_identity",
    "archive_work",
    "restore_work",
    "list_themes",
    "get_theme",
    "create_theme",
    "edit_theme",
    "delete_theme",
    "make_default_theme",
    "add_to_theme",
    "add_selection_to_theme",
    "remove_selection_from_theme",
    "remove_from_theme",
    "move_in_theme",
    "activate_theme",
    "list_walls",
    "create_wall",
    "rename_wall",
    "delete_wall",
    "assign_wall",
    "assign_display",
    "get_work_mat",
    "set_work_mat",
    "set_mat_mode",
    "set_playback",
    "add_label",
    "remove_label",
    "unassign_wall",
    "clear_wall",
    "hang_selection",
    "not_this_one_again",
    "list_exclusions",
    "allow_again",
    "work_placements",
    "list_history",
    "list_clients",
    "add_client",
    "rename_client",
    "remove_client",
    "issue_client_token",
    "step_wall",
    "get_scenes",
    "draft_scene",
    "pin_scene",
    "unpin_scene",
    "apply_scene",
    "release_scene",
    "discard_scene",
    "get_manifest",
    "get_health",
    "get_sources",
    "get_source_yields",
    "get_estimate",
    "get_budget",
    "start_run",
    "start_get",
    "list_runs",
    "get_run",
    "approve_run",
    "decline_run",
    "cancel_run",
    "get_spend_history",
    "get_run_spend",
    "start_resolve_run",
    "list_candidates",
    "get_candidate",
    "list_candidate_images",
    "set_verdict",
    "want_candidate",
    "list_wanted",
    "sighting_hosts",
    "wikidata_matches",
    "pick_wikidata_item",
    "select_candidate_image",
    "reject_candidate_image",
    "get_candidate_preview",
    "get_thumbnail",
    "get_wall_preview",
    "list_affinities",
    "set_affinity",
    "delete_affinity",
    "list_settings",
    "set_setting",
    "unattended_standing",
    "list_watches",
    "get_watch",
    "create_watch",
    "update_watch",
    "delete_watch",
)


def _assembled() -> list[BaseRoute]:
    """The resource modules' routes in `_REGISTRATION_ORDER`, each exactly once."""
    declared: dict[str, BaseRoute] = {}
    for resource in _RESOURCES:
        for route in resource.router.routes:
            if route.name in declared:
                raise RuntimeError(f"two routes are named {route.name}; a handler's name is its place in the registration order")
            declared[route.name] = route
    if len(set(_REGISTRATION_ORDER)) != len(_REGISTRATION_ORDER):
        raise RuntimeError("a route is placed twice in the registration order")
    unplaced = sorted(set(declared) - set(_REGISTRATION_ORDER))
    unrouted = sorted(set(_REGISTRATION_ORDER) - set(declared))
    if unplaced or unrouted:
        raise RuntimeError(f"the registration order and the routes disagree: no place for {unplaced}; no route for {unrouted}")
    return [declared[name] for name in _REGISTRATION_ORDER]


router = APIRouter(prefix=API_PREFIX)
router.routes.extend(_assembled())

__all__ = [
    "LOOK_AGAIN",
    "_acquisition",
    "_candidate_card",
    "_display_state",
    "_failed_fetches",
    "_health",
    "_last_shown",
    "_look",
    "_pictures",
    "_player_state",
    "_source_plugin",
    "_spend",
    "_spend_history",
    "_verdict_notice",
    "_wall",
    "_wall_wait",
    "_walls",
    "_watch",
    "list_works",
    "router",
    "service_error_response",
    "set_work_mat",
]
