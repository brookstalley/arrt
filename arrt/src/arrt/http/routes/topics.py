"""The routes for topics: the index, a topic's page, its works and its artists, and the search of the registry's topics."""

from collections.abc import Callable, Sequence
from typing import Annotated, Final

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from arrt.http.models import (
    HeldTopicOut,
    OfferedTopicOut,
    RegistryCreatorOut,
    SimilarArtistOut,
    TopicArtistsOut,
    TopicFoundOut,
    TopicKindOut,
    TopicPageOut,
    TopicRegistryOut,
    TopicSearchOut,
    TopicsOut,
    TopicWorkOut,
    TopicWorksOut,
    WorkOut,
)
from arrt.http.routes.common import API_PREFIX, _services
from arrt.http.routes.shapes import _work
from arrt.library.services.topics import TopicIndex, TopicPage, TopicWorksView

router = APIRouter(prefix=API_PREFIX)


@router.get("/topics")
def list_topics(request: Request) -> TopicsOut:
    """Library › Topics: every topic the library's works in circulation are in, by kind, with counts.

    Read from the facet rows the topic sweep writes, so it never waits on
    Wikidata. Always a 200.
    """
    return _topics(_services(request).topics.index())


@router.get("/registry/topics")
def search_topics(request: Request, q: Annotated[str, Query()] = "") -> TopicSearchOut:
    """Topics Wikidata finds for a typed name: periods, movements, kinds of work, and subjects.

    Always a 200: `state` says whether the registry was asked and what it did.
    Kept for `REGISTRY_KEPT_FOR`, like every registry answer: a typeahead asks with
    every word, and the same word asked again is answered from disk.
    """
    found = _services(request).topics.named(q)
    return TopicSearchOut(
        state=str(found.state),
        note=found.note,
        topics=[
            TopicFoundOut(
                qid=topic.qid,
                label=topic.label,
                kinds=[kind.value for kind in topic.kinds],
                description=topic.description,
                start=topic.start,
                end=topic.end,
            )
            for topic in found.topics
        ],
    )


@router.get("/topics/{qid}")
def get_topic(request: Request, qid: str) -> TopicPageOut:
    """The library's half of a Topic page: the topic as its works carry it, and those works. No network.

    A topic none of the library's works is in answers with no label and no
    works rather than a 404: a Topic page reached by search is ordinary. A
    malformed QID is a 400.
    """
    services = _services(request)
    page = services.topics.page(qid)
    # Two calls composed, as a theme's works are: the topic says which works,
    # and the survey says what each is as a card.
    return _topic_page(page, [_work(entry) for entry in services.survey.survey_works(page.work_ids)])


@router.get("/topics/{qid}/registry")
def get_topic_registry(request: Request, qid: str) -> TopicRegistryOut:
    """The topic as Wikidata knows it, the page's head, asked separately so it delays nothing.

    Always a 200 for a well-formed QID; a malformed one is a 400. Kept per topic
    for a week, across restarts; a missing item and a failure are not.
    """
    view = _services(request).topics.topic(qid)
    known = view.known
    return TopicRegistryOut(
        state=str(view.state),
        note=view.note,
        qid=qid,
        label=None if known is None else known.label,
        kinds=[] if known is None else [kind.value for kind in known.kinds],
        description=None if known is None else known.description,
        start=None if known is None else known.start,
        end=None if known is None else known.end,
    )


#: The media type of a topic's works asked for as they arrive: one
#: `TopicWorksOut` per line.
NDJSON: Final[str] = "application/x-ndjson"


@router.get("/topics/{qid}/works", responses={200: {"content": {NDJSON: {}}}})
def get_topic_works(request: Request, qid: str) -> Response:
    """*Representative works*: the topic's most renowned works, each with what marks it: held, wanted, its image.

    Asked after the page is drawn: a period's works took 7 to 26 seconds to
    ask for. Always a 200 for a well-formed QID; a malformed one is a 400.

    **Streamed when asked for as `application/x-ndjson`**: one `TopicWorksOut`
    per line as each of Wikidata's answers lands, the works when their ranking
    does and again with their makers, the last line `complete`. Streamed rather
    than paged or polled because the answers are one request's work on the
    server: a page or a poll would hold the half-answer somewhere between
    requests, and a stream holds it nowhere. A kept answer is one complete line
    at once. Anything else asking gets the last line alone, as JSON.
    """
    stages = _services(request).topics.works_in_stages(qid)
    pictured = _services(request).catalogue.pictured
    if NDJSON not in request.headers.get("accept", ""):
        last = next(stages)
        for view in stages:
            last = view
        return JSONResponse(_topic_works(last, pictured).model_dump(mode="json"))
    # A sync generator, so Starlette runs each step in its thread pool: the
    # registry's questions block, and the event loop must not wait on them.
    return StreamingResponse((_topic_works(view, pictured).model_dump_json() + "\n" for view in stages), media_type=NDJSON)


def _topic_works(view: TopicWorksView, pictured: Callable[[Sequence[str]], str | None]) -> TopicWorksOut:
    return TopicWorksOut(
        state=str(view.state),
        note=view.note,
        complete=view.complete,
        works=[
            TopicWorkOut(
                qid=entry.work.qid,
                title=entry.work.title,
                sitelinks=entry.work.sitelinks,
                year=entry.work.year,
                image=entry.work.image,
                creators=[
                    RegistryCreatorOut(qid=creator.qid, name=creator.name, artist_id=view.artists.get(creator.qid))
                    for creator in entry.work.creators
                ],
                creator_unknown=entry.work.creator_unknown,
                state=str(entry.state),
                held_artwork_ids=list(entry.held),
                pictured_artwork_id=pictured(entry.held),
                wanted=entry.wanted,
            )
            for entry in view.works
        ],
    )


@router.get("/topics/{qid}/artists")
def get_topic_artists(request: Request, qid: str) -> TopicArtistsOut:
    """The topic's *Artists*, the most renowned first, each with the library's artist where held.

    Asked after the page is drawn, as *Representative works* is. Always a 200
    for a well-formed QID; a malformed one is a 400.
    """
    view = _services(request).topics.artists(qid)
    return TopicArtistsOut(
        state=str(view.state),
        note=view.note,
        artists=[
            SimilarArtistOut(qid=p.qid, name=p.name, born=p.born, died=p.died, images=p.images, artist_id=view.held.get(p.qid))
            for p in view.people
        ],
    )


def _topics(index: TopicIndex) -> TopicsOut:
    return TopicsOut(
        state=str(index.state),
        note=index.note,
        kinds=[
            TopicKindOut(
                kind=group.kind.value,
                topics=[HeldTopicOut(qid=topic.qid, label=topic.label, works=topic.works) for topic in group.topics],
                offered=[OfferedTopicOut(qid=offer.qid, label=offer.label) for offer in group.offered],
            )
            for group in index.groups
        ],
    )


def _topic_page(page: TopicPage, works: list[WorkOut]) -> TopicPageOut:
    return TopicPageOut(
        state=str(page.state),
        note=page.note,
        qid=page.qid,
        label=page.label,
        kinds=[kind.value for kind in page.kinds],
        works=works,
    )
