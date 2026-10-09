"""The works, artists and topics a reply offers, read off what its tools returned.

A card is an item **the answer names that a tool returned**. A registry search
returns dozens of items and the answer is where the agent chose among them, so
the answer decides which become cards; the tool payloads decide what each card
says. A QID the answer names that no tool returned gets no card, so an item a
model invented is never offered for Get.

The eval's scorer reads tool payloads through `items_in` too, so what it counts
as a work, an artist or a topic is what a curator is shown.
"""

import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal

_QID = re.compile(r"\bQ[1-9][0-9]*\b")

Kind = Literal["work", "artist", "topic"]


@dataclass(frozen=True)
class Item:
    """One thing a tool returned, in the fields a card shows."""

    kind: Kind
    qid: str
    #: A work's title, an artist's name, a topic's label.
    label: str
    #: A work's makers, an artist's years, a topic's kinds: one line under the label.
    detail: str
    #: The library's own id when it holds this: an artwork id for a work, an artist id for an artist.
    held: str | None = None
    #: A topic's kinds as the registry gives them (`period`, `movement`, …); empty otherwise.
    kinds: tuple[str, ...] = ()
    image: str | None = None

    def card(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "qid": self.qid,
            "label": self.label,
            "detail": self.detail,
            "held": self.held,
            "kinds": list(self.kinds),
            "image": self.image,
        }


def qids_named(text: str) -> list[str]:
    """Every QID in `text`, once each, in the order it first appears."""
    return list(dict.fromkeys(_QID.findall(text)))


def items_in(payload: object) -> dict[str, Item]:
    """Every work, artist and topic anywhere in one tool payload, by QID.

    Read by shape, not by which action answered, because the same work comes
    back from a search, an artist's page and a topic's works in the same
    fields. What does not take one of the three shapes is not an item:
    museums (`holdings`, `holders`) carry a name and a QID but neither years
    nor an artist id.
    """
    found: dict[str, Item] = {}
    for node in _dicts(payload):
        item = _item(node)
        if item is not None:
            _keep(found, item)
    return found


def cards_for(answer: str, payloads: Iterable[object]) -> list[dict[str, Any]]:
    """The cards a reply offers: each item the answer names that some payload returned, in the answer's order."""
    known: dict[str, Item] = {}
    for payload in payloads:
        for item in items_in(payload).values():
            _keep(known, item)
    return [known[qid].card() for qid in qids_named(answer) if qid in known]


def _keep(known: dict[str, Item], item: Item) -> None:
    """Add `item` to `known`, where the same item seen twice, once marked held, keeps the library's answer."""
    standing = known.get(item.qid)
    if standing is None or (standing.held is None and item.held is not None):
        known[item.qid] = item


def _item(node: Mapping[str, Any]) -> Item | None:
    return _held_work(node) or _registry_item(node)


def _held_work(node: Mapping[str, Any]) -> Item | None:
    """A work the library holds, as `art_catalogue(action='get')` gives it: its item is `wikidata_qid`."""
    if not (_is_qid(node.get("wikidata_qid")) and isinstance(node.get("artwork_id"), str) and isinstance(node.get("title"), str)):
        return None
    artist = node.get("artist")
    maker = _text(artist.get("name")) if isinstance(artist, Mapping) else _text(artist)
    return Item("work", node["wikidata_qid"], node["title"], maker or "", held=node["artwork_id"])


def _registry_item(node: Mapping[str, Any]) -> Item | None:
    """A work, artist or topic as the registry actions give one: its item is `qid`."""
    qid = node.get("qid")
    if not _is_qid(qid):
        return None
    if "title" in node:
        title = node.get("title")
        if not isinstance(title, str):
            return None
        held = node.get("held_artwork_ids") or ()
        return Item("work", qid, title, _makers(node), held=held[0] if held else None, image=_text(node.get("image")))
    name = node.get("name")
    if isinstance(name, str) and ("artist_id" in node or "born" in node):
        return Item("artist", qid, name, _years(node), held=_text(node.get("artist_id")))
    label = node.get("label")
    if isinstance(label, str):
        kinds = tuple(str(kind) for kind in node.get("kinds") or ())
        return Item("topic", qid, label, ", ".join(kinds), kinds=kinds)
    return None


def _is_qid(value: object) -> bool:
    return isinstance(value, str) and _QID.fullmatch(value) is not None


def _makers(work: Mapping[str, Any]) -> str:
    creators = work.get("creators") or ([work["creator"]] if work.get("creator") else [])
    return ", ".join(str(creator.get("name")) for creator in creators if isinstance(creator, Mapping) and creator.get("name"))


def _years(person: Mapping[str, Any]) -> str:
    born, died = person.get("born"), person.get("died")
    if born is not None and died is not None:
        return f"{born}–{died}"
    if born is not None:
        return f"born {born}"
    return "" if died is None else f"died {died}"


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _dicts(value: object) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _dicts(child)
