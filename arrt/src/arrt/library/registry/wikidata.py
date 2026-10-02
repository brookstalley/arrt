"""Wikidata's query service, asked the questions a `Registry` answers.

Every shape here was measured before this module existed; the measurements are
`wikidata-findings.md`. Three of them decide how it is written:

**The User-Agent is the deployment's and has no default.** Wikimedia refuses or
blocks requests without a descriptive agent and contact details, and inventing
one would misrepresent whoever runs this, the same reasoning `ARTIC_USER_AGENT`
follows. The caller passes it, and nothing here constructs one.

**The endpoint is a constant, and redirects are not followed.** Nothing a curator
or a museum wrote ever becomes a URL here, so the source-URL guard
(`security-model.md`) has nothing to check; refusing redirects outright is the
stricter half of it, and the service has never been seen to send one.

**"Visual artist" no longer sits under "artist" in Wikidata's occupation tree**, so
`people_named` filters on the occupation that does reach painters, or on having
created something at all, and not on the root that once covered both.
"""

import json
import logging
import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Final

import httpx

from arrt.library.registry import (
    QID,
    CommonsFile,
    ItemId,
    MuseumIdentifier,
    RegistryArtist,
    RegistryCreator,
    RegistryHolder,
    RegistryHolding,
    RegistryPerson,
    RegistrySimilar,
    RegistryText,
    RegistryUnavailable,
    RegistryWork,
    RegistryWorkEntry,
    RegistryWorkMatch,
)
from arrt.library.registry.identifiers import IdentifierScheme

log = logging.getLogger(__name__)

#: The query service. A constant: see the module docstring on redirects.
SPARQL_ENDPOINT: Final[str] = "https://query.wikidata.org/sparql"

#: Values per query. The service's limit is on the query's running time, not its
#: text, and a batch this size of exact-identifier lookups measured well under a
#: second; a POST body carries it, so URL length does not bound it.
BATCH: Final[int] = 200

#: Seconds. A query that has not answered in this long is one the service is
#: about to time out itself (its limit is 60 s).
TIMEOUT_SECONDS: Final[float] = 60.0


#: Visual artist (`Q3391743`): the occupation painters, sculptors and
#: photographers sit under.
_VISUAL_ARTIST: Final[str] = "Q3391743"

#: Rows one work's query may return: every combination of its creators, media,
#: collections and inventory numbers. A few dozen for a work held in two places;
#: the cap is there so an item vandalised with hundreds of statements cannot
#: make one page read thousands of rows.
_WORK_ROWS: Final[int] = 2000

#: The classes a work found by search must be an instance of, as the search
#: index's own `haswbstatement` reads them: painting, sculpture, drawing, print,
#: photograph, mural, watercolor painting, work of art, triptych, panel painting.
#: Filtering in the index rather than in SPARQL is what keeps TV series and comics,
#: which carry a creator too, out of the list in well under two seconds; a
#: subclass walk took up to a minute and kept them in (`wikidata-findings.md`).
_ARTWORK_CLASSES: Final[tuple[str, ...]] = (
    "Q3305213",
    "Q860861",
    "Q93184",
    "Q11060274",
    "Q125191",
    "Q219423",
    "Q18761202",
    "Q838948",
    "Q79218",
    "Q55439",
)

#: How many search hits are read before ranking by renown. The query service
#: otherwise pages through every hit, which took 44 s for `david`.
_SEARCHED: Final[int] = 50

#: A word the search can be given: letters and digits, with the apostrophes and
#: hyphens names carry inside them. Everything else is search syntax and is never
#: passed through from a curator: `:` and `"` and `*`, and a leading `-`, which
#: the index reads as "not". Words are also lowercased before they are sent, since
#: `AND`, `OR` and `NOT` in capitals are operators and the index ignores case.
_WORD: Final[re.Pattern[str]] = re.compile(r"^\w[\w'’-]*$")

#: Label languages, in order. `mul` is Wikidata's language-neutral label, which
#: some items (the National Gallery of Art among them) now carry instead of an
#: English one; without it their QID comes back as the name.
_LABELS: Final[str] = "en,mul"

#: Joins an artist's movements in one result. A character no movement's name holds.
_SEPARATOR: Final[str] = "\u241e"

#: The only image URLs passed on: a Commons file, by name.
_COMMONS_FILE: Final[re.Pattern[str]] = re.compile(r"^https?://commons\.wikimedia\.org/wiki/Special:FilePath/([^?#\s]+)$")


