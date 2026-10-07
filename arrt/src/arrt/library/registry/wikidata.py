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

**A topic's kind is read from the classes above it, in Python, not asked of the
service.** Asking whether an item sits under *visual artwork* walked the class
tree downwards from the root and took three to fourteen seconds; asking for the
item's own ancestors among a handful of roots takes half a second
(`wikidata-findings.md` § Topics).
"""

import json
import logging
import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Final
from urllib.parse import quote, unquote, urlsplit

import httpx

from arrt.library.registry import (
    QID,
    RASTER_TYPES,
    CommonsFile,
    ItemId,
    MuseumIdentifier,
    RegistryArtist,
    RegistryCreator,
    RegistryHolder,
    RegistryHolding,
    RegistryImageSize,
    RegistryPerson,
    RegistrySimilar,
    RegistryText,
    RegistryTopic,
    RegistryTopicRef,
    RegistryTopicsOf,
    RegistryTopicWork,
    RegistryUnavailable,
    RegistryWork,
    RegistryWorkEntry,
    RegistryWorkMatch,
    TopicKind,
    WorkPage,
)
from arrt.library.registry.identifiers import IdentifierScheme

log = logging.getLogger(__name__)

#: The query service. A constant: see the module docstring on redirects.
SPARQL_ENDPOINT: Final[str] = "https://query.wikidata.org/sparql"

#: Where a Commons file's own facts are asked: the registry names the file, and
#: only Commons knows how big it is. A constant, asked with no redirect followed,
#: for the same reason as the query service (see the module docstring). The
#: Commons image source asks the same endpoint; a source may read the registry,
#: never the reverse, so each holds its own copy of the address.
COMMONS_API: Final[str] = "https://commons.wikimedia.org/w/api.php"

#: The parts a measurement can be qualified with that surround a work rather
#: than being it: frame, framed, mount. The others (canvas above all, then
#: supports, panels, sheets) are the work itself, as measured in
#: `wikidata-findings.md` § A work's size.
_AROUND: Final[str] = "wd:Q860792, wd:Q101698846, wd:Q107105674"

#: Seconds to wait for Commons to size a picture. It answers in a fraction of a
#: second, and a page waits on it, so an outage costs a visit this rather than
#: the query service's own allowance.
COMMONS_TIMEOUT_SECONDS: Final[float] = 5.0

#: Values per query. The service's limit is on the query's running time, not its
#: text, and a batch this size of exact-identifier lookups measured well under a
#: second; a POST body carries it, so URL length does not bound it.
BATCH: Final[int] = 200

#: Seconds. A query that has not answered in this long is one the service is
#: about to time out itself (its limit is 60 s). For the hand-run matcher, which
#: nobody is waiting on.
TIMEOUT_SECONDS: Final[float] = 60.0

#: Seconds, for the server's pages, where a curator is waiting and a stalled
#: query holds one of the workers the library's own requests share. The slowest
#: artist or work page query measured was 7.4 s (Renoir's similar artists,
#: `wikidata-findings.md`); past this the page says Wikidata could not be asked,
#: and the next visit asks again. A topic's works and artists are the exception
#: (`SECTION_TIMEOUT_SECONDS`).
INTERACTIVE_TIMEOUT_SECONDS: Final[float] = 20.0

#: Seconds, for the two questions a Topic page asks after it has drawn: its
#: works and its artists. A named period's took 26-60 s when measured
#: (`wikidata-findings.md` § Topics), so at the pages' 20 s they could never
#: answer, and a failure is never kept, so they never would. Given the service's
#: own limit instead, a period is slow once and then kept for a week. Nothing
#: waits on these but the section that asked.
SECTION_TIMEOUT_SECONDS: Final[float] = TIMEOUT_SECONDS


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

#: The classes a period is an instance of, directly or through a subclass:
#: century, decade, historical period. Being one is the only way to be a period.
_PERIOD_CLASSES: Final[frozenset[str]] = frozenset({"Q578", "Q39911", "Q11514315"})

#: The classes a movement is an instance of: art movement, art style. Read as
#: instances only: *woodcut print* is a subclass of *art style*, and a medium.
_MOVEMENT_CLASSES: Final[frozenset[str]] = frozenset({"Q968159", "Q1792644"})

#: Visual artwork (`Q4502142`): a medium is a subclass of it.
_VISUAL_ARTWORK: Final[str] = "Q4502142"

#: Century (`Q578`): the one period a held work's facts name.
_CENTURY: Final[str] = "Q578"

#: Millennium (`Q36507`). The Gregorian centuries are each part of one; the
#: Islamic calendar's are centuries too, with years of their own, and are not.
_MILLENNIUM: Final[str] = "Q36507"

#: When an item has more than one kind, the one its works are found by. A
#: movement's works are its artists', which is what a curator browsing Baroque
#: means; the same item's period would be everything made in 160 years.
_KIND_ORDER: Final[tuple[TopicKind, ...]] = (TopicKind.MOVEMENT, TopicKind.PERIOD, TopicKind.MEDIUM, TopicKind.SUBJECT)

#: How many search hits a topic search reads, as the search ranks them.
_TOPICS_SEARCHED: Final[int] = 20

#: Rows one item's pages may return. A famous painting carries a few dozen
#: identifiers; the cap is there for the same reason `_WORK_ROWS` is.
_PAGE_ROWS: Final[int] = 500

#: Rows a work's creators' names may return: one per name per language. Canaletto
#: alone takes 266 rows (172 distinct names, measured 2026-10-06), and a work by
#: a workshop names several people. A cap that truncates leaves a name out, which
#: refuses.
_NAME_ROWS: Final[int] = 5000

#: The characters an identifier keeps when it is put into a formatter URL, as
#: Wikibase's own `wfUrlencode` keeps them; everything else is percent-encoded, so
#: `fr:La_Persistance_de_la_mémoire` arrives as a URL and not as text.
_FORMATTER_SAFE: Final[str] = ";:@$!*(),/~"

#: The longest page URL kept. Past this it is not an address anyone typed.
_PAGE_URL_MAX: Final[int] = 2048

#: The only image URLs passed on: a Commons file, by name.
_COMMONS_FILE: Final[re.Pattern[str]] = re.compile(r"^https?://commons\.wikimedia\.org/wiki/Special:FilePath/([^?#\s]+)$")


class WikidataRegistry:
    """The `Registry` over Wikidata's query service."""

    def __init__(self, *, user_agent: str, client: httpx.Client | None = None, timeout: float = TIMEOUT_SECONDS) -> None:
        self._headers = {"User-Agent": user_agent, "Accept": "application/sparql-results+json"}
        self._http = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0), follow_redirects=False)

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
        rows = self._select(
            f"""SELECT ?item ?itemLabel ?links (MIN(YEAR(?born)) AS ?bornYear) (MIN(YEAR(?died)) AS ?diedYear) WHERE {{
              SERVICE wikibase:mwapi {{
                bd:serviceParam wikibase:endpoint "www.wikidata.org"; wikibase:api "EntitySearch";
                  mwapi:search {_literal(name)}; mwapi:language "en" .
                ?item wikibase:apiOutputItem mwapi:item .
              }}
              ?item wdt:P31 wd:Q5 ; wikibase:sitelinks ?links .
              FILTER EXISTS {{ {{ ?item wdt:P106/wdt:P279* wd:{_VISUAL_ARTIST} }} UNION {{ ?made wdt:P170 ?item }} }}
              OPTIONAL {{ ?item wdt:P569 ?born }}
              OPTIONAL {{ ?item wdt:P570 ?died }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}". }}
            }} GROUP BY ?item ?itemLabel ?links ORDER BY DESC(?links) ?itemLabel"""
        )
        # By renown, as the work search is: a caller that keeps the first few
        # (the typeahead keeps three) keeps the famous one, not a namesake. The
        # sort key is selected as well as grouped by: the query service ignored
        # an ORDER BY on a grouped key it was not asked to return (measured
        # 2026-10-01: "dali" put Dalibor Chatrný, 4 sitelinks, before Dalí, 247).
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
                   ?collection ?collectionLabel ?inventory ?inventoryAt ?height ?width WHERE {{
              VALUES ?work {{ wd:{item} }}
              ?work wikibase:sitelinks ?links .
              OPTIONAL {{ ?work wdt:P571 ?inception . BIND(YEAR(?inception) AS ?year) }}
              OPTIONAL {{ ?work wdt:P18 ?img }}
              OPTIONAL {{ ?work wdt:P170 ?creator }}
              OPTIONAL {{ ?work wdt:P186 ?medium }}
              OPTIONAL {{ ?work wdt:P195 ?collection }}
              OPTIONAL {{ ?work p:P217 ?numbered . ?numbered ps:P217 ?inventory .
                         OPTIONAL {{ ?numbered pq:P195 ?inventoryAt }} }}
              {_measured("P2048", "height")}
              {_measured("P2049", "width")}
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
            height_cm=_centimetres(rows, "height"),
            width_cm=_centimetres(rows, "width"),
        )

    def image_size(self, image: CommonsFile) -> RegistryImageSize | None:
        found = _COMMONS_FILE.match(image)
        if found is None:
            raise ValueError(f"{image!r} is not a Commons file path.")
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "prop": "imageinfo",
            "iiprop": "size|mime",
            "titles": f"File:{unquote(found.group(1))}",
        }
        try:
            response = self._http.get(
                COMMONS_API,
                params=params,
                headers={**self._headers, "Accept": "application/json"},
                timeout=httpx.Timeout(COMMONS_TIMEOUT_SECONDS),
            )
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"Commons could not be reached: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            # A redirect lands here too, as it does for the query service.
            raise RegistryUnavailable(f"Commons answered HTTP {response.status_code}.")
        try:
            page = response.json()["query"]["pages"][0]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise RegistryUnavailable("Commons' answer was not the imageinfo shape it documents.") from exc
        if isinstance(page, Mapping) and page.get("missing"):
            return None
        infos = page.get("imageinfo") if isinstance(page, Mapping) else None
        info = infos[0] if isinstance(infos, list) and infos and isinstance(infos[0], Mapping) else None
        if info is None:
            raise RegistryUnavailable("Commons described the file in a shape it does not document.")
        if info.get("mime") not in RASTER_TYPES:
            return None
        width, height = info.get("width"), info.get("height")
        # Only `missing` says there is no such file; a picture Commons gives no
        # size for is an answer not understood, not a file without one.
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise RegistryUnavailable("Commons described a picture without its size.")
        return RegistryImageSize(width=width, height=height)

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

    def label_of(self, qid: str) -> RegistryText | None:
        item = _require_qid(qid)
        # `wikibase:sitelinks` is on every item that exists and on nothing else,
        # so a missing item gives no row where the label service alone would
        # still answer with the QID.
        rows = self._select(f"""SELECT ?itemLabel WHERE {{
              VALUES ?item {{ wd:{item} }}
              ?item wikibase:sitelinks ?links .
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}" . ?item rdfs:label ?itemLabel . }}
            }}""")
        return RegistryText(_value(rows[0], "itemLabel")) if rows else None

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
        return self._with_images([(_qid(row, "other"), row) for row in rows], "otherLabel")

    def topic(self, qid: str) -> RegistryTopic | None:
        item = _require_qid(qid)
        # `wikibase:sitelinks` is on every item that exists, so a missing item
        # gives no row (as in `label_of`).
        rows = self._select(f"""SELECT ?item ?itemLabel ?description ?start ?end ?via ?root WHERE {{
              VALUES ?item {{ wd:{item} }}
              ?item wikibase:sitelinks ?links .
              OPTIONAL {{ ?item schema:description ?description FILTER(LANG(?description) = "en") }}
              {_TOPIC_FACTS}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}" . ?item rdfs:label ?itemLabel . }}
            }} LIMIT {_WORK_ROWS}""")
        return _topic(item, rows) if rows else None

    def topic_works(self, topic: RegistryTopic, *, limit: int) -> Sequence[RegistryTopicWork]:
        where = _works_in(topic)
        if where is None:
            return []
        # The most renowned works are chosen first and named after: the label
        # service and the optional facts, run over every work in a century, are
        # what would make this slow. One row per work, however many made it.
        rows = self._select(
            f"""SELECT ?work ?workLabel ?links (MIN(YEAR(?inception)) AS ?year) (SAMPLE(?image) AS ?img) WHERE {{
              {{ SELECT DISTINCT ?work ?links WHERE {{
                  {where}
                  ?work wikibase:sitelinks ?links .
                }} ORDER BY DESC(?links) STR(?work) LIMIT {int(limit)} }}
              OPTIONAL {{ ?work wdt:P571 ?inception }}
              OPTIONAL {{ ?work wdt:P18 ?image }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}" . ?work rdfs:label ?workLabel . }}
            }} GROUP BY ?work ?workLabel ?links ORDER BY DESC(?links) ?workLabel""",
            timeout=SECTION_TIMEOUT_SECONDS,
        )
        works = [(_qid(row, "work"), row) for row in rows]
        if not works:
            return []
        made = self._select(f"""SELECT ?work ?maker ?makerLabel WHERE {{
              VALUES ?work {{ {" ".join(f"wd:{work}" for work, _ in works)} }}
              ?work wdt:P170 ?maker .
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}" . ?maker rdfs:label ?makerLabel . }}
            }}""")
        makers: dict[ItemId, dict[ItemId, RegistryText]] = {}
        unknown: set[ItemId] = set()
        for row in made:
            work = _qid(row, "work")
            maker = _qid(row, "maker", required=False)
            if maker is None:
                # "Somebody, unknown": a blank node, whose URL is nobody's name.
                unknown.add(work)
            else:
                makers.setdefault(work, {}).setdefault(maker, RegistryText(_value(row, "makerLabel")))
        return [
            RegistryTopicWork(
                qid=work,
                title=RegistryText(_value(row, "workLabel")),
                sitelinks=_integer(row, "links") or 0,
                year=_integer(row, "year"),
                image=_commons_file(row.get("img", {}).get("value")),
                creators=tuple(RegistryCreator(qid=qid, name=name) for qid, name in sorted(makers.get(work, {}).items())),
                creator_unknown=work in unknown,
            )
            for work, row in works
        ]

    def topic_artists(self, topic: RegistryTopic, *, limit: int) -> Sequence[RegistrySimilar]:
        # Ranked by the fame of their works in the topic, the sum of those works'
        # sitelinks, the artist's own breaking ties. Ranked by the artist's own
        # fame, Benjamin Franklin led woodcut for *Join, or Die* and Adolf Hitler
        # led watercolour; by how many works, whoever has an item per work led,
        # Philip Galle the 16th century and Leonardo out (`wikidata-findings.md`
        # § Topics).
        if topic.kind is TopicKind.MOVEMENT:
            # A movement's own artists (`P135` sits on people, not works), visual
            # artists only, as `similar_to` keeps them, and its works are theirs.
            # One with no work of visual art recorded is still the movement's.
            made = f"""?artist wdt:P135 wd:{_require_qid(topic.qid)} ; wdt:P31 wd:Q5 ; wikibase:sitelinks ?links .
                      FILTER EXISTS {{ ?artist wdt:P106/wdt:P279* wd:{_VISUAL_ARTIST} }}
                      OPTIONAL {{ ?work wdt:P170 ?artist . {_ARTWORK} ?work wikibase:sitelinks ?workLinks . }}"""
        else:
            where = _works_in(topic)
            if where is None:
                return []
            made = f"""{where}
                      ?work wdt:P170 ?artist ; wikibase:sitelinks ?workLinks .
                      ?artist wdt:P31 wd:Q5 ; wikibase:sitelinks ?links ."""
        # Each work once per artist before it is summed: a work reached twice (two
        # of the ten classes, depicting and of the genre, two inceptions) would
        # otherwise count its fame twice. An artist with no work sums to nought.
        # How many works is asked too, so an answer shows what the fame outranked.
        rows = self._select(
            f"""SELECT ?artist ?artistLabel ?links ?fame ?works (MIN(YEAR(?b)) AS ?born) (MIN(YEAR(?d)) AS ?died)
            WHERE {{
              {{ SELECT ?artist ?links (SUM(COALESCE(?workLinks, 0)) AS ?fame) (COUNT(?work) AS ?works) WHERE {{
                  {{ SELECT DISTINCT ?artist ?links ?work ?workLinks WHERE {{
                      {made}
                  }} }}
                }} GROUP BY ?artist ?links ORDER BY DESC(?fame) DESC(?links) STR(?artist) LIMIT {int(limit)} }}
              OPTIONAL {{ ?artist wdt:P569 ?b }}
              OPTIONAL {{ ?artist wdt:P570 ?d }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}" . ?artist rdfs:label ?artistLabel . }}
            }} GROUP BY ?artist ?artistLabel ?links ?fame ?works""",
            timeout=SECTION_TIMEOUT_SECONDS,
        )
        people = [(_qid(row, "artist"), row) for row in rows]
        # The service chose them in this order, and the grouping around the
        # choice promises none, so the order is put back here.
        people.sort(key=lambda person: (-(_integer(person[1], "fame") or 0), -(_integer(person[1], "links") or 0), person[0]))
        return self._with_images(people, "artistLabel")

    def topics_named(self, text: str) -> Sequence[RegistryTopic]:
        # A subject is anything else, so the kinds alone would offer every hit:
        # a hit with no kind of its own is kept only if something depicts it or
        # has it as its genre. That is what drops the French political party
        # *Renaissance*, which the search ranks first. Asking for a work of
        # visual art in particular took seconds for *still life* and dropped
        # nothing more (`wikidata-findings.md` § Topics). A movement is kept only
        # if some work of visual art has a maker in it, which drops
        # *impressionism in music*, whose page would list no works. Baroque
        # music stays: composers who also drew name it as their movement.
        rows = self._select(f"""SELECT ?item ?itemLabel ?description ?links ?start ?end ?via ?root ?depicted ?followed WHERE {{
              SERVICE wikibase:mwapi {{
                bd:serviceParam wikibase:endpoint "www.wikidata.org"; wikibase:api "EntitySearch";
                  mwapi:search {_literal(text)}; mwapi:language "en"; mwapi:limit "{_TOPICS_SEARCHED}";
                  wikibase:limit {_TOPICS_SEARCHED} .
                ?item wikibase:apiOutputItem mwapi:item .
              }}
              ?item wikibase:sitelinks ?links .
              OPTIONAL {{ ?item schema:description ?description FILTER(LANG(?description) = "en") }}
              {_TOPIC_FACTS}
              BIND(EXISTS {{ ?work wdt:P180|wdt:P136 ?item }} AS ?depicted)
              BIND(EXISTS {{ ?maker wdt:P135 ?item . ?work wdt:P170 ?maker . {_ARTWORK} }} AS ?followed)
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{_LABELS}" . ?item rdfs:label ?itemLabel . }}
            }} ORDER BY DESC(?links) ?itemLabel""")
        grouped: dict[ItemId, list[Mapping[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(_qid(row, "item"), []).append(row)
        found = []
        for item, its in grouped.items():
            if any(_is_work(row) for row in its):
                # A work is not a topic to browse, whatever its class makes it:
                # Kunisada's woodcut print *Woodcut* read as a movement, because
                # *woodcut print* is a subclass of *art style*.
                continue
            topic = _topic(item, its)
            # Dropped only when the service says no: any other answer is not the
            # service's to give, and the hit is kept.
            if topic.kind is TopicKind.SUBJECT and _said_no(its[0], "depicted"):
                continue
            if topic.kind is TopicKind.MOVEMENT and _said_no(its[0], "followed"):
                continue
            found.append(topic)
        return found

    def topics_of(self, work_qids: Sequence[str], artist_qids: Sequence[str]) -> RegistryTopicsOf:
        # Each route binds its own variable, so a topic's kind is the route that
        # reached it and never a string read back from the answer.
        works: dict[ItemId, set[RegistryTopicRef]] = {}
        for batch in _batches(sorted({_require_qid(qid) for qid in work_qids})):
            # A work's century is the Gregorian century item whose years hold
            # its inception's (two, where the registry's centuries before 1000
            # overlap by a year); its kind of work is a class it is an instance
            # of that sits under visual artwork (painting, woodcut print).
            rows = self._select(f"""SELECT ?item ?period ?periodLabel ?subject ?subjectLabel ?medium ?mediumLabel WHERE {{
                  VALUES ?item {{ {" ".join(f"wd:{qid}" for qid in batch)} }}
                  {{ ?item wdt:P571 ?inception .
                     ?period wdt:P31 wd:{_CENTURY} ; wdt:P361/wdt:P31 wd:{_MILLENNIUM} ; wdt:P580 ?s ; wdt:P582 ?e .
                     FILTER(YEAR(?inception) >= YEAR(?s) && YEAR(?inception) <= YEAR(?e)) }}
                  UNION {{ ?item wdt:P180|wdt:P136 ?subject }}
                  UNION {{ ?item wdt:P31 ?medium . ?medium wdt:P279* ?root . FILTER(?root IN (wd:{_VISUAL_ARTWORK})) }}
                  SERVICE wikibase:label {{
                    bd:serviceParam wikibase:language "{_LABELS}" .
                    ?period rdfs:label ?periodLabel . ?subject rdfs:label ?subjectLabel . ?medium rdfs:label ?mediumLabel .
                  }}
                }}""")
            _collect(rows, set(batch), works, _WORK_ROUTES)
        artists: dict[ItemId, set[RegistryTopicRef]] = {}
        for batch in _batches(sorted({_require_qid(qid) for qid in artist_qids})):
            rows = self._select(f"""SELECT ?item ?movement ?movementLabel WHERE {{
                  VALUES ?item {{ {" ".join(f"wd:{qid}" for qid in batch)} }}
                  ?item wdt:P135 ?movement .
                  SERVICE wikibase:label {{
                    bd:serviceParam wikibase:language "{_LABELS}" . ?movement rdfs:label ?movementLabel .
                  }}
                }}""")
            _collect(rows, set(batch), artists, {"movement": TopicKind.MOVEMENT})
        return RegistryTopicsOf(works=_sorted_refs(works), artists=_sorted_refs(artists))

    def pages_about(self, qid: str) -> Sequence[WorkPage]:
        item = _require_qid(qid)
        # Two kinds of statement give a page: an external identifier, put into
        # its property's formatter URL (MoMA's P2014 and
        # `https://www.moma.org/collection/works/$1`), and "described at URL"
        # (P973), which is a URL already. Measured 2026-10-03 on four corpus items
        # (`build-plan-source-plugins.md` Chunk 03).
        rows = self._select(f"""SELECT ?prop ?value ?formatter ?described WHERE {{
              {{ wd:{item} ?direct ?value .
                 ?prop wikibase:directClaim ?direct ; wikibase:propertyType wikibase:ExternalId ; wdt:P1630 ?formatter . }}
              UNION {{ wd:{item} wdt:P973 ?described . }}
            }} LIMIT {_PAGE_ROWS}""")
        pages: set[WorkPage] = set()
        for row in rows:
            described = row.get("described", {}).get("value")
            formatter, value = row.get("formatter", {}).get("value"), row.get("value", {}).get("value")
            if isinstance(described, str):
                page = _work_page(described)
            elif isinstance(formatter, str) and isinstance(value, str) and "$1" in formatter:
                page = _work_page(formatter.replace("$1", quote(value, safe=_FORMATTER_SAFE)))
            else:
                # A formatter with nowhere to put the identifier names no page.
                page = None
            if page is not None:
                pages.add(page)
        return sorted(pages)

    def creator_names(self, qid: str) -> Mapping[ItemId, frozenset[RegistryText]]:
        item = _require_qid(qid)
        rows = self._select(f"""SELECT ?creator ?name WHERE {{
              wd:{item} wdt:P170 ?creator .
              {{ ?creator rdfs:label ?name }} UNION {{ ?creator skos:altLabel ?name }}
            }} LIMIT {_NAME_ROWS}""")
        names: dict[ItemId, set[RegistryText]] = {}
        for row in rows:
            # An unknown creator is a blank node, not an item: it has no names to compare.
            creator = _qid(row, "creator", required=False)
            name = row.get("name", {}).get("value")
            if creator is not None and isinstance(name, str) and name.strip():
                names.setdefault(creator, set()).add(RegistryText(name))
        return {creator: frozenset(written) for creator, written in names.items()}

    def close(self) -> None:
        self._http.close()

    def _with_images(self, people: Sequence[tuple[ItemId, Mapping[str, Any]]], label: str) -> list[RegistrySimilar]:
        """People listed, each with a count of their works that have a free image: one more question, or none for nobody."""
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
                name=RegistryText(_value(row, label)),
                sitelinks=_integer(row, "links") or 0,
                born=_integer(row, "born"),
                died=_integer(row, "died"),
                images=images.get(person, 0),
            )
            for person, row in people
        ]

    def _select(self, query: str, *, timeout: float | None = None) -> list[Mapping[str, Any]]:
        """Run one SELECT and return its bindings, or say why it could not be run.

        `timeout` overrides the client's for this one question; none keeps it.
        """
        extra = {} if timeout is None else {"timeout": httpx.Timeout(timeout, connect=10.0)}
        try:
            response = self._http.post(SPARQL_ENDPOINT, data={"query": query}, headers=self._headers, **extra)
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"Wikidata could not be reached: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            # A redirect lands here too, deliberately: see the module docstring.
            raise RegistryUnavailable(f"Wikidata answered HTTP {response.status_code}.")
        try:
            bindings = response.json()["results"]["bindings"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RegistryUnavailable("Wikidata's answer was not the JSON results shape it documents.") from exc
        if not isinstance(bindings, list):
            raise RegistryUnavailable("Wikidata's answer carried no list of results.")
        return bindings


#: A topic's facts beyond its name: its years, and which of the kind roots sit
#: above it, by instance (`P31`) or by subclass (`P279`). The roots are asked for
#: by name from the item upwards; see the module docstring on why.
_ROOTS: Final[str] = ", ".join(f"wd:{qid}" for qid in sorted(_PERIOD_CLASSES | _MOVEMENT_CLASSES | {_VISUAL_ARTWORK}))
_TOPIC_FACTS: Final[str] = f"""OPTIONAL {{ ?item wdt:P580 ?s . BIND(YEAR(?s) AS ?start) }}
              OPTIONAL {{ ?item wdt:P582 ?e . BIND(YEAR(?e) AS ?end) }}
              OPTIONAL {{
                {{ ?item wdt:P31/wdt:P279* ?root . BIND("P31" AS ?via) }} UNION {{ ?item wdt:P279* ?root . BIND("P279" AS ?via) }}
                FILTER(?root IN ({_ROOTS}))
              }}"""


def _topic(item: ItemId, rows: Sequence[Mapping[str, Any]]) -> RegistryTopic:
    """One topic from the rows its facts arrived as: every combination of its years and the roots above it."""
    instance_of: set[str] = set()
    subclass_of: set[str] = set()
    starts: set[int] = set()
    ends: set[int] = set()
    for row in rows:
        root = _qid(row, "root", required=False)
        if root is not None:
            (instance_of if row.get("via", {}).get("value") == "P31" else subclass_of).add(root)
        start, end = _integer(row, "start"), _integer(row, "end")
        if start is not None:
            starts.add(start)
        if end is not None:
            ends.add(end)
    found = set()
    # A start and an end alone make nothing a period: they let in exhibitions, a
    # war and *16th-century clothing*, and made Romanticism one. Every period a
    # person named is an instance of a period class (`wikidata-findings.md` § Topics).
    if instance_of & _PERIOD_CLASSES:
        found.add(TopicKind.PERIOD)
    if instance_of & _MOVEMENT_CLASSES:
        found.add(TopicKind.MOVEMENT)
    if _VISUAL_ARTWORK in subclass_of:
        found.add(TopicKind.MEDIUM)
    first = rows[0]
    return RegistryTopic(
        qid=item,
        label=RegistryText(_value(first, "itemLabel")),
        kinds=tuple(kind for kind in _KIND_ORDER if kind in found) or (TopicKind.SUBJECT,),
        description=RegistryText(_value(first, "description")) if "description" in first else None,
        # The widest span its statements give: a period recorded twice is the
        # whole of both.
        start=min(starts) if starts else None,
        end=max(ends) if ends else None,
    )


def _said_no(row: Mapping[str, Any], name: str) -> bool:
    """Whether the service answered a yes-or-no question in `row` with no: a missing or other answer is not a no."""
    return row.get(name, {}).get("value") == "false"


def _is_work(row: Mapping[str, Any]) -> bool:
    """Whether a row of a topic's facts says it is an instance of visual artwork: a work, not a topic."""
    return row.get("via", {}).get("value") == "P31" and _qid(row, "root", required=False) == _VISUAL_ARTWORK


#: Binds `?work` to a work of visual art: an instance of one of the ten classes.
_ARTWORK: Final[str] = f"?work wdt:P31 ?class . VALUES ?class {{ {' '.join(f'wd:{qid}' for qid in _ARTWORK_CLASSES)} }}"


def _works_in(topic: RegistryTopic) -> str | None:
    """The pattern binding `?work` to the topic's works of visual art, by its kind; None for a period with no years."""
    item = _require_qid(topic.qid)
    match topic.kind:
        case TopicKind.MOVEMENT:
            # `P135` sits on artists, not works (`wikidata-findings.md` § Topics).
            return f"?maker wdt:P135 wd:{item} . ?work wdt:P170 ?maker . {_ARTWORK}"
        case TopicKind.PERIOD:
            if topic.start is None or topic.end is None:
                return None
            # Read as a range of the inception index, which the hint allows. A
            # filter on YEAR() over the works of art timed out at a minute for
            # the 16th century; the range answered in 7 to 26 seconds for a
            # century, a decade and the Dutch Golden Age, and still took 50 s or
            # more for the Belle Époque and the Edo period (`wikidata-findings.md`).
            return (
                "?work wdt:P571 ?made . hint:Prior hint:rangeSafe true . "
                f"FILTER(?made >= {_instant(topic.start)} && ?made < {_instant(topic.end + 1)}) {_ARTWORK}"
            )
        case TopicKind.MEDIUM:
            # A kind of work is itself the class, and is often not one of the ten.
            return f"?work wdt:P31 wd:{item} ."
        case TopicKind.SUBJECT:
            return f"{{ ?work wdt:P180 wd:{item} }} UNION {{ ?work wdt:P136 wd:{item} }} {_ARTWORK}"


def _instant(year: int) -> str:
    """The first moment of `year` as a SPARQL dateTime, the form the inception index holds."""
    year = int(year)
    return f'"{"-" if year < 0 else ""}{abs(year):04d}-01-01T00:00:00Z"^^xsd:dateTime'


#: The variables `topics_of` binds for a work, and the kind each route gives.
_WORK_ROUTES: Final[Mapping[str, TopicKind]] = {
    "period": TopicKind.PERIOD,
    "subject": TopicKind.SUBJECT,
    "medium": TopicKind.MEDIUM,
}


def _collect(
    rows: Sequence[Mapping[str, Any]],
    asked: set[str],
    into: dict[ItemId, set[RegistryTopicRef]],
    routes: Mapping[str, TopicKind],
) -> None:
    for row in rows:
        item = _qid(row, "item")
        if item not in asked:
            # As in `works_by_identifier`: an item not asked about is not a key.
            continue
        for name, kind in routes.items():
            topic = _qid(row, name, required=False)
            # An unknown value ("depicts: somebody") is no topic.
            if topic is not None:
                into.setdefault(item, set()).add(
                    RegistryTopicRef(qid=topic, label=RegistryText(_value(row, f"{name}Label")), kind=kind)
                )


def _sorted_refs(found: Mapping[ItemId, set[RegistryTopicRef]]) -> dict[ItemId, tuple[RegistryTopicRef, ...]]:
    order = {kind: index for index, kind in enumerate(_KIND_ORDER)}
    return {
        item: tuple(sorted(refs, key=lambda ref: (order[ref.kind], ref.label.casefold(), ref.qid)))
        for item, refs in sorted(found.items())
    }


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


def _work_page(url: str) -> WorkPage | None:
    """`url` when it is an `http(s)` address with a host and nothing a URL cannot carry; else None.

    The only check a work page gets, because nothing here sends one to the browser
    (`WorkPage`). A value no reader could fetch, or one that would log as more
    than one line, is dropped here rather than stored.
    """
    if len(url) > _PAGE_URL_MAX or any(character <= " " or character == "\x7f" for character in url):
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return WorkPage(url)


def _commons_file(url: str | None) -> CommonsFile | None:
    """A Commons file URL, made `https`, or None for anything else the registry offered as an image."""
    found = _COMMONS_FILE.match(url or "")
    return None if found is None else CommonsFile(f"https://commons.wikimedia.org/wiki/Special:FilePath/{found.group(1)}")


def _measured(prop: str, name: str) -> str:
    """The clause reading one dimension of a work as `?name`, in metres.

    Only the best-ranked statements (`wikibase:BestRank`, which is what `wdt:`
    reads), and none whose *applies to part* (`P518`) is what surrounds the work
    (`_AROUND`). Other parts are the work's own: a painting's height is most
    often recorded as the canvas's. `psn:` is the value Wikidata has already
    normalised to metres, so no unit is read here; a value in a unit with no
    metric equivalent has none and is left out.
    """
    return f"""OPTIONAL {{ ?work p:{prop} ?{name}Said . ?{name}Said a wikibase:BestRank ;
                           psn:{prop}/wikibase:quantityAmount ?{name} .
                         FILTER NOT EXISTS {{ ?{name}Said pq:P518 ?{name}Part . FILTER(?{name}Part IN ({_AROUND})) }} }}"""


def _centimetres(rows: Sequence[Mapping[str, Any]], name: str) -> float | None:
    """The one measurement `?name` holds across a work's rows, in centimetres to the millimetre.

    None when there is none, or more than one: the rows repeat a measurement once
    per combination of the work's other facts, so it is the distinct values that
    count, and two of them disagree.
    """
    metres: set[float] = set()
    for row in rows:
        if name not in row:
            continue
        try:
            value = float(_value(row, name))
        except ValueError:
            continue
        if value > 0:
            metres.add(value)
    if len(metres) != 1:
        return None
    return round(next(iter(metres)) * 100, 1)


def _integer(row: Mapping[str, Any], name: str) -> int | None:
    if name not in row:
        return None
    try:
        return int(float(_value(row, name)))
    except ValueError:
        return None
