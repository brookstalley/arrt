"""Arrt's Player surface, as the contract describes it, and nothing more.

Served on the contract's own routes (`contract/routes.json`) with the contract's
own admission rules (`player-contract.md` § Transport), so the tests that use it
pin the Player to the contract rather than to Arrt's code, which a Player in
another repository will not have:

* every request carries a client's token: unknown is `401`;
* a per-wall route for a wall not assigned to that client is `403`;
* `GET /client` lists that client's walls with an ETag, `304` on a match;
* `POST /client/heartbeat` is `204`, and `400` for a body the contract's schema
  refuses — so a Player writing a bad one fails here as it would against Arrt;
* `GET /labels/{label_id}` serves a label document with an ETag, `304` on a
  match, and `403` for a label output another client holds or an unknown id.
"""

import copy
import hashlib
import io
import json
from pathlib import Path

from aiohttp import web
from jsonschema import Draft202012Validator
from PIL import Image

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
ROUTES = json.loads((CONTRACT / "routes.json").read_text(encoding="utf-8"))["routes"]
MANIFEST_FIXTURE = json.loads((CONTRACT / "fixtures" / "manifest.v1" / "valid" / "minor-2-with-media.json").read_text())
CLIENT_HEARTBEAT_SCHEMA = json.loads((CONTRACT / "schemas" / "client-heartbeat.v1.schema.json").read_text())

#: The client every test's Player is, unless it says otherwise.
TOKEN = "the-clients-token"
CLIENT_ID = "c-the-pi"