class WikidataRegistry:
    """The `Registry` over Wikidata's query service."""

    def __init__(self, *, user_agent: str, client: httpx.Client | None = None) -> None:
        self._headers = {"User-Agent": user_agent, "Accept": "application/sparql-results+json"}
        self._http = client or httpx.Client(timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=10.0), follow_redirects=False)

    def works_by_identifier(
        self, scheme: IdentifierScheme, values: Sequence[str]
    ) -> Mapping[MuseumIdentifier, frozenset[ItemId]]:
        found: dict[MuseumIdentifier, set[ItemId]] = {}
        for batch in _batches(sorted(set(values))):
            asked = set(batch)
            listed = " ".join(_literal(value) for value in batch)
            rows = self._select(f"SELECT ?id ?item WHERE {{ VALUES ?id {{ {listed} }} ?item wdt:{scheme.value} ?id . }}")
            for row in rows:
                # The answer names the identifier it matched; one that was not asked
                # about is the service's mistake, or someone else's text, and not a key.
                value = _value(row, "id")
                if value in asked:
                    found.setdefault(MuseumIdentifier(value), set()).add(_qid(row, "item"))
        return {value: frozenset(items) for value, items in found.items()}

    def creators_of(self, work_qids: Sequence[str]) -> Mapping[ItemId, frozenset[ItemId]]:
        found: dict[ItemId, set[ItemId]] = {}
        for batch in _batches(sorted({_require_qid(qid) for qid in work_qids})):
            asked = set(batch)
            listed = " ".join(f"wd:{qid}" for qid in batch)
            rows = self._select(f"SELECT ?item ?creator WHERE {{ VALUES ?item {{ {listed} }} ?item wdt:P170 ?creator . }}")
            for row in rows:
                creator = _qid(row, "creator", required=False)
                item = _qid(row, "item")
                # As in `works_by_identifier`: an item not asked about is not a key.
                if creator is not None and item in asked:
                    found.setdefault(item, set()).add(creator)
        return {item: frozenset(creators) for item, creators in found.items()}

    def people_named(self, name: str) -> Sequence[RegistryPerson]:
        rows = self._select(f"""SELECT ?item ?itemLabel (MIN(YEAR(?born)) AS ?bornYear) (MIN(YEAR(?died)) AS ?diedYear) WHERE {{
              SERVICE wikibase:mwapi {{
                bd:serviceParam wikibase:endpoint "www.wikidata.org"; wikibase:api "EntitySearch";
                  mwapi:search {_literal(name)}; mwapi:language "en" .
                ?item wikibase:apiOutputItem mwapi:item .
              }}
              ?item wdt:P31 wd:Q5 .
              FILTER EXISTS {{ {{ ?item wdt:P106/wdt:P279* wd:{_VISUAL_ARTIST} }} UNION {{ ?made wdt:P170 ?item }} }}
              OPTIONAL {{ ?item wdt:P569 ?born }}
              OPTIONAL {{ ?item wdt:P570 ?died }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}". }}
            }} GROUP BY ?item ?itemLabel""")
        return [
            RegistryPerson(
                qid=_qid(row, "item"),
                label=_value(row, "itemLabel"),
                born=_integer(row, "bornYear"),
                died=_integer(row, "diedYear"),
            )
            for row in rows
        ]

    def artist(self, qid: str, *, works: int, holdings: int, include: Sequence[str] = ()) -> RegistryArtist:
        item = _require_qid(qid)
        profile = self._select(
            f"""SELECT ?description (GROUP_CONCAT(DISTINCT ?movementLabel; separator="{_SEPARATOR}") AS ?movements) WHERE {{
              OPTIONAL {{ wd:{item} schema:description ?description FILTER(LANG(?description) = "en") }}
              OPTIONAL {{ wd:{item} wdt:P135 ?movement }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}" . ?movement rdfs:label ?movementLabel . }}
            }} GROUP BY ?description"""
        )
        named = self._select(f"""SELECT ?itemLabel (MIN(YEAR(?born)) AS ?bornYear) (MIN(YEAR(?died)) AS ?diedYear) WHERE {{
              VALUES ?item {{ wd:{item} }}
              OPTIONAL {{ ?item wdt:P569 ?born }}
              OPTIONAL {{ ?item wdt:P570 ?died }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}". }}
            }} GROUP BY ?itemLabel""")
        listed = self._select(
            f"""SELECT ?work ?workLabel ?links (MIN(YEAR(?inception)) AS ?year) (SAMPLE(?image) AS ?img) WHERE {{
              ?work wdt:P170 wd:{item} ; wikibase:sitelinks ?links .
              OPTIONAL {{ ?work wdt:P571 ?inception }}
              OPTIONAL {{ ?work wdt:P18 ?image }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}". }}
            }} GROUP BY ?work ?workLabel ?links ORDER BY DESC(?links) ?workLabel LIMIT {int(works)}"""
        )
        listed_qids = {_qid(row, "work") for row in listed}
        wanted = sorted({_require_qid(extra) for extra in include} - listed_qids)
        if wanted:
            listed = listed + self._select(
                f"""SELECT ?work ?workLabel ?links (MIN(YEAR(?inception)) AS ?year) (SAMPLE(?image) AS ?img) WHERE {{
                  VALUES ?work {{ {" ".join(f"wd:{extra}" for extra in wanted)} }}
                  ?work wikibase:sitelinks ?links .
                  OPTIONAL {{ ?work wdt:P571 ?inception }}
                  OPTIONAL {{ ?work wdt:P18 ?image }}
                  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}". }}
                }} GROUP BY ?work ?workLabel ?links ORDER BY DESC(?links) ?workLabel"""
            )
        total = self._select(f"SELECT (COUNT(DISTINCT ?work) AS ?n) WHERE {{ ?work wdt:P170 wd:{item} . }}")
        held_by = self._select(f"""SELECT ?collection ?collectionLabel (COUNT(DISTINCT ?work) AS ?n) WHERE {{
              ?work wdt:P170 wd:{item} ; wdt:P195 ?collection .
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}". }}
            }} GROUP BY ?collection ?collectionLabel ORDER BY DESC(?n) LIMIT {int(holdings)}""")
        first = profile[0] if profile else {}
        person = named[0] if named else {}
        return RegistryArtist(
            qid=item,
            name=person["itemLabel"]["value"] if "itemLabel" in person else None,
            born=_integer(person, "bornYear"),
            died=_integer(person, "diedYear"),
            description=first["description"]["value"] if "description" in first else None,
            # The label service answers a movement with no readable name with its
            # QID, which reads as a name; one with no name is left out instead.
            movements=tuple(
                name for name in first.get("movements", {}).get("value", "").split(_SEPARATOR) if name and not QID.match(name)
            ),
            works=tuple(
                RegistryWorkEntry(
                    qid=_qid(row, "work"),
                    title=_value(row, "workLabel"),
                    sitelinks=_integer(row, "links") or 0,
                    year=_integer(row, "year"),
                    image=_commons_file(row.get("img", {}).get("value")),
                )
                for row in listed
            ),
            works_total=(_integer(total[0], "n") or 0) if total else 0,
            holdings=tuple(
                RegistryHolding(qid=_qid(row, "collection"), name=_value(row, "collectionLabel"), works=_integer(row, "n") or 0)
                for row in held_by
            ),
        )

    def work(self, qid: str) -> RegistryWork | None:
        item = _require_qid(qid)
        # One query whose rows are every combination of the work's creators,
        # media, collections and inventory numbers: a single work has few of each,
        # and one round trip beats four. Read back into sets below.
        rows = self._select(f"""SELECT ?workLabel ?links ?year ?img ?creator ?creatorLabel ?mediumLabel
                   ?collection ?collectionLabel ?inventory ?inventoryAt WHERE {{
              VALUES ?work {{ wd:{item} }}
              ?work wikibase:sitelinks ?links .
              OPTIONAL {{ ?work wdt:P571 ?inception . BIND(YEAR(?inception) AS ?year) }}
              OPTIONAL {{ ?work wdt:P18 ?img }}
              OPTIONAL {{ ?work wdt:P170 ?creator }}
              OPTIONAL {{ ?work wdt:P186 ?medium }}
              OPTIONAL {{ ?work wdt:P195 ?collection }}
              OPTIONAL {{ ?work p:P217 ?numbered . ?numbered ps:P217 ?inventory .
                         OPTIONAL {{ ?numbered pq:P195 ?inventoryAt }} }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}". }}
            }} LIMIT {_WORK_ROWS}""")
        if not rows:
            return None
        creators: dict[ItemId, RegistryText] = {}
        collections: dict[ItemId, RegistryText] = {}
        numbers: set[tuple[str, ItemId | None]] = set()
        media: set[RegistryText] = set()
        years: set[int] = set()
        images: set[CommonsFile] = set()
        for row in rows:
            creator = _qid(row, "creator", required=False)
            if creator is not None:
                creators.setdefault(creator, RegistryText(_value(row, "creatorLabel")))
            collection = _qid(row, "collection", required=False)
            if collection is not None:
                collections.setdefault(collection, RegistryText(_value(row, "collectionLabel")))
            if "inventory" in row:
                numbers.add((_value(row, "inventory"), _qid(row, "inventoryAt", required=False)))
            if "mediumLabel" in row:
                media.add(RegistryText(_value(row, "mediumLabel")))
            year = _integer(row, "year")
            if year is not None:
                years.add(year)
            image = _commons_file(row.get("img", {}).get("value"))
            if image is not None:
                images.add(image)
        first = rows[0]
        return RegistryWork(
            qid=item,
            title=RegistryText(_value(first, "workLabel")),
            sitelinks=_integer(first, "links") or 0,
            year=min(years) if years else None,
            image=min(images) if images else None,
            creators=tuple(RegistryCreator(qid=qid, name=name) for qid, name in sorted(creators.items())),
            media=tuple(sorted(media)),
            holders=tuple(
                RegistryHolder(qid=qid, name=name, inventory=_inventory(qid, numbers, single=len(collections) == 1))
                for qid, name in sorted(collections.items(), key=lambda pair: pair[1])
            ),
        )

    def works_matching(self, words: Sequence[str], *, prefix: bool, limit: int) -> Sequence[RegistryWorkMatch]:
        plain = [word.lower() for word in words if _WORD.match(word)]
        if not plain:
            return []
        text = " ".join(plain) + ("*" if prefix else "")
        classes = "|".join(f"P31={qid}" for qid in _ARTWORK_CLASSES)
        rows = self._select(f"""SELECT ?item ?itemLabel ?links (SAMPLE(?image) AS ?img)
                   (SAMPLE(?maker) AS ?creator) (SAMPLE(?makerLabel) AS ?creatorLabel) WHERE {{
              SERVICE wikibase:mwapi {{
                bd:serviceParam wikibase:endpoint "www.wikidata.org"; wikibase:api "Search";
                  mwapi:srsearch {_literal(f"{text} haswbstatement:{classes}")}; mwapi:srlimit "{_SEARCHED}";
                  wikibase:limit {_SEARCHED} .
                ?item wikibase:apiOutputItem mwapi:title .
              }}
              ?item wikibase:sitelinks ?links .
              OPTIONAL {{ ?item wdt:P18 ?image }}
              OPTIONAL {{ ?item wdt:P170 ?maker }}
              SERVICE wikibase:label {{
                bd:serviceParam wikibase:language "{_LABELS}" .
                ?item rdfs:label ?itemLabel . ?maker rdfs:label ?makerLabel .
              }}
            }} GROUP BY ?item ?itemLabel ?links ORDER BY DESC(?links) ?itemLabel LIMIT {int(limit)}""")
        found = []
        for row in rows:
            # The maker's name comes from the label service, as every other name
            # here does: it prefers `en` to `mul`, where a label filter accepting
            # both handed SAMPLE whichever it met first ("Pieter Bruegel" one
            # time, "Pieter Brueghel the Elder" the next).
            maker = _qid(row, "creator", required=False)
            found.append(
                RegistryWorkMatch(
                    qid=_qid(row, "item"),
                    title=RegistryText(_value(row, "itemLabel")),
                    sitelinks=_integer(row, "links") or 0,
                    image=_commons_file(row.get("img", {}).get("value")),
                    creator=None if maker is None else RegistryCreator(qid=maker, name=RegistryText(_value(row, "creatorLabel"))),
                )
            )
        return found

    def similar_to(self, qid: str, *, limit: int) -> Sequence[RegistrySimilar]:
        item = _require_qid(qid)
        # Ranked by renown, not by how many movements are shared: the second put
        # four painters few have heard of ahead of Picasso for van Gogh. Visual
        # artists only, which drops critics and keeps those Wikidata also calls
        # painters (`wikidata-findings.md`).
        rows = self._select(f"""SELECT ?other ?otherLabel ?links (MIN(YEAR(?b)) AS ?born) (MIN(YEAR(?d)) AS ?died) WHERE {{
              wd:{item} wdt:P135 ?movement .
              ?other wdt:P135 ?movement ; wdt:P31 wd:Q5 ; wikibase:sitelinks ?links .
              FILTER(?other != wd:{item})
              FILTER EXISTS {{ ?other wdt:P106/wdt:P279* wd:{_VISUAL_ARTIST} }}
              OPTIONAL {{ ?other wdt:P569 ?b }}
              OPTIONAL {{ ?other wdt:P570 ?d }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}" . ?other rdfs:label ?otherLabel . }}
            }} GROUP BY ?other ?otherLabel ?links ORDER BY DESC(?links) ?otherLabel LIMIT {int(limit)}""")
        people = [(_qid(row, "other"), row) for row in rows]
        if not people:
            return []
        listed = " ".join(f"wd:{person}" for person, _ in people)
        seen = self._select(f"""SELECT ?person (COUNT(DISTINCT ?work) AS ?n) WHERE {{
              VALUES ?person {{ {listed} }}
              ?work wdt:P170 ?person ; wdt:P18 ?image .
            }} GROUP BY ?person""")
        images = {_qid(row, "person"): _integer(row, "n") or 0 for row in seen}
        return [
            RegistrySimilar(
                qid=person,
                name=RegistryText(_value(row, "otherLabel")),
                sitelinks=_integer(row, "links") or 0,
                born=_integer(row, "born"),
                died=_integer(row, "died"),
                images=images.get(person, 0),
            )
            for person, row in people
        ]

    def close(self) -> None:
        self._http.close()

    def _select(self, query: str) -> list[Mapping[str, Any]]:
        """Run one SELECT and return its bindings, or say why it could not be run."""
        try:
            response = self._http.post(SPARQL_ENDPOINT, data={"query": query}, headers=self._headers)
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"Wikidata could not be reached: {exc}") from exc
        if response.status_code != 200:
            # A redirect lands here too, deliberately: see the module docstring.
            raise RegistryUnavailable(f"Wikidata answered HTTP {response.status_code}.")
        try:
            bindings = response.json()["results"]["bindings"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RegistryUnavailable("Wikidata's answer was not the JSON results shape it documents.") from exc
        if not isinstance(bindings, list):
            raise RegistryUnavailable("Wikidata's answer carried no list of results.")
        return bindings


def _inventory(collection: ItemId, numbers: set[tuple[str, ItemId | None]], *, single: bool) -> RegistryText | None:
    """The number this collection gives the work: the one qualified with it, or an unqualified one if it is the only holder."""
    for number, at in sorted(numbers, key=lambda pair: pair[0]):
        if at == collection or (at is None and single):
            return RegistryText(number)
    return None


def _batches(values: Sequence[str]) -> Iterator[Sequence[str]]:
    for start in range(0, len(values), BATCH):
        yield values[start : start + BATCH]


def _literal(text: str) -> str:
    """`text` as a SPARQL string literal: quoted, with what could end it escaped."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    return f'"{escaped}"'


def _require_qid(qid: str) -> str:
    if not QID.match(qid):
        raise ValueError(f"{qid!r} is not a Wikidata item id.")
    return qid


def _value(row: Mapping[str, Any], name: str) -> str:
    try:
        return str(row[name]["value"])
    except (KeyError, TypeError) as exc:
        raise RegistryUnavailable(f"A Wikidata result had no {name!r}.") from exc


def _qid(row: Mapping[str, Any], name: str, *, required: bool = True) -> ItemId | None:
    """The QID at the end of an entity URI, or None for a value that is not an item (an unknown creator)."""
    if not required and name not in row:
        return None
    candidate = _value(row, name).rsplit("/", 1)[-1]
    if QID.match(candidate):
        return ItemId(candidate)
    if required:
        raise RegistryUnavailable(f"A Wikidata result's {name!r} was not an item: {candidate!r}.")
    return None


def _commons_file(url: str | None) -> CommonsFile | None:
    """A Commons file URL, made `https`, or None for anything else the registry offered as an image."""
    found = _COMMONS_FILE.match(url or "")
    return None if found is None else CommonsFile(f"https://commons.wikimedia.org/wiki/Special:FilePath/{found.group(1)}")


def _integer(row: Mapping[str, Any], name: str) -> int | None:
    if name not in row:
        return None
    try:
        return int(float(_value(row, name)))
    except ValueError:
        return None