class ServerDouble:
    """One server, any number of clients and walls, every document held in memory."""

    def __init__(self, *, wall_id: str = "living-room", output: str = "frame") -> None:
        #: Each wall's manifest, or absent for a wall nothing has been published for.
        self.manifests: dict[str, dict] = {}
        self.media: dict[str, bytes] = {}
        #: token -> client id. A token mapped to a client this server does not
        #: hold is a valid token for a client with no walls.
        self.tokens: dict[str, str] = {TOKEN: CLIENT_ID}
        self.clients: dict[str, dict] = {
            CLIENT_ID: {"name": "The Pi in the hall", "walls": [{"wall_id": wall_id, "name": wall_id, "output": output}]}
        }
        #: Each wall heartbeat POSTed, as bytes, in order, and by wall.
        self.heartbeats: list[bytes] = []
        self.heartbeats_by_wall: dict[str, list[dict]] = {}
        #: Each client heartbeat accepted.
        self.client_heartbeats: list[dict] = []
        #: Forced answers, for the failure tests.
        self.media_status: int | None = None
        self.client_status: int | None = None
        self.client_body: bytes | None = None
        self.authorizations: list[str | None] = []
        self.requests: list[tuple[str, str]] = []
        self.echo_heartbeats_to: Path | None = None
        #: Each label's document, by label id.
        self.label_documents: dict[str, dict] = {}
        #: A forced answer for every label request, for the failure tests.
        self.label_status: int | None = None
        self._default_wall = wall_id
        #: Each manifest major requested, in order, as the integer asked for.
        self.majors_requested: list[int] = []

    # -- the app ---------------------------------------------------------------------

    def app(self) -> web.Application:
        application = web.Application()
        for key, handler in (
            ("client", self.serve_client),
            ("client_heartbeat", self.receive_client_heartbeat),
            ("manifest", self.serve_manifest),
            ("manifest_major", self.serve_manifest_major),
            ("media", self.serve_media),
            ("heartbeat", self.receive_heartbeat),
            ("label", self.serve_label),
        ):
            application.router.add_route(ROUTES[key]["method"], ROUTES[key]["path"], handler)
        return application

    def _admit(self, request: web.Request, wall_id: str | None) -> tuple[dict | None, web.Response | None]:
        header = request.headers.get("Authorization")
        self.authorizations.append(header)
        self.requests.append((request.method, request.path))
        client_id = self.tokens.get((header or "").removeprefix("Bearer "))
        if client_id is None:
            return None, web.json_response({"error": "A valid client token is required."}, status=401)
        client = self.clients.get(client_id, {"name": client_id, "walls": []})
        if wall_id is not None and wall_id not in {wall["wall_id"] for wall in client["walls"]}:
            return None, web.json_response({"error": "That wall is not this client's."}, status=403)
        return {"client_id": client_id, **client}, None

    async def serve_client(self, request: web.Request) -> web.Response:
        client, refused = self._admit(request, None)
        if refused is not None:
            return refused
        if self.client_status is not None:
            return web.Response(status=self.client_status)
        body = self.client_body or json.dumps(client).encode()
        etag = f'"{hashlib.sha256(body).hexdigest()}"'
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=304, headers={"ETag": etag})
        return web.Response(body=body, content_type="application/json", headers={"ETag": etag})

    async def receive_client_heartbeat(self, request: web.Request) -> web.Response:
        _client, refused = self._admit(request, None)
        if refused is not None:
            return refused
        try:
            document = json.loads(await request.read())
        except ValueError:
            return web.json_response({"error": "The body is not JSON."}, status=400)
        errors = [error.message for error in Draft202012Validator(CLIENT_HEARTBEAT_SCHEMA).iter_errors(document)]
        names = [output.get("name") for output in document.get("outputs", []) if isinstance(output, dict)]
        if len(names) != len(set(names)):
            errors.append("two outputs share a name")
        if errors:
            return web.json_response({"error": "; ".join(errors)}, status=400)
        self.client_heartbeats.append(document)
        return web.Response(status=204)

    async def serve_label(self, request: web.Request) -> web.Response:
        client, refused = self._admit(request, None)
        if refused is not None:
            return refused
        if self.label_status is not None:
            return web.Response(status=self.label_status)
        label_id = request.match_info["label_id"]
        document = self.label_documents.get(label_id)
        if document is None or label_id not in {label["label_id"] for label in client.get("labels", [])}:
            return web.json_response({"error": "That label output is not this client's."}, status=403)
        body = json.dumps(document).encode()
        etag = f'"{hashlib.sha256(body).hexdigest()}"'
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=304, headers={"ETag": etag})
        return web.Response(body=body, content_type="application/json", headers={"ETag": etag})

    async def serve_manifest(self, request: web.Request) -> web.Response:
        wall_id = request.match_info["wall_id"]
        _client, refused = self._admit(request, wall_id)
        if refused is not None:
            return refused
        manifest = self.manifests.get(wall_id)
        if manifest is None:
            return web.json_response({"error": "Nothing has been published for this wall yet."}, status=404)
        body = json.dumps(manifest).encode()
        etag = f'"{hashlib.sha256(body).hexdigest()}"'
        if request.headers.get("If-None-Match") == etag:
            return web.Response(status=304, headers={"ETag": etag})
        return web.Response(body=body, content_type="application/json", headers={"ETag": etag})

    async def serve_manifest_major(self, request: web.Request) -> web.Response:
        """A wall's manifest at one major, as Arrt mounts it: 404 for a major it does not publish for that wall."""
        major = int(request.match_info["major"])
        self.majors_requested.append(major)
        wall_id = request.match_info["wall_id"]
        _client, refused = self._admit(request, wall_id)
        if refused is not None:
            return refused
        manifest = self.manifests.get(wall_id)
        if manifest is None or manifest["schema"]["major"] != major:
            return web.json_response({"error": f"No manifest of major {major} is published for this wall."}, status=404)
        return await self.serve_manifest(request)

    async def serve_media(self, request: web.Request) -> web.Response:
        _client, refused = self._admit(request, None)
        if refused is not None:
            return refused
        if self.media_status is not None:
            return web.Response(status=self.media_status)
        data = self.media.get(request.match_info["sha256"])
        if data is None:
            return web.json_response({"error": "No render with that hash is held."}, status=404)
        return web.Response(body=data, content_type="image/jpeg")

    async def receive_heartbeat(self, request: web.Request) -> web.Response:
        wall_id = request.match_info["wall_id"]
        _client, refused = self._admit(request, wall_id)
        if refused is not None:
            return refused
        body = await request.read()
        self.heartbeats.append(body)
        self.heartbeats_by_wall.setdefault(wall_id, []).append(json.loads(body))
        if self.echo_heartbeats_to is not None:
            # What Arrt does with a POSTed heartbeat on a host it shares.
            self.echo_heartbeats_to.write_bytes(body)
        return web.Response(status=204)

    # -- curating ----------------------------------------------------------------------

    @property
    def manifest(self) -> dict | None:
        """The default wall's manifest."""
        return self.manifests.get(self._default_wall)

    @manifest.setter
    def manifest(self, document: dict | None) -> None:
        if document is None:
            self.manifests.pop(self._default_wall, None)
        else:
            self.manifests[self._default_wall] = document

    def assign(self, wall_id: str, output: str, *, client_id: str = CLIENT_ID) -> None:
        """Place a wall on one of a client's outputs, taking it from wherever it was."""
        self.unassign(wall_id)
        self.clients.setdefault(client_id, {"name": client_id, "walls": []})["walls"].append(
            {"wall_id": wall_id, "name": wall_id, "output": output}
        )

    def map_label(self, label_id: str, output: str, wall_id: str, document: dict, *, client_id: str = CLIENT_ID) -> None:
        """Map one of a client's label outputs to a wall, serving `document` for it."""
        client = self.clients.setdefault(client_id, {"name": client_id, "walls": []})
        client["labels"] = [label for label in client.get("labels", []) if label["output"] != output]
        client["labels"].append({"label_id": label_id, "output": output, "wall_id": wall_id})
        self.label_documents[label_id] = document

    def unmap_label(self, label_id: str) -> None:
        for client in self.clients.values():
            client["labels"] = [label for label in client.get("labels", []) if label["label_id"] != label_id]

    def unassign(self, wall_id: str) -> None:
        for client in self.clients.values():
            client["walls"] = [wall for wall in client["walls"] if wall["wall_id"] != wall_id]

    def publish(
        self,
        *work_ids: str,
        wall_id: str | None = None,
        sequence: int = 4,
        interval_seconds: int | None = None,
        renders: dict[str, bytes] | None = None,
    ) -> dict:
        """The contract's minor 2 fixture for one wall, carrying these works with real bytes behind their hashes."""
        document = copy.deepcopy(MANIFEST_FIXTURE)
        template = document["entries"][0]
        document["entries"] = []
        document["directive"]["sequence"] = sequence
        if interval_seconds is not None:
            document["rotation"]["interval_seconds"] = interval_seconds
        for work_id in work_ids:
            data = (renders or {}).get(work_id, f"the render of {work_id}".encode())
            sha = hashlib.sha256(data).hexdigest()
            self.media[sha] = data
            entry = copy.deepcopy(template)
            entry["work_id"] = work_id
            entry["label"] = {**entry["label"], "title": f"Title of {work_id}"}
            entry["media"] = {"url": f"/media/sha256-{sha}", "sha256": sha, "bytes": len(data), "content_type": "image/jpeg"}
            document["entries"].append(entry)
        self.manifests[wall_id or self._default_wall] = document
        return document

    def publish_feed(
        self,
        slots: list[tuple[str, str, str]],
        *,
        staging: tuple[str, ...] = (),
        wall_id: str | None = None,
        media: dict[str, bytes] | None = None,
    ) -> dict:
        """A one-day major 2 feed for one wall, each work's master held behind its hash.

        `slots` are (work, from, until) as full RFC 3339 instants on 2026-06-21,
        the test clock's day. `media` overrides a work's bytes; a work whose
        bytes are given as b"" is published with a hash but nothing held for it.
        """
        works: dict[str, dict] = {}
        for work_id in dict.fromkeys([work for work, _, _ in slots] + list(staging)):
            data = (media or {}).get(work_id, _a_master(work_id))
            sha = hashlib.sha256(data or work_id.encode()).hexdigest()
            if data:
                self.media[sha] = data
            works[work_id] = {
                "media": {"url": f"/media/sha256-{sha}", "sha256": sha, "bytes": len(data), "content_type": "image/jpeg"},
                "mat_color": "#222222",
                "label": {"title": f"Title of {work_id}"},
            }
        document = {
            "schema": {"major": 2, "minor": 0},
            "generated_at": "2026-06-21T00:00:00+00:00",
            "playlist": {"id": "pl-1", "name": "A playlist"},
            "works": works,
            "schedule": {
                "horizon": {"from": "2026-06-21T00:00:00+00:00", "until": "2026-06-22T00:00:00+00:00"},
                "slots": [{"work_id": work, "from": start, "until": until} for work, start, until in slots],
            },
            "scene": None,
            "staging": list(staging),
        }
        self.manifests[wall_id or self._default_wall] = document
        return document


def _a_master(work_id: str) -> bytes:
    """A small real JPEG, its colour drawn from the work's id, so each work's hash differs and a wall can compose it."""
    shade = hashlib.sha256(work_id.encode()).digest()
    buffer = io.BytesIO()
    Image.new("RGB", (120, 80), (shade[0], shade[1], shade[2])).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()
