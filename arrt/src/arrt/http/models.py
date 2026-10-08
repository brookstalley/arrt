"""The shapes the browser surface receives.

Typed rather than free dictionaries because this is the half of the FastAPI
decision that framework was chosen for: a response model is checked against what
the handler actually returns, so a field renamed in the service layer fails here
rather than becoming an empty cell in a grid.

**Field names match the MCP surface wherever both carry the same fact**
(`artwork_id`, `theme_id`, `lifespan_text`). The two surfaces format for
different readers and are allowed to differ in *shape*; they are not allowed to
differ in what a thing is *called*, because that is how an agent and a click come
to disagree about the same catalogue in a way no test would catch.

This surface carries **no stability obligation** — it ships with its only
consumer and both deploy together (`api-contract.md`). Nothing outside this
repository may bind to it.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ArtistOut(BaseModel):
    """A person a work is attributed to."""

    artist_id: str
    name: str
    nationality: str | None
    born: int | None
    died: int | None
    #: The source's own words for the lifespan, kept because "c. 1650" and a
    #: parsed year are different claims.
    lifespan_text: str | None
    biography: str | None
    #: Which part of the name is the family name — the part the e-paper label
    #: leads with. Stored rather than derived from `name`, because no rule over
    #: one string is right for both "van Gogh" and "Frank Lloyd Wright"; null on
    #: a record that is not a person, and on one nobody has said yet.
    family_name: str | None
    given_name: str | None
    #: The short nationality the e-paper label sets, when the recorded one is
    #: prose rather than a demonym — "Born Moscow (formerly Russian Empire, now
    #: Russia)" against "Russian". Null means `nationality` is what the label
    #: sets, which is the ordinary case; the two are held apart rather than the
    #: recorded value being overwritten, because what an institution printed
    #: about a person is not this product's to edit.
    display_nationality: str | None
    #: The Wikidata item for this person, as the bare QID, or null when none is
    #: known; and who set it: `matched`, `curator`, or null when never set.
    wikidata_qid: str | None
    wikidata_qid_set_by: str | None


class FitOut(BaseModel):
    """How the held master would meet the space it is rendered into.

    Derived on every read from this deployment's panel and mat, never stored: a
    stored verdict is a judgement about one particular television.
    """

    #: `native`, `matted_small` or `below_floor`.
    verdict: str
    rendered_width: int
    rendered_height: int
    #: The number a curator can actually judge — "would show at 8.6 inches". A
    #: thumbnail cannot convey resolution, which is why this is not optional.
    rendered_long_edge_inches: float


class ImageOut(BaseModel):
    """Whether there is an image to show, and which held image it is."""

    available: bool
    #: `tv_display` when the wall's own render is current, `original` when the
    #: master stands in for it, null when there is nothing to show.
    source_kind: str | None
    #: Present exactly when `available` is false, saying what is missing.
    note: str | None


class HeldArtistOut(BaseModel):
    """An artist the library holds, and how many of their works are in circulation."""

    artist: ArtistOut
    held: int
    #: The work the Artists index pictures them by, their first accepted work in
    #: circulation; its thumbnail is `/api/works/{id}/thumbnail`. None only for
    #: an artist with nothing in circulation.
    pictured_artwork_id: str | None


class ArtistListOut(BaseModel):
    """Library › Artists: every artist with a work in circulation, by surname (`surname_key`)."""

    artists: list[HeldArtistOut]


class InReviewOut(BaseModel):
    """A proposed work waiting for a verdict in To review: Review is `#review/{run_id}`, the card `candidate_work_id`.

    A registry row carrying one is *Waiting for review* and is not offered for a
    Get: a run has already found it.
    """

    run_id: str
    candidate_work_id: str


class RegistryWorkOut(BaseModel):
    """One work the registry lists for an artist. `title` is registry text: show it as text."""

    qid: str
    title: str
    year: int | None
    #: How many Wikipedias cover it, which is what the list is sorted by.
    sitelinks: int
    #: A Commons file URL, and only ever one: anything else the registry
    #: offered was dropped before it got here.
    image: str | None
    #: The library's works in circulation that are this one (matched by QID).
    #: Empty when not held; more than one is a duplicate for the curator to see.
    held_artwork_ids: list[str]
    #: A wanted work names this item (Wanted). Reported beside
    #: `held_artwork_ids` rather than instead of it: the page decides which mark
    #: wins (held), and both are true when a wanted work has since been acquired.
    wanted: bool
    #: The proposed work awaiting a verdict that this is, when it is not held.
    in_review: InReviewOut | None = None


class RegistryHoldingOut(BaseModel):
    qid: str
    name: str
    works: int


class ArtistCandidateOut(BaseModel):
    qid: str
    name: str
    born: int | None
    died: int | None
    #: Whether their years agree with the library's, by the matcher's own test.
    years_agree: bool


class UnlinkedArtistOut(BaseModel):
    artist_id: str
    name: str
    born: int | None
    died: int | None


class ArtistRegistryOut(BaseModel):
    """What Wikidata knows about an artist, or why there is nothing to show.

    `state` is `known`, `no_identity` (the artist has no QID), `not_configured`
    (no registry on this server) or `unavailable` (it could not be asked), and
    `note` says which in a sentence whenever it is not `known`. Every string from
    the registry is untrusted text.
    """

    state: str
    note: str | None
    qid: str | None
    #: The registry's name for them, and their years: what heads the page of an
    #: artist the library does not hold.
    name: str | None = None
    born: int | None = None
    died: int | None = None
    #: The library's artist with this QID, when one is asked for by QID: the page
    #: to send the curator to instead. Always null on the library artist's own route.
    artist_id: str | None = None
    description: str | None
    movements: list[str]
    works: list[RegistryWorkOut]
    #: How many works the registry lists in all; `works` is the most renowned of them.
    works_total: int
    holdings: list[RegistryHoldingOut]
    #: State `no_identity` only: who Wikidata's name search says the library's
    #: artist might be, those whose years agree first. Proposed, never stored.
    candidates: list[ArtistCandidateOut] = []
    #: An artist reached by QID: the library's artists of the same name with no
    #: QID, whom the page offers to link to this item.
    unlinked: list[UnlinkedArtistOut] = []


class RegistryCreatorOut(BaseModel):
    qid: str
    name: str
    #: The library's artist with this QID, where it holds one.
    artist_id: str | None


class RegistryHolderOut(BaseModel):
    qid: str
    name: str
    #: The collection's own number for the work, where the registry pairs one with it.
    inventory: str | None


class RegistryWorkPageOut(BaseModel):
    """One work as Wikidata knows it, for the page of a work the library may not hold.

    `state` is `known`, `not_found` (Wikidata has no such item), `not_configured`
    or `unavailable`, and `note` says which in a sentence whenever it is not
    `known`. `held_artwork_ids` is the library's answer and is filled whatever the
    registry did: a non-empty one sends the page to the library's own work. Every
    string from the registry is untrusted text.
    """

    state: str
    note: str | None
    qid: str
    title: str | None
    year: int | None
    sitelinks: int | None
    #: A Commons file URL, and only ever one.
    image: str | None
    creators: list[RegistryCreatorOut]
    media: list[str]
    holders: list[RegistryHolderOut]
    held_artwork_ids: list[str]
    #: A wanted work names this item (Wanted). Reported beside
    #: `held_artwork_ids` rather than instead of it: the page decides which mark
    #: wins (held), and both are true when a wanted work has since been acquired.
    wanted: bool
    #: The work's own height and width in centimetres, each null where Wikidata
    #: gives none, or more than one that disagree.
    height_cm: float | None
    width_cm: float | None
    #: The picture's size in pixels, as Commons holds the file; null with no
    #: picture, or when Commons could not be asked.
    image_width: int | None
    image_height: int | None
    #: How that picture would meet this deployment's wall, as the review grid
    #: judges a scan; null whenever the size is.
    fit: FitOut | None


class LookPictureOut(BaseModel):
    """One instance a source holds of a work, judged as a Get's run would judge it.

    `key` names its picture at `/api/registry/works/{qid}/look/pictures/{key}`,
    the picture store's key computed on the server; null when the source gave no
    preview. Titles and artists are what the source calls the work: untrusted text.
    """

    key: str | None
    provider: str
    #: Where the instance lives at its source. Shown as text, never fetched by the page.
    url: str
    title: str
    artist: str | None
    #: The scan's own size in pixels, as the source reported it. Never null in
    #: practice, since phase 2 refuses a find whose size is unknown; typed as the
    #: source's report is.
    width: int | None
    height: int | None
    fit: FitOut
    below_floor: bool
    confidence: float
    rights_status: str | None
    #: Why phase 2 keeps it, in the words a review card uses, under the name a
    #: scan's carries everywhere else (`InstanceOut`, `list_images`).
    selection_rationale: str


class LookSourceOut(BaseModel):
    """What one image source said about the work."""

    provider: str
    #: `asking`, `found`, `holds_none`, `refused` (it holds a work by this title,
    #: or on the item's page, by another artist), `unreachable` or `cannot`.
    state: str
    #: How many instances it holds that a Get would keep.
    found: int
    #: The gates that turned its other results away: `not_held`,
    #: `identity_refused`, `size_unknown`.
    refusals: list[str]
    answered_at: str | None
    #: When a source that could not be asked will be asked again.
    retry_at: str | None


class LookOut(BaseModel):
    """What the image sources hold of a work the library does not, before any Get.

    `state` is `asking` (poll again) or `answered`, or why nothing is asked:
    `held` (the page goes to `held_artwork_ids`), `being_got`, `no_sources`,
    `not_configured`, `not_found`, `unavailable`. `pictures` are every source's
    finds, best first.
    """

    qid: str
    state: str
    note: str | None
    held_artwork_ids: list[str]
    sources: list[LookSourceOut]
    pictures: list[LookPictureOut]


class RegistryPersonFoundOut(BaseModel):
    qid: str
    name: str
    born: int | None
    died: int | None
    #: The library's artist this is, where it holds one: by QID, or, for a held
    #: artist with none, by name and life dates. One artist is one row.
    artist_id: str | None
    #: A proposed work of theirs awaiting a verdict, when the library does not hold them.
    in_review: InReviewOut | None = None


class RegistryWorkFoundOut(BaseModel):
    qid: str
    title: str
    sitelinks: int
    #: A Commons file URL, and only ever one.
    image: str | None
    creator: RegistryCreatorOut | None
    #: The library's works in circulation that are this one: by QID, or, for a
    #: held work with none, by title and artist. A held work is never also not held.
    held_artwork_ids: list[str]
    #: A wanted work names this item (Wanted). Reported beside
    #: `held_artwork_ids` rather than instead of it: the page decides which mark
    #: wins (held), and both are true when a wanted work has since been acquired.
    wanted: bool
    #: The proposed work awaiting a verdict that this is, when it is not held.
    in_review: InReviewOut | None = None


class RegistrySearchOut(BaseModel):
    """The registry's half of a search: artists and works, each marked where the library holds it.

    `state` is `known`, `too_short` (fewer than three letters: nothing asked),
    `not_configured` or `unavailable`, with a `note` sentence for the last two.
    Every string from the registry is untrusted text.
    """

    state: str
    note: str | None
    artists: list[RegistryPersonFoundOut]
    works: list[RegistryWorkFoundOut]


class SimilarArtistOut(BaseModel):
    qid: str
    name: str
    born: int | None
    died: int | None
    #: Their works with a free image on Wikidata.
    images: int
    #: The library's artist with this QID, where it holds one.
    artist_id: str | None


class SimilarArtistsOut(BaseModel):
    """*Similar artists*: visual artists sharing a movement, by renown, or why there are none.

    `state` is `known`, `not_configured` or `unavailable`, with a `note` for the
    last two. Every string from the registry is untrusted text.
    """

    state: str
    note: str | None
    artists: list[SimilarArtistOut]


class HeldTopicOut(BaseModel):
    """A topic the library's works are in. `label` is registry text: show it as text."""

    qid: str
    label: str
    #: The library's works in circulation in it.
    works: int


class OfferedTopicOut(BaseModel):
    """A topic Library › Topics offers whether or not any work is in it: the server's fixed list."""

    qid: str
    label: str


class TopicKindOut(BaseModel):
    """Every topic of one kind the library's works are in, by name, and those of the fixed list that none is in."""

    #: `period`, `movement`, `subject` or `medium`.
    kind: str
    topics: list[HeldTopicOut]
    #: The centuries and movements offered before any is held, in the list's
    #: order, without any already under `topics`. Empty without a registry.
    offered: list[OfferedTopicOut]


class TopicsOut(BaseModel):
    """Library › Topics: one group per kind, period first, each topic with its count. Read from the facets alone.

    `state` is `known`, or `not_configured` with a `note` saying topics need
    `WIKIDATA_USER_AGENT`; then the groups hold only what an earlier
    configuration recorded.
    """

    state: str
    note: str | None
    kinds: list[TopicKindOut]


class TopicRegistryOut(BaseModel):
    """A topic as Wikidata knows it: the head of a Topic page, or why there is none.

    `state` is `known`, `not_found`, `not_configured` or `unavailable`, with a
    `note` for every state but `known`. Every string is registry text.
    """

    state: str
    note: str | None
    qid: str
    label: str | None
    #: Every kind Wikidata's classes give it, the one its works are found by first.
    kinds: list[str]
    description: str | None
    #: A period's first and last years.
    start: int | None
    end: int | None


class TopicWorkOut(BaseModel):
    """One of a topic's works, as Wikidata lists it, with what the library holds of it."""

    qid: str
    title: str
    sitelinks: int
    year: int | None
    #: A Commons file URL, and only ever one.
    image: str | None
    creators: list[RegistryCreatorOut]
    #: A maker recorded as unknown: somebody made it and nobody knows who.
    creator_unknown: bool
    #: `held`, `image_found` or `no_image`.
    state: str
    #: The library's works in circulation that are it, by QID.
    held_artwork_ids: list[str]
    #: A wanted work names this item (Wanted). Reported beside
    #: `held_artwork_ids` rather than instead of it: the page decides which mark
    #: wins (held), and both are true when a wanted work has since been acquired.
    wanted: bool


class TopicWorksOut(BaseModel):
    """*Representative works*: up to 50, the most renowned first, or why there are none.

    `state` is `known`, `not_found`, `not_configured` or `unavailable`, with a
    `note` for every state but `known`.
    """

    state: str
    note: str | None
    works: list[TopicWorkOut]
    #: False on every line of the streamed answer but the last: the works are
    #: listed and Wikidata is still being asked who made them, so `creators` is
    #: empty and `creator_unknown` false because nothing has been said yet.
    complete: bool


class TopicArtistsOut(BaseModel):
    """A topic's *Artists*: up to 12, the most renowned first, or why there are none. States as `TopicWorksOut`."""

    state: str
    note: str | None
    artists: list[SimilarArtistOut]


class TopicFoundOut(BaseModel):
    """A topic a typed name finds. Every string is registry text."""

    qid: str
    label: str
    kinds: list[str]
    description: str | None
    start: int | None
    end: int | None


class TopicSearchOut(BaseModel):
    """Topics Wikidata finds for a typed name. `state` is `known`, `not_configured` or `unavailable`."""

    state: str
    note: str | None
    topics: list[TopicFoundOut]


class WorkOut(BaseModel):
    """One work as a grid card shows it."""

    artwork_id: str
    title: str
    artist: ArtistOut | None
    date_created: str | None
    medium: str | None
    dimensions: str | None
    description: str | None
    #: The line written for a wall label, which is not the holding institution's
    #: paragraph — see `description` above it, and `Artwork` for why one cannot
    #: stand in for the other.
    commentary: str | None
    rights: str | None
    status: str
    #: The Wikidata item for this work, as the bare QID, and who set it. Matched
    #: only through the holding museum's own identifier, never a title.
    wikidata_qid: str | None
    wikidata_qid_set_by: str | None
    fit: FitOut | None
    #: Present exactly when `fit` is null, saying why there is no verdict. A card
    #: with no size must not read like a card whose work is small.
    fit_note: str | None
    image: ImageOut


class WorkFacetOut(BaseModel):
    """One thing a work is said to be."""

    facet_id: str
    #: One of the six shared vocabulary kinds — `artist`, `movement`, `era`,
    #: `subject`, `medium`, `palette`.
    kind: str
    value: str
    #: `sourced` or `inferred`. **Inferred is the rule rather than the exception**
    #: for the wired collection, so a screen states that default once and marks
    #: only the rare `sourced` value; badging every inferred row is a label on
    #: almost everything, which is a label nobody reads.
    derivation: str
    #: Which field of which provider, or which model. Null where nobody recorded it.
    source_note: str | None
    #: The Wikidata item the value names, the Topic page it opens; null where none.
    value_qid: str | None


class FacetOptionOut(BaseModel):
    """One value a facet control offers."""

    value: str
    #: Works this value would select **given every other facet but not this one**.
    #: That is what lets a curator change their mind about a facet without first
    #: clearing it.
    count: int
    selected: bool
    #: True for an option that would select nothing. **Returned rather than
    #: omitted**: a vocabulary that shrank as filters were applied would read as
    #: data loss rather than as an empty intersection. A selected value is never
    #: disabled, because the control that turns it off is the option itself.
    disabled: bool


class FacetGroupOut(BaseModel):
    """One facet kind as a control renders it."""

    kind: str
    #: Commonest first, then alphabetically, capped — with every selected value
    #: kept whatever its count.
    options: list[FacetOptionOut]
    #: How many values this kind offers in total, before the cap.
    total_values: int
    #: True when the cap left some out, so a control can say how much it is not
    #: showing rather than implying the vocabulary is as long as the list.
    truncated: bool


class ThemeOptionOut(BaseModel):
    """One theme as the *Filter* rail offers it, beside the facets."""

    theme_id: str
    name: str
    #: Works this theme would select **given every other filter but the theme**,
    #: as a facet option's count ignores its own kind.
    count: int
    selected: bool
    #: True for a theme that would select nothing; never for the selected one.
    disabled: bool


class WorkPageOut(BaseModel):
    """A page of works that describes its own place in the set."""

    works: list[WorkOut]
    total: int
    limit: int
    offset: int
    truncated: bool
    #: The facet controls for exactly this filter, in the same response as the
    #: works they label. **Not a second route** — they answer the same question
    #: the grid answers, and two routes would give a curator two answers to it
    #: with a write free to land in between.
    facets: list[FacetGroupOut] = []
    #: Every theme, by name, as a filter option counted against this filter.
    #: Uncapped, and repeated on every page: themes are made by hand, one at a
    #: time, so there are tens of them. If that stops being true, so does the
    #: case for sending them whole with each page.
    themes: list[ThemeOptionOut] = []
    #: *Size on the wall*: one option per fit band, always all four in the order
    #: `native`, `matted_small`, `below_floor`, `unknown` (no master yet), each
    #: counted over every other filter but the bands, as a facet is.
    fits: list[FacetOptionOut] = []
    #: *Not on any wall*: the works no wall plays now, through the theme or
    #: selection hanging on it, counted over every other filter. Null only on
    #: a page built before the facet existed.
    not_on_wall: FacetOptionOut | None = None


class SourceOut(BaseModel):
    """A place a work can be obtained from."""

    source_id: str
    url: str
    provider: str
    source_class: str
    acquisition_method: str
    #: Provenance and source quality. It gates nothing.
    rights_status: str
    is_primary: bool
    confidence: float | None
    selection_rationale: str | None
    last_fetch_status: str | None
    #: When that status was recorded. Present for the same reason the MCP shape
    #: carries it: "failed" with no date cannot be told from "failed months ago
    #: and since fixed", which is the question a curator asks before retrying.
    last_fetched_at: datetime | None


class OriginalOut(BaseModel):
    """The master image a work holds."""

    relative_path: str
    width: int
    height: int
    byte_size: int
    content_hash: str


class RenditionOut(BaseModel):
    """A derived image, and whether it still matches the master it was made from."""

    rendition_id: str
    kind: str
    target_width: int
    target_height: int
    relative_path: str
    #: Derived on every read rather than stored, so it cannot disagree with the
    #: original it is a statement about.
    stale: bool
    generated_at: str


class MatColorOut(BaseModel):
    """A mat colour chosen for a work, and how it was chosen."""

    hex_rgb: str
    #: `vision_model` or `dominant_color_fallback` — recorded because a
    #: mechanical fallback and a considered choice are otherwise identical.
    method: str
    is_current: bool
    reason: str | None
    chosen_at: str


class TopicPageOut(BaseModel):
    """The library's half of a Topic page, read from the facets alone: it never waits on Wikidata.

    `label` and `kinds` are what the library's works carry the topic as, and are
    null and empty for a topic none of them is in; the registry's own head is
    `/api/topics/{qid}/registry`. `works` are the library's works in circulation
    in it, by title. `state` and `note` as `TopicsOut`.
    """

    state: str
    note: str | None
    qid: str
    label: str | None
    kinds: list[str]
    works: list[WorkOut]


class AcquisitionStateOut(BaseModel):
    """Where one work stands in the acquisition queue.

    `phase` is one of `queued`, `fetching`, `failed`, `gave_up` and `paused`,
    each said in words by the client beside its glyph. `detail` is why the last
    attempt failed, or why the queue is paused; `remedy` is what an operator
    changes to end a pause, when the condition has one.
    """

    artwork_id: str
    phase: str
    failures: int
    detail: str | None
    next_try_at: str | None
    since: str | None
    condition: str | None
    remedy: str | None


class QueuePauseOut(BaseModel):
    """Why the acquisition queue is paused: a condition that is the deployment's, not any work's."""

    condition: str
    detail: str
    since: str
    remedy: str | None


class QueuedWorkOut(BaseModel):
    """One work the acquisition queue owes something, named for a person.

    `acquisition.detail` names the work by `title`, never by its id.
    """

    title: str
    acquisition: AcquisitionStateOut


class AcquisitionQueueOut(BaseModel):
    """Activity › Queue's acquisitions: the pause, if any, then one page of the works still in line.

    `works` is the works queued, being fetched or paused, in the order tried,
    paged by `limit` and `offset` out of `total`. A work that failed or that the
    queue gave up on is not among them: it is counted in `failing`, and listed
    under its cause at `/api/acquisitions/causes`, of which there are `causes`.
    """

    pause: QueuePauseOut | None
    works: list[QueuedWorkOut]
    total: int
    limit: int
    offset: int
    failing: int
    causes: int


class FailureCauseOut(BaseModel):
    """Every work whose last try failed for one reason: the reason, naming no work, and how many."""

    cause: str
    works: int
    #: Of `works`, how many will be tried again on their own, and how many the
    #: queue gave up on and wait for Retry.
    failed: int
    gave_up: int


class FailureCausesOut(BaseModel):
    """One page of the causes the queue's failed works share, the largest first, out of `total`."""

    causes: list[FailureCauseOut]
    total: int
    limit: int
    offset: int


class CauseWorksOut(BaseModel):
    """One page of the works that failed for `cause`, in the order the queue holds them, out of `total`."""

    cause: str
    works: list[QueuedWorkOut]
    total: int
    limit: int
    offset: int


class RefusedRetryOut(BaseModel):
    """Why Retry all left some works where they were, naming no work, and how many."""

    reason: str
    works: int


class RetryCauseOut(BaseModel):
    """What Retry all did: how many works it put back in line, and why it refused any it did not."""

    cause: str
    retried: int
    refused: list[RefusedRetryOut]


class WorkDetailOut(BaseModel):
    """One work in full."""

    work: WorkOut
    original: OriginalOut | None
    sources: list[SourceOut]
    renditions: list[RenditionOut]
    mat_colors: list[MatColorOut]
    #: What this work is, in the vocabulary the collection is filtered by. On the
    #: detail rather than on `WorkOut`, because the grid shows the collection's
    #: counts and the Work screen shows one work's facts.
    facets: list[WorkFacetOut] = []
    #: Where the work stands in the acquisition queue; null when the queue owes
    #: it nothing (its image is held and prepared, or it is archived).
    acquisition: AcquisitionStateOut | None = None


class ThemeOut(BaseModel):
    """A grouping of works, and the pace it runs at.

    **It does not say where it is hanging**, and that is the shape of the
    2026-08-12 ruling rather than an omission: a theme is global, two walls may
    hang the same one, and an `is_active` boolean here could only ever have meant
    "active on the one television". `WallOut` is what says what is where.
    """

    theme_id: str
    name: str
    description: str | None
    #: Null means "inherit the deployment default" rather than "unset", so it is
    #: reported as stored rather than resolved to a number that would read as a
    #: choice the curator made.
    rotation_interval_seconds: int | None
    shuffle: bool | None
    created_at: str
    #: Whether works the curator accepts join this theme. At most one is.
    is_default: bool
    #: A selection: works hung on a wall by choosing them, stored as a theme. The
    #: Themes index and the theme pickers leave these out; a wall hanging one
    #: says "a selection" rather than printing this theme's made-up name.
    hidden: bool


class WallRefOut(BaseModel):
    """A wall named from somewhere that is not about walls.

    Just enough to say which wall and to print its name. The full shape would
    carry the theme hanging on it, and a theme listing that carried each wall's
    theme would be answering a question nobody asked from inside the answer to
    another one.
    """

    wall_id: str
    name: str


class ThemePlacementOut(BaseModel):
    """A theme and every wall showing it.

    A list rather than a single wall, because two walls may hang the same theme
    — and a field with room for one would have re-made the single-wall
    assumption one layer above the boolean that was removed. Empty is the
    ordinary state of a theme nobody has hung.
    """

    theme: ThemeOut
    hanging_on: list[WallRefOut]


class ThemeSummaryOut(ThemePlacementOut):
    """A theme as the Themes index draws its card: where it hangs, its size, and a few of its works.

    The listing carries these rather than leaving the index to read every
    theme's works, because a card needs a count and four pictures and a theme
    may hold thousands of works; ten themes would otherwise be ten full reads.
    """

    #: How many works the theme holds, which is how many `GET /api/themes/{id}`
    #: lists: every member, pictured or not.
    work_count: int
    #: Up to four of its works that have a picture, in curated order, for
    #: `GET /api/works/{id}/thumbnail`. Fewer, or none, when fewer of its works
    #: hold an image; a work with no image is skipped rather than drawn empty.
    picture_ids: list[str]


class ThemeListOut(BaseModel):
    """Every theme, where each is hanging, and what its card shows."""

    themes: list[ThemeSummaryOut]


class ReportedStateOut(BaseModel):
    """What a wall's controller last said its screen was doing."""

    #: `showing_art`, `in_use`, `dark`, `no_screen` or `unreachable`.
    state: str
    work_id: str | None
    #: Null from a Player before heartbeat minor 3, which never said.
    since: str | None


class DisplayStateOut(BaseModel):
    """What a wall's screen is doing (`labels-and-surfaces.md` § Display state).

    The controller's five states, read from the wall's heartbeat (a Player before
    minor 3 is read as `showing_art` with its `current_work_id`), and the
    server's own two: `unassigned`, no client shows the wall (it has no display,
    its display has no client, or two clients report its display); `silent`,
    no readable report, or one older than three heartbeat intervals.
    """

    state: str
    #: The work on screen, only with `showing_art`; null there for a picture this
    #: wall did not put there.
    work_id: str | None
    #: When the wall entered this state, where known; for `silent`, the last report's instant.
    since: str | None
    #: The wall's last readable heartbeat: when it was written and how old it is.
    reported_at: str | None
    age_seconds: float | None
    #: For `silent`, what the last readable report said; null otherwise.
    last: ReportedStateOut | None


class ClientNameOut(BaseModel):
    """A client named where another record mentions it."""

    client_id: str
    name: str


class DisplayFaultOut(BaseModel):
    """One display two or more clients report now: neither shows its wall until one stops."""

    identity: str
    #: Every client reporting it, in name order. Two or more.
    clients: list[ClientNameOut]
    #: The server's record under that identity, null when it holds none.
    display_id: str | None
    #: The wall on that display, which neither client shows.
    wall_id: str | None
    #: The fault in one sentence, naming both clients, the same words on every surface.
    description: str


class DisplayOut(BaseModel):
    """One physical screen, keyed by who the device says it is (`feeds-and-players.md` § Displays).

    Nothing about the device beyond what it is and where it is plugged in.
    """

    display_id: str
    #: A Frame's device id as its client read it, or `{client_id}/{output}` for
    #: an output with no identity a client can read.
    identity: str
    #: `frame` or `framebuffer`; null until its client has reported it.
    kind: str | None
    #: The client that last reported it; null once another device has been
    #: reported on its output.
    client_id: str | None
    output: str
    first_seen: str
    #: The wall shown on it, or null.
    wall_id: str | None
    #: Set while two clients report it.
    fault: DisplayFaultOut | None


class WallLabelOut(BaseModel):
    """A label output captioning a wall, and the client that holds it."""

    label_id: str
    client_id: str
    client_name: str
    output: str


class WallOut(BaseModel):
    """A place where art hangs, and what is hanging there.

    The theme travels with the wall rather than being a second request, because
    every screen that shows a wall shows what is on it — and because the pair is
    read at one instant here, where two requests could report a wall and a theme
    that were never simultaneously true.

    **`theme` is null when nothing is hanging**, which is an ordinary state: an
    empty catalogue, or a curator who took everything down.
    """

    wall_id: str
    name: str
    created_at: str
    theme: ThemeOut | None
    #: What this wall was last told to do. Carried because the Walls screen shows
    #: "what is next" beside "what is hanging", and because a per-wall counter is
    #: the thing a reader has to be able to see is per-wall.
    directive_sequence: int
    pinned_work_id: str | None
    #: The client of the wall's display, or null while it has none — an
    #: ordinary state, like a wall with nothing hanging. Read from `display`;
    #: whether that client shows the wall now is `display.fault` being null.
    client_id: str | None
    #: The name of that client's output the wall is shown on. Null exactly when
    #: `client_id` is.
    output: str | None
    #: The display the wall is on, or null while it has none.
    display_id: str | None
    display: DisplayOut | None
    #: Every label output captioning the wall, on any client.
    labels: list[WallLabelOut]
    #: What the wall's screen is doing now, as far as the server can say.
    display_state: DisplayStateOut


class ClientWallOut(BaseModel):
    """A wall as a client listing names it: which wall, and on which of the client's outputs."""

    wall_id: str
    name: str
    output: str


class ReportedOutputOut(BaseModel):
    """One output as the client last reported it."""

    name: str
    #: `frame` or `framebuffer`.
    kind: str
    connected: bool
    #: [width, height] in pixels, or null when the client does not know it.
    screen: list[int] | None
    #: Who the display is, as the client read it from the device; null for an
    #: output with none a client can read.
    identity: str | None


class ReportedLabelOutputOut(BaseModel):
    """One label output as the client last reported it."""

    name: str
    #: `epaper`.
    kind: str
    connected: bool
    #: [width, height] in pixels, or null when the client does not know it.
    size: list[int] | None


class LabelOutputOut(BaseModel):
    """A label output a client holds, and the wall it captions."""

    label_id: str
    output: str
    #: Null while it captions no wall.
    wall_id: str | None


class ClientHeartbeatOut(BaseModel):
    """What a client last said about its outputs, as an observation with an age."""

    reported_at: str | None
    age_seconds: float | None
    #: True when the client has never reported. Not the same as `problem`.
    absent: bool
    #: Set when a report is present and could not be read.
    problem: str | None
    #: The reading as one sentence — never reported, unreadable, or its age —
    #: so the page and the tool surface say it in the same words.
    description: str
    outputs: list[ReportedOutputOut]
    label_outputs: list[ReportedLabelOutputOut]


class ClientOut(BaseModel):
    """An installed Player: its name, when its token was issued, its walls and its last report.

    The token itself is never here: it exists only in the answer that issued it.
    """

    client_id: str
    name: str
    created_at: str
    #: Null while the client has no token, and is admitted nowhere.
    token_issued_at: str | None
    #: The walls it shows now: those on its displays, but for a display in fault.
    walls: list[ClientWallOut]
    #: The displays whose client it is, a wall on one or not.
    displays: list[DisplayOut]
    label_outputs: list[LabelOutputOut]
    #: The display faults it is one side of, each naming every client involved.
    faults: list[DisplayFaultOut]
    heartbeat: ClientHeartbeatOut


class ClientListOut(BaseModel):
    """Every client the server knows."""

    clients: list[ClientOut]


class ClientTokenOut(BaseModel):
    """A client's new token. The only time it is ever shown."""

    client_id: str
    token: str
    token_issued_at: str


class WallAssignmentOut(BaseModel):
    """A wall just placed on a display, and anything the curator should know about it."""

    wall: WallOut
    #: Set when the output could not be confirmed against the client's last
    #: report, or the display has no client or is in fault; the assignment is
    #: made either way.
    notice: str | None


class LabelAssignmentOut(BaseModel):
    """A wall just given a label, and anything the curator should know about it."""

    wall: WallOut
    label_id: str
    #: Set when the label output could not be confirmed against the client's
    #: last report; the mapping is made either way.
    notice: str | None


class WallListOut(BaseModel):
    """Every wall, with what each is showing."""

    walls: list[WallOut]


class DirectiveOut(BaseModel):
    """What one wall was last told to do.

    **The wall is in the answer, not only in the request.** A directive is a row
    per wall rather than a singleton, and an answer that reported only a counter
    would leave a caller holding a number with nothing attached to it — which is
    exactly the state the singleton was in before the split.

    `WallOut` carries the same two facts beside the theme, and this is
    deliberately not that: stepping a wall changes what it was told to do and
    nothing about what hangs there, so an answer shaped like a wall would invite
    a reader to look for a change in the rest of it.
    """

    wall_id: str
    sequence: int
    #: Null after a step, always: moving on and standing on a pinned work are
    #: contradictory instructions, so the step clears any pin.
    pinned_work_id: str | None


class ThemeDetailOut(BaseModel):
    """A theme and the works it holds, in curated order."""

    theme: ThemeOut
    works: list[WorkOut]
    #: Whether a wall hanging it shows its works shuffled: `theme.shuffle`
    #: resolved against the deployment's default, as the manifest resolves it.
    #: `theme.shuffle` alone is null when it inherits, which says nothing about
    #: whether the order on this page decides what the wall shows first.
    shuffled: bool


class ManifestEntryOut(BaseModel):
    """One work as the display plane would receive it."""

    artwork_id: str
    title: str
    artist: str | None
    render_path: str


class ExclusionOut(BaseModel):
    """One work that is in the theme and not on the wall, and why."""

    artwork_id: str
    title: str
    #: One of `UnplayableReason`'s values (`library/readiness.py`), or of
    #: `KeptOff`'s (`programming/manifest/builder.py`) for a work the curator
    #: said not to show again: each a distinct thing a curator would act on
    #: differently. Named there rather than listed here, so a reason added to
    #: either cannot be missing from this description.
    reason: str
    #: A sentence to act on, not a restatement of the reason.
    detail: str


class ManifestOut(BaseModel):
    """What a theme would put on the wall, and everything it would leave off.

    Exclusions are the half of this a list-only view drops silently, which is the
    whole reason the builder reports them.
    """

    #: Which wall this build is about. Named in the response so a confirmation
    #: can say "Hang Winter in the living room" without a second request, even
    #: while there is one wall and the answer is obvious.
    wall_id: str
    wall_name: str
    theme: ThemeOut
    entries: list[ManifestEntryOut]
    exclusions: list[ExclusionOut]
    considered: int
    rotation_interval_seconds: int
    shuffle: bool
    directive_sequence: int
    pinned_work_id: str | None
    #: One sentence saying how much of the theme reached the wall, stated even
    #: when nothing was excluded — a message that appeared only on trouble would
    #: train a reader to skim past its absence.
    summary: str


class HeartbeatOut(BaseModel):
    """What curation can observe about the display plane, stated as observation.

    Never a verdict. `absent` and `problem` are different answers on purpose:
    nothing has ever run is normal on a fresh deployment, and a file that will
    not parse is a fault.
    """

    path: str
    reported_at: str | None
    age_seconds: float | None
    absent: bool
    problem: str | None
    #: One sentence stating what was observed, never a judgement about it.
    description: str
    #: The document as the display plane wrote it, handed through untouched.
    #:
    #: **This is what gives the failure table a reader.** TV connectivity, e-paper
    #: state and the last error are all mapped onto this document by
    #: `observability-strategy.md`, and until it reached the panel those rows named
    #: a signal nothing displayed — a monitoring plan whose evidence existed only
    #: in a file no surface opened.
    #:
    #: Passed through rather than unpacked into named fields, because
    #: `reported_at` is the *only* key that artifact makes contract and the rest is
    #: explicitly the writer's to shape. Naming them here would invent a second
    #: contract the writer never agreed to, and a writer that spelled one
    #: differently would go silently unreported — the exact failure the one named
    #: key exists to prevent, reintroduced for every other field.
    reported: dict[str, Any] | None


class BackupOut(BaseModel):
    """When the catalogue was last safely copied, or that nothing has copied it.

    The catalogue is the irreplaceable asset — the image tree is deliberately not
    backed up, because every file in it can be fetched again. A backup that
    silently stopped succeeding a month ago is the failure this reading exists to
    make visible, and it is the same silent-failure class as everything else here.
    """

    path: str
    completed_at: str | None
    age_seconds: float | None
    #: True when no backup has ever recorded itself. Held apart from `problem`
    #: for the reason the heartbeat holds them apart: never run is normal on a
    #: deployment whose backup is not yet scheduled, and a receipt that will not
    #: parse is a fault.
    absent: bool
    problem: str | None
    #: One sentence stating what was observed, never a judgement about it. There
    #: is no threshold here: six days is alarming for a nightly job and
    #: unremarkable for a destination that is usually asleep, and this surface
    #: does not know which deployment it is on.
    description: str
    #: The receipt as the backup job wrote it, past the one key this side reads.
    #: Where the copy went and how large it was are the job's to record.
    reported: dict[str, Any] | None


class WallHeartbeatOut(BaseModel):
    """One wall and what the display serving it last said about itself.

    The wall's name travels with its reading rather than being looked up by the
    client from a second call: a panel that has to join two responses to say
    *which* room is silent is a panel that will say "a wall is silent" instead.
    """

    wall_id: str
    wall_name: str
    heartbeat: HeartbeatOut


class SourcePluginOut(BaseModel):
    """One installed source plugin: loaded, declined, or not loaded, and its faults since startup."""

    name: str
    #: `loaded`, `declined` (installed and not configured here) or `failed`
    #: (installed and could not be loaded). Carried as itself, never as a flag.
    state: str
    #: Why it declined or failed; null when it loaded.
    reason: str | None
    faults: int
    last_fault_at: str | None
    last_fault_age_seconds: float | None
    last_fault: str | None
    description: str
    #: The installed distribution that registers the plugin, and its version;
    #: null for a plugin registered by hand, or one two distributions both claim.
    distribution: str | None
    version: str | None
    #: The source interface major the plugin was written for; null when it
    #: failed before saying.
    api_major: int | None
    #: What its parts provide: `finds_images`, `finds_pages`, `reads`,
    #: `browses`. Empty for a plugin that did not load.
    provides: list[str]


class SourcesOut(BaseModel):
    """Every installed source plugin, most preferred first, and the interface this Arrt provides."""

    #: `major.minor`. A plugin written for another major is refused by name.
    interface_version: str
    sources: list[SourcePluginOut]


class PicturesOut(BaseModel):
    """How much the picture store keeps: its files and their bytes, and how old the count is.

    The store has no ceiling (owner, 2026-10-06), so its growth is watched here
    rather than bounded. The same names, and the same values, as `art_display`'s
    `status` carries (`test_surface_parity.py`).
    """

    pictures_bytes: int
    pictures_files: int
    #: Seconds since the walk the count came from, which is reused for ten minutes.
    age_seconds: float
    #: Directories and files the walk could not read: not zero is a disk fault,
    #: and the count is short by what they hold.
    unreadable: int
    description: str


class HealthOut(BaseModel):
    """Observations about the walls, the backup, the source plugins and the picture store.

    **No geometry**, since 2026-10-08 (#266): there is no longer one television
    to state it for. A wall's own geometry is wave 4's, under Clients.

    **The heartbeat is a list, one entry per wall**, since 2026-08-12. Each wall's
    display writes its own file, so "has the display plane reported" stopped being
    a question with one answer and became "which wall has not" — and a single
    reading could not have carried the name of the room that went quiet.

    **There is no budget balance here**: the month's budget is the sidebar's,
    `BudgetOut` (#290). It stays off this panel because the provider's
    `limit_remaining` fails by inversion rather than by staleness, so stating
    its age, this panel's remedy for a stale figure, would not warn about the
    case that bites (`services/health.py`).
    """

    walls: list[WallHeartbeatOut]
    #: One sentence across every wall, naming the ones that have not reported.
    #: An observation and never a verdict: no threshold is applied here, so this
    #: says how long ago rather than whether that is too long.
    description: str
    backup: BackupOut
    #: Every installed source plugin, most preferred first. Empty when none is
    #: installed, which the panel says in words.
    sources: list[SourcePluginOut]
    pictures: PicturesOut


class SourceYieldOut(BaseModel):
    """What one installed source has given the library, counted from the records.

    An observation, never a ranking, and it survives a restart because nothing
    here is a tally: every figure is counted again from the catalogue and the
    search records on each read.
    """

    #: The plugin's name, as `SourcePluginOut.name` carries it.
    name: str
    #: Distinct images, by address, it has offered to a search or as a held
    #: work's source; one the curator turned down still counts.
    offered: int
    #: Works held by an image from it: their primary source is this one.
    chosen: int
    #: Of those, the works no other source offered any image for.
    only_here: int
    #: The median long edge, in pixels, of its offered images whose size is
    #: known; null when none is.
    median_long_edge: int | None


class SourceYieldsOut(BaseModel):
    """Every installed source plugin's yield, most preferred first, as `GET /api/health` lists the plugins."""

    sources: list[SourceYieldOut]


class RunOut(BaseModel):
    """One discovery run as a list row shows it.

    The terminal state is carried as itself and never collapsed into a
    succeeded/failed flag, for the same reason the MCP surface refuses to: out of
    money, broke, and the process restarted underneath it call for three
    different responses from the person reading the row.
    """

    run_id: str
    #: `discovery`, `resolve` or `get`. A re-search and a Get are runs, which
    #: is what lets one screen follow any of them without knowing which it is
    #: looking at.
    kind: str
    status: str
    #: Whether this run has ended. Carried rather than left for the client to
    #: derive from a list of status names, because that list is the thing that
    #: goes stale: a tenth status added to the enum would leave a browser polling
    #: a finished run forever, with nothing failing to say so.
    is_terminal: bool
    initiated_by: str
    intent: str | None
    #: How the engine read the intent, in its own words. A work list is judged
    #: against the reading of the request rather than its wording, so a
    #: surprising list is explicable instead of merely wrong. Null while phase 1
    #: is still working: nothing has read the intent yet.
    strategy: str | None
    #: Whether the run stopped for approval: false on every run since the gate
    #: was removed (2026-10-07), true only on one that stopped before then.
    approval_required: bool
    #: Prices are strings, never floats. A tenth of a cent that cannot be
    #: represented exactly is a rounding error in the figure a curator authorised
    #: against, and then in a total nobody reconciles.
    estimated_cost_usd: str | None
    actual_cost_usd: str | None
    unresolved_work_count: int | None
    parent_run_id: str | None
    started_at: str
    completed_at: str | None
    #: The theme a Get's accepted works join instead of the default, or null for
    #: the default. An id, which may name a theme deleted since: the run records
    #: where the curator asked the works to go, and the theme is looked up by
    #: whoever shows it.
    destination_theme_id: str | None
    #: Why the run's worker ended it, in its own words: present on `failed` and
    #: `halted_by_budget`, null on every other ending and on a run that ended
    #: before reasons were kept. Prose for a curator to read, never a code to
    #: branch on; `status` is what says which ending this was.
    end_reason: str | None


class CandidateWorkOut(BaseModel):
    """One work a run proposed or was offered, in words rather than pictures.

    Shared by the run view and the review grid, which show the same work at two
    altitudes — a row in a run's work list, and the text half of a card being
    judged. One model rather than two because it is one work: a second shape
    would let the two screens come to call the same fact by different names,
    which is the failure `models.py` exists to prevent one surface further out.
    """

    work_id: str
    #: The catalogue work acceptance made of it; null until it is accepted. What
    #: a review card follows to say how the work's image is coming along.
    artwork_id: str | None = None
    title: str
    artist: str | None
    #: Why the engine named this work. Shown because a curator judging a work
    #: list is judging the reasoning as much as the titles.
    rationale: str
    #: `proposed` — the model named it — `offered`, meaning a wired collection
    #: volunteered it on top of the list, or `chosen`, meaning the curator chose
    #: it from Wikidata for a Get. Never merged into one count: the curator
    #: authorised a list of a stated size and the supplement adds to it.
    provenance: str
    #: The Wikidata item a chosen work was asked for by; null otherwise.
    wikidata_qid: str | None
    #: For an offered work, the browse query that produced it and how many works
    #: that query matched in the collection; null on both for a proposed work.
    #:
    #: Sent as two facts rather than as a finished sentence so each surface can
    #: say them where its own grouping puts them — `product-brief.md` requires a
    #: curator to be able to tell one-of-four-hundred from one-of-one, and asks
    #: that it be said once for the query rather than on every card. A composed
    #: sentence could only ever be said per work, which is what it used to be.
    #:
    #: **`matched` is the collection's holdings, not the number offered.** The
    #: per-run bound caps what is shown; this is what it is capped from, and the
    #: two are meant to be read against each other.
    offered_for_artist: str | None
    offered_artist_matched: int | None
    verdict: str
    #: Whether the verdict is final (`Verdict.is_terminal`): accepted or rejected.
    #: A decided work takes no second verdict and no change of scan, so the review
    #: card offers neither; served rather than listed in the client, so a verdict
    #: made final later reaches the card without a second copy to update.
    decided: bool
    resolution_status: str
    #: Which kind of nothing an unresolved work came back with, or null. A bare
    #: `unresolved` cannot tell a title nobody holds from a scan too small for
    #: the wall, and those lead to opposite actions.
    unresolved_reason: str | None
    #: `confirmed`, `unconfirmed` or `unknown` (`Confirmation`): whether a source
    #: confirms the work exists. A proposed work is confirmed only on phase 1's
    #: word that a search result names it; with no word it is `unknown`, never
    #: confirmed. The card marks anything not confirmed *Not confirmed*, and the
    #: review listing sorts unconfirmed works after confirmed ones.
    confirmation: str


class RunTallyOut(BaseModel):
    """How many works a run has, cut the ways a curator reads them.

    Proposed and offered are counted apart wherever a number is shown. With
    twelve offered works behind one unresolved proposal, a merged "12 of 13 have
    an image" reports a resolution rate the run never achieved.
    """

    total: int
    proposed: int
    offered: int
    #: A Get's works, which the curator chose; zero on every other kind of run.
    chosen: int
    resolved: int
    #: How many of the model's own works ended up with an image — the numerator
    #: any resolution rate is stated over. Counted directly rather than derived
    #: by subtracting offered works from resolved, which goes negative as soon as
    #: an offered work is re-searched to nothing.
    resolved_proposals: int
    unresolved: int
    pending: int


class SearchUsageOut(BaseModel):
    """What a run has used of its search allowance.

    Two numbers rather than one verdict: the usage is this run's own history and
    the allowance is the deployment's current setting, so a run read after the
    setting changed shows both instead of a boolean recomputed against a rule it
    never ran under.
    """

    used: int
    allowance: int
    exhausted: bool


class RunViewOut(BaseModel):
    """A run in full — its state, its works, and what it has spent looking."""

    run: RunOut
    tally: RunTallyOut
    #: Every work, uncapped, and **nothing bounds how many there are** but one
    #: model answer's output reservation — phase 1 is deliberately not capped at
    #: a work count, so a run that read an intent too broadly ("you asked for
    #: Dalí and I found 200 works, really?") shows it whole. So this list is as
    #: long as the run is wide.
    #:
    #: Sent whole anyway. The MCP surface stops at 100 because a model's context
    #: is the scarce thing; here the reader is a curator reading the run, and a
    #: truncated list is the one that hides how wide it read.
    works: list[CandidateWorkOut]
    searches: SearchUsageOut
    #: Whether this deployment can resolve images at all. A run sitting in
    #: `resolving_images` means work under way or work nothing will ever pick up,
    #: and there is no other way to tell those apart.
    image_resolution_available: bool


class RunListOut(BaseModel):
    """The newest runs, and how many there were before the cap.

    `total` and `truncated` are carried rather than left for the client to
    infer from `len(runs)`: a silently short list is indistinguishable from a
    complete one, which is how a curator concludes there have been fifty runs
    when there have been four hundred.
    """

    runs: list[RunOut]
    count: int
    total: int
    truncated: bool
    #: Works with an image and no verdict yet, across every run and not only the
    #: listed ones: what *To review* counts.
    awaiting_works: int
    #: The same, by run id, for the listed runs that hold any; a run with none is
    #: absent. Beside the runs rather than on each, because a run read on its own
    #: has its works to say it.
    awaiting: dict[str, int]


class EstimateOut(BaseModel):
    """What something is expected to cost, and which question was answered.

    `phase` is carried rather than inferred from whether a run was named: "what
    will asking cost" and "what will resolving what I found cost" are different
    questions, and a number whose meaning depends on remembering what you sent
    gets read wrong.
    """

    phase: str
    estimated_cost_usd: str
    #: `free`, `$`, `$$` or `$$$` (`spending.cost_tier`): what the control shows
    #: before the action is taken. Asking's is the tier of its bound.
    tier: str
    basis: str
    run_id: str | None


class CostTiersOut(BaseModel):
    """Where the tiers change, so a control can word a figure as its tier: free at zero, then `$`, `$$`, `$$$`."""

    #: Under this is `$`.
    cents_below_usd: str
    #: Under this is `$$`; this or more is `$$$`.
    dimes_below_usd: str


class BudgetOut(BaseModel):
    """What is left of this month's budget, read from the provider (`spending.BudgetService`).

    `state` is `known` (the key's monthly limit, from the provider), `configured`
    (the key has no limit; `MONTHLY_BUDGET_USD` less the provider's spend this
    month), `uncapped` (no limit and no budget: only `spent_usd`),
    `not_configured` (no key; nothing spends) or `unavailable`. Money is a
    decimal string. Display only and up to a minute old: nothing gates on it.
    """

    state: str
    #: What is left this month, never below zero; null unless `known` or `configured`.
    remaining_usd: str | None
    #: The month's budget: the key's limit or the configured one.
    budget_usd: str | None
    #: What the provider counts as spent this month, where it said.
    spent_usd: str | None
    note: str | None
    tiers: CostTiersOut


class SpendOut(BaseModel):
    """What was actually spent, over a run or over a calendar month.

    **No `run_direct_cost_usd`, unlike the MCP twin, and the absence is a
    decision.** This surface's costs panel reads "what this run alone spent" off
    the run record's `actual_cost_usd`, which is the same figure — so carrying it
    here as well would give one screen two sources for one number, and the unread
    one is where they would silently diverge. What this payload is fetched for is
    the family total, which lives nowhere else.

    Stated here rather than as a `#:` comment where the field used to be: a
    comment in that position documents the field *below* it, so an explanation of
    something absent would be read as describing `year`.
    """

    scope: str
    cost_usd: str
    run_id: str | None

    year: int | None
    month: int | None


class InstanceOut(BaseModel):
    """One image instance as a curator judging it needs to see it.

    **The size is not decoration and it is why this model is not just a URL.** A
    900 px scan and a 6000 px scan are the same picture in a review card, so a
    grid that showed only pictures would not protect against hanging a postage
    stamp. Every instance therefore carries the size it would render at on *this*
    deployment's wall, in inches — the number a curator can actually judge.
    """

    image_id: str
    work_id: str
    #: Where the scan lives at its provider. Shown because an instance with no
    #: local copy is still real and still selectable, and this is all a curator
    #: has to go on when the picture cannot travel.
    url: str
    provider: str
    confidence: float
    #: Whether this is the instance a verdict would accept on. Not the same
    #: question as whether it is the one pictured on the card — a work whose scans
    #: are all below the floor or all turned down has no selection and is still
    #: shown, which is what `shown_is_on_offer` reports one level up.
    is_selected: bool
    #: Whether the curator has turned this scan down. A rejected instance stays on
    #: the card, labelled: it is the evidence of a judgement already made, and
    #: hiding it would leave a curator wondering why a re-search returned fewer
    #: instances than before.
    rejected: bool
    rights_status: str | None
    selection_rationale: str | None
    #: The scan's own size in pixels, as its provider reported it, or null when
    #: nobody recorded it. What the browser shows a curator as the scan's
    #: resolution: pixels are a fact about the scan, where the fit below is a
    #: fact about the one panel this server is configured for. Each is null when
    #: the provider did not report it, and `fit` is null whenever either is.
    width: int | None
    height: int | None
    fit: FitOut | None
    #: Present exactly when `fit` is null. An instance whose dimensions nobody
    #: recorded must not read like one known to be small: the first is a fact
    #: about our record, the second a fact about the picture.
    fit_note: str | None
    #: Whether a picture travels with this instance. Carried so a card knows
    #: before it asks, rather than requesting bytes that are not there and
    #: painting a blank box while it finds out.
    preview_available: bool
    #: Present exactly when no picture travels, saying which of the four reasons
    #: applies — never kept (or, on a work decided before 2026-10-06, deleted
    #: then), gone from disk, or undecodable. They send whoever asks to different places.
    preview_note: str | None


class CandidateCardOut(BaseModel):
    """One proposed work with the instance whose picture stands for it."""

    work: CandidateWorkOut
    #: The instance pictured on the card, or null when there is genuinely nothing
    #: to show — no instances at all, or every one of them rejected.
    #: `instances_held` and `instances_surviving` tell those two apart.
    shown: InstanceOut | None
    #: Whether the pictured instance is also the one a verdict would accept on. A
    #: work with no selection still arrives pictured, because a below-floor scan
    #: must be shown, labelled and selectable rather than hidden — and a card
    #: carrying no image because nothing was auto-selected would hide it.
    shown_is_on_offer: bool
    instances_held: int
    instances_surviving: int
    #: The catalogue artwork this work already became through an earlier run,
    #: or null. Additive: a client that ignores it offers Accept as before.
    held_artwork_id: str | None = None


class CandidatePageOut(BaseModel):
    """One page of a run's works, with enough context to describe itself."""

    run: RunOut
    works: list[CandidateCardOut]
    total: int
    limit: int
    offset: int
    truncated: bool


class InstanceListingOut(BaseModel):
    """A work's instances in the order the review card offers them, capped."""

    work: CandidateWorkOut
    instances: list[InstanceOut]
    #: What the work actually holds, against `len(instances)` for what this card
    #: shows. Reported separately so a truncated card cannot be read as a
    #: complete one — the failure a count omitted alongside a list always makes.
    held: int
    #: The same distinction one level in: how many instances are still choosable,
    #: against how many of *those* fit. A card that dropped only refused scans and
    #: one that also dropped choosable ones are different things to tell a
    #: curator, and `held` counts both kinds together.
    surviving_held: int
    truncated: bool
    #: False only when the choosable instances alone outrun the cap, which is the
    #: one case where a truncated card withholds something actionable.
    shows_every_choosable_instance: bool


class VerdictOut(BaseModel):
    """A recorded verdict, and what recording it did beyond the verdict itself."""

    work: CandidateWorkOut
    #: Null on a rejection, and the id of the minted work on an acceptance — the
    #: handle every catalogue action takes, so accepting hands back the thing the
    #: next call needs rather than making the caller go looking.
    artwork_id: str | None
    decided_at: str | None
    #: Both reported on every acceptance, empty included. A key present only when
    #: an artist was minted would teach a reader to take its absence as "nothing
    #: happened", which is the silence this pair exists to break: a duplicate
    #: artist row looks exactly like a painter newly encountered.
    minted_artist: ArtistOut | None
    possible_duplicate_artists: list[ArtistOut]
    notice: str | None


class SelectedImageOut(BaseModel):
    """Which instance a work now stands on.

    No `is_on_offer` flag: `select_image` either makes this the instance on offer
    or refuses, and a refusal returns no payload — so the field could only ever
    read true, and would restate the fact that the call succeeded.
    """

    image_id: str
    work_id: str
    url: str
    selection_rationale: str | None


class StartRun(BaseModel):
    """An intent to search for, in the curator's own words."""

    intent: str


class StartResolve(BaseModel):
    """The works to look again for images of."""

    work_ids: list[str]


class StartGet(BaseModel):
    """The Wikidata items of the works to get, and where the accepted ones go."""

    qids: list[str]
    #: The theme the accepted works join instead of the default, or null for the
    #: default. An unknown theme refuses the Get and starts nothing. Creating a
    #: new theme is an earlier `POST /api/themes`, never something this does.
    theme_id: str | None = None


class SkippedOut(BaseModel):
    """An item a Get left out, and why: `held`, `being_got`, `in_review` or `not_found`."""

    qid: str
    reason: str


class GetOut(BaseModel):
    """The run a Get started, or null when every item was skipped, and what it skipped."""

    run: RunOut | None
    skipped: list[SkippedOut]


class SetVerdict(BaseModel):
    """A curator's decision about a proposed work: `accepted` or `rejected`.

    `wanted` is deliberately not settable here: its one way in is
    `POST /api/candidates/{id}/want`, which is also where a scan being turned
    down on the way is suppressed, so the two can never come apart. The service
    refuses it, and the refusal names `want`.
    """

    verdict: str
    #: Why, in the curator's words. Optional, and worth having: "rejected" and
    #: "rejected because it is a studio copy" are the same row to the pipeline and
    #: different evidence to whoever reads it later.
    reason: str | None = None


class WantWork(BaseModel):
    """That the curator wants a work, and which scan of it, if any, they are turning down.

    `turning_down` is a scan of this work. Named, it is suppressed and the
    selection falls through, as turning it down on its own row does; omitted,
    nothing is suppressed, because wanting a work found with no scan is not a
    judgement about any scan.
    """

    turning_down: str | None = None


class WorkMatchOut(BaseModel):
    """One Wikidata item matching a wanted work's title, for the curator to pick from.

    Registry text, shown as text. `has_image` says whether Commons holds a file
    for it, which is what a re-search by this item could find.
    """

    qid: str
    title: str
    creator: str | None
    sitelinks: int
    has_image: bool
    #: Whether its creator is the artist the run proposed: what puts it first.
    by_proposed_artist: bool


class WorkMatchesOut(BaseModel):
    """Wikidata's items for a wanted work, and why there are or are not any."""

    work_id: str
    title: str
    #: `known`, `not_configured` (no `WIKIDATA_USER_AGENT`) or `unavailable`.
    state: str
    note: str | None
    matches: list[WorkMatchOut]


class PickItem(BaseModel):
    """The Wikidata item the curator picked for a wanted work."""

    qid: str


class WantedWorkOut(BaseModel):
    """A work the curator wants and holds no scan of they would accept.

    Named as `art_review(action='list_wanted')` names the same facts.
    """

    work_id: str
    title: str
    artist: str | None
    #: The run that proposed the work, which is where its card lives.
    run_id: str
    #: The Wikidata item the work is known by, or null when none is.
    wikidata_qid: str | None
    #: How many of its scans the curator turned down: zero for a work wanted
    #: because nothing was found. Counted from its scans, not stored.
    scans_turned_down: int
    #: The scan its review card pictures it by (`CandidateCardOut.shown`), or null
    #: when nothing was found or every scan was turned down. Usually below the
    #: floor, since a wanted work holds no scan the curator would accept.
    shown: InstanceOut | None = None


class WantedListingOut(BaseModel):
    """Every wanted work, newest run first.

    Uncapped, and what bounds it is the curator: each row is a work somebody
    wanted by name, one call per work, so the list grows no faster than works are
    judged. A row carries its picture's description, never its bytes: whether one
    exists is a `stat`, and the browser asks for each by URL as it scrolls in.
    """

    works: list[WantedWorkOut]


class SightingHostOut(BaseModel):
    """A host with pages for open works that no installed source plugin reads.

    A name, never an address: a sighting's URL came from a registry anyone can
    edit, and none reaches the browser (`security-model.md` § Direction).
    """

    host: str
    #: How many open works it has such a page for.
    works: int


class SightingHostsOut(BaseModel):
    """Every such host, most works first. Named as `art_review(action='sighting_hosts')` names the same facts."""

    hosts: list[SightingHostOut]


class SelectImage(BaseModel):
    """Why this scan rather than the one the pipeline picked."""

    rationale: str | None = None


class CreateTheme(BaseModel):
    """Everything needed to record a theme."""

    name: str
    description: str | None = None


class RenameTheme(BaseModel):
    """The new name, and deliberately nothing else.

    `update_theme` can also change a description and a theme's pace, and this
    body cannot reach either. That is the route's scope rather than an oversight:
    the service distinguishes "leave this alone" from "clear it" with a sentinel,
    and a request model whose optional fields default to `None` would erase a
    theme's rotation settings every time a curator corrected a typo in its name.
    A body that can only say one thing cannot say that one by accident.
    """

    name: str


class CreateWall(BaseModel):
    """Everything needed to record a wall: a name, and nothing device-shaped."""

    name: str


class NameClient(BaseModel):
    """A client's name, to record it or to rename it. Nothing device-shaped."""

    name: str


class AssignWall(BaseModel):
    """Which client shows the wall, and on which of its outputs, by the name the client reports."""

    client_id: str
    output: str


class AssignDisplay(BaseModel):
    """Which display shows the wall, by the display's id."""

    display_id: str


class AddLabel(BaseModel):
    """Which label output captions the wall: a client's, by the name the client reports."""

    client_id: str
    output: str


class HangTheme(BaseModel):
    """Which wall a theme is being hung on.

    **Required, even while there is one wall and the answer is obvious.** A
    request that omitted it would produce a confirmation that reads correctly
    today and silently becomes wrong the day a second display arrives.
    """

    wall_id: str


class HangSelection(BaseModel):
    """The works to hang on a wall, in the order they should show. One or more."""

    artwork_ids: list[str]


class NotAgainRequest(BaseModel):
    """*Not this one again*: which work, and how far the curator meant it.

    `scope` is `theme` (take it out of the theme hanging on this wall) or
    `every_wall` (keep it off every wall until allowed again; it stays held).
    """

    artwork_id: str
    scope: str


class NotAgainOut(BaseModel):
    """What *Not this one again* did, and the wall as it now stands."""

    scope: str
    artwork_id: str
    wall: WallOut
    #: The theme the work left, for `theme`; null for `every_wall`.
    left_theme: ThemeOut | None
    #: When the work was kept off every wall, for `every_wall`; null for `theme`.
    excluded_at: str | None


class ExcludedWorkOut(BaseModel):
    """A work kept off every wall. It is still held, and still in its themes."""

    artwork_id: str
    excluded_at: str


class ExcludedWorkListOut(BaseModel):
    """Every work kept off every wall, oldest first."""

    exclusions: list[ExcludedWorkOut]


class WorkPlacementsOut(BaseModel):
    """Where one held work is: the themes holding it, and whether it is kept off every wall.

    `themes` includes selections (`theme.hidden`), each with the walls hanging
    it, because a selection is how a single work hangs on a wall. A hidden theme
    hanging nowhere is an old selection, which the Work page leaves unsaid.
    """

    artwork_id: str
    themes: list[ThemePlacementOut]
    #: When the work was kept off every wall, or null when it may go on walls.
    excluded_at: str | None


class HistoryEventOut(BaseModel):
    """One act in the history: what, when, and what it was about.

    `kind` is one of `EventKind`'s values (`persistence/records.py`). Every id
    is a reference that may no longer resolve (a work archived, a theme
    deleted), so `detail` carries the words the event is read by, copied when
    it happened: a `title`, a `theme_name`, whether a hang was a `selection`,
    how a Get ended (`status`, `reason`).
    """

    event_id: str
    kind: str
    occurred_at: str
    artwork_id: str | None
    run_id: str | None
    wall_id: str | None
    theme_id: str | None
    detail: dict[str, Any]


class HistoryPageOut(BaseModel):
    """A page of history, newest first, and how many events the filter holds."""

    events: list[HistoryEventOut]
    total: int
    limit: int
    offset: int


class StepDisplay(BaseModel):
    """Which wall is being told to move on to the next work.

    **Required, for the reason `HangTheme` states.** A `next` aimed at the living
    room that stepped the study is one counter being asked a question it cannot
    answer, and a request that guessed would be indistinguishable from one that
    meant it.
    """

    wall_id: str


class RetryCause(BaseModel):
    """Retry all: the cause, exactly as `/api/acquisitions/causes` words it."""

    cause: str


class SetIdentity(BaseModel):
    """The curator's word on which Wikidata item this is.

    A QID (`Q160149`) sets it; null says there is none, which the matcher then
    leaves alone. Either way the curator's word outlasts every matching pass.
    """

    qid: str | None


class AddWork(BaseModel):
    """A work to place in a theme, at a chosen index or at the end of the order."""

    artwork_id: str
    #: An index into the order the theme is displayed in, not a number stored on
    #: the work. Null puts it last — the screens send nothing, and a work nobody
    #: has placed belongs at the end rather than outside the order.
    position: int | None = None


class MoveWork(BaseModel):
    """Where a work should sit in a theme's order."""

    #: Null moves it behind everything a curator has placed deliberately.
    position: int | None = Field(default=None)


class SampleOut(BaseModel):
    """One picture shown beside a name a reply gave, to make the name concrete.

    **Not a candidate and not on its way to becoming one.** Nothing here has been
    proposed, judged, or acquired — it is a work the wired collection holds by an
    artist the model named. `image_url` is the collection's own preview address,
    loaded by the browser directly, because a conversation keeps no files of its
    own. Moving such pictures behind Arrt's routes, into the picture store, is a
    plan of its own (`build-plan-picture-store.md` § Not in this plan).
    """

    title: str
    artist: str | None
    #: Null when the deployment browses no collection, or when the collection's
    #: record carries no preview. The name is still shown; a sample without a
    #: picture is a fact stated plainly rather than a blank box.
    image_url: str | None


class SuggestionOut(BaseModel):
    """One thing a turn named, and whatever pictures were found for it.

    `kind` is drawn from the same closed set an affinity is recorded against —
    artist, movement, era, subject, medium, palette — because a suggestion is
    what an affinity would later be recorded *about*, and two vocabularies would
    leave the thing said and the thing remembered unable to be matched up.
    """

    kind: str
    value: str
    #: Frozen at the moment the turn was written, never looked up on read. The
    #: transcript is a record of what was said, so a thread re-read next month
    #: shows the pictures it showed at the time rather than whatever the
    #: collection would answer today. Empty for a kind the collection cannot be
    #: browsed by, which today is everything but `artist`.
    samples: list[SampleOut]


class ConversationTurnOut(BaseModel):
    """One thing said in a conversation.

    `role` is `curator` or `system` — the product's own words, deliberately not
    the provider's `user`/`assistant`. The transcript a curator reads back is in
    the product's terms, and the translation to a chat API's happens once, far
    below this surface.
    """

    turn_id: str
    ordinal: int
    role: str
    #: Verbatim, and never null. A model turn that was cut off arrives from the
    #: provider with no content at all; storing that null is what would make the
    #: *next* turn fail over a missing content field rather than over anything
    #: that went wrong, so a turn with nothing in it carries the empty string.
    text: str
    suggested: list[SuggestionOut]
    #: The seam. Set on the turn where the curator committed a direction, and the
    #: only edge from a conversation to a run. A run started from the Discover
    #: box has none, and neither does any turn before the commit.
    committed_run_id: str | None
    created_at: str


class ConversationOut(BaseModel):
    """One conversation as a list row shows it."""

    conversation_id: str
    started_at: str
    #: What the list is ordered by. Distinct from `started_at` because the thread
    #: a curator is looking for is the one they last said something in, and the
    #: day it began says nothing about that.
    last_turn_at: str
    #: A short account of where the conversation got to, for the list. **Never
    #: read back as taste** — an affinity is the only thing the product consults
    #: for that, and a summary consulted as one would be a second, prose-shaped
    #: opinion free to drift from the recorded one.
    summary: str | None


class ConversationViewOut(BaseModel):
    """A whole thread, and whatever is outstanding on it.

    `failure` and `unanswered_turn_id` are the retryable failed turn, and they
    are deliberately different kinds of fact. `unanswered_turn_id` is derived
    from the transcript — a thread whose last turn is the curator's is one whose
    question was not answered — so it survives a reload and cannot disagree with
    what the thread says. `failure` is the account of why *this* attempt did not
    answer, and it lives only on the response to that attempt: it is a fact about
    a call rather than about the conversation, and a transcript that kept it
    would report a provider's transient complaint as part of what was said.

    **Every write returns this whole view rather than the turn it wrote.** A
    failed turn must stay in the thread and be retryable, which a client cannot
    render from an error body — so a turn that could not be answered is a 200
    carrying the thread and the reason, and only a refusal that recorded nothing
    at all is a 400.
    """

    conversation: ConversationOut
    turns: list[ConversationTurnOut]
    #: The run this conversation seeded, if it has seeded one — the most recent,
    #: because a curator may commit a second direction from the same thread and
    #: the card at the bottom is about the last thing they did. This is what the
    #: commit card polls, and it is why committing never has to navigate.
    committed_run_id: str | None
    failure: str | None
    unanswered_turn_id: str | None


class ConversationListOut(BaseModel):
    """Every conversation, the most recently spoken in first."""

    conversations: list[ConversationOut]
    count: int


class Speak(BaseModel):
    """Something to say, or nothing — which asks again for the last answer.

    **Omitting the text is how a failed turn is retried, and that is what keeps a
    spend-triggering POST safe to press twice.** Retrying asks for the answer to
    the question already standing at the end of the thread rather than re-sending
    the question, so a thread whose last turn *was* answered has nothing to retry
    and is told so — which is exactly the case where the model was billed and the
    response was lost on the way back to the browser. The transcript closes the
    double-spend window, in place of an idempotency key a client would have to
    remember to send.
    """

    text: str | None = None


class CommitDirection(BaseModel):
    """The direction to search for, in the words the curator is committing to.

    Sent rather than derived on the server from the last turn's suggestions, for
    the reason the direct-intent box exists at all: what gets searched for is the
    curator's decision, and a commit button that sent something they had not read
    would be the wizard this flow is arranged to avoid.
    """

    intent: str


class ConversationDeletionOut(BaseModel):
    """What deleting a conversation destroyed, and what it left standing.

    **`description` is the response's point and the counts qualify it.** This is
    the one operation in the product that genuinely destroys a record, and the
    requirement is that the confirmation names a consequence — the ability to
    rebuild those judgments when the derivation improves, which is gone — rather
    than reporting how many rows moved.
    """

    conversation_id: str
    turns_deleted: int
    #: Judgments that kept their judgment and lost their derivation. Their rows
    #: are untouched but for `source_turn_id`, which is now null.
    affinities_detached: int
    #: Ledger entries that kept their amount and lost their citation. **No month
    #: total changes**, which is why these are detached rather than cascaded.
    spend_records_detached: int
    #: Searches this thread committed. They are untouched; what is gone is the
    #: record that this conversation is where they came from.
    runs_unattributed: int
    description: str


class AffinityOut(BaseModel):
    """One standing judgment about a thing the curator has reacted to.

    `sentiment` and `open_to_more` are two fields rather than one warmth score,
    because "meh on Magritte, but open to learning more" is two facts and a single
    scalar renders it as a low value indistinguishable from "never show me this
    again".
    """

    affinity_id: str
    #: One of the six shared vocabulary kinds — the same closed set a work's
    #: facets are recorded in, so that what a work *is* and what the curator
    #: *likes* can be matched at all.
    kind: str
    #: The thing itself, as it was named. A string and never a foreign key: the
    #: artists a conversation surfaces are the ones the curator could not have
    #: named, so most judgments are about a name this catalogue does not hold.
    value: str
    sentiment: str
    open_to_more: bool
    #: `stated`, `inferred` or `observed` — where the judgment came from, and the
    #: thing the Taste screen shows beside every row so a curator knows which
    #: claim they are arguing with.
    derivation: str
    #: The account of the judgment in the curator's terms. Null is normal for
    #: `stated`; required on the write path for the other two, where it is the
    #: only evidence a deleted conversation leaves behind.
    rationale: str | None
    #: The turn this was read out of, where one was cited and still exists.
    #: **Null on an `inferred` row whose conversation was deleted**, which is a
    #: legal state rather than a corruption.
    source_turn_id: str | None
    #: The thread that turn belongs to, resolved by the service rather than
    #: stored — the affinity cites a turn, and a turn already knows its
    #: conversation. This is what the Taste screen's way back to a judgment's
    #: provenance is addressed by; null exactly where `source_turn_id` is.
    conversation_id: str | None
    artist_id: str | None
    created_at: str
    updated_at: str


class AffinityListOut(BaseModel):
    """The whole taste, or whatever narrowing was asked for.

    Unpaged, deliberately: this is a household's entire taste, which is tens of
    rows, and a page over it would be a second way to read what one call hands
    back whole.
    """

    affinities: list[AffinityOut]
    count: int


class SetAffinity(BaseModel):
    """One judgment to write over whatever was there.

    Addressed by (`kind`, `value`) rather than by an id, because the thing being
    judged is a name in a sentence rather than a row anybody fetched — which is
    what makes this an upsert and not a create.

    `sentiment` and `open_to_more` are both required, with no default for either:
    the default that reads as safe — do not offer more — is the one that silently
    blacklists an artist the curator asked to keep hearing about.
    """

    kind: str
    value: str
    sentiment: str
    open_to_more: bool
    #: Defaults to `stated`, which is what the Taste screen's correction and every
    #: reaction in a thread are. `observed` is refused whoever sends it.
    derivation: str = "stated"
    rationale: str | None = None
    #: Required by the service when `derivation` is `inferred`, and meaningless
    #: otherwise: a curator saying a thing is the whole provenance.
    source_turn_id: str | None = None


class WorksFilter(BaseModel):
    """The narrowing `GET /api/works` takes, as a body: which works an act on a whole filter means.

    The same names and the same meanings as that route's query parameters, so
    *Select all* on Artworks acts on exactly the works the grid beside it is
    counting, including the ones not yet loaded. `sort` decides only the order
    the works are acted on in, which is the order a theme they join keeps.

    **An unknown key is refused, not dropped.** A narrowing added to the listing
    and not here would otherwise be ignored, and the act would reach more works
    than the grid shows.
    """

    model_config = ConfigDict(extra="forbid")

    q: str | None = None
    status: str | None = None
    artist_id: str | None = None
    theme: str | None = None
    sort: str | None = None
    artist: list[str] = []
    movement: list[str] = []
    era: list[str] = []
    subject: list[str] = []
    medium: list[str] = []
    palette: list[str] = []
    fit: list[str] = []
    not_on_wall: bool = False


class WorkSelection(BaseModel):
    """Which works an act on a selection is for: by id, or every work a filter matches.

    Exactly one of `artwork_ids` and `filter`. `except_ids` takes works out of a
    filter's set — the ones the curator unticked after *Select all*.
    """

    artwork_ids: list[str] | None = None
    filter: WorksFilter | None = None
    except_ids: list[str] = []


class ThemeAdditionOut(BaseModel):
    """What adding a selection to a theme did."""

    #: How many joined the theme now.
    added: int
    #: How many the theme already held, and so were passed over.
    already: int


class ThemeRemovalOut(BaseModel):
    """What taking a selection out of a theme did."""

    #: The ids that left, so a screen can take exactly those tiles away.
    removed: list[str]


class ArchivedWorksOut(BaseModel):
    """What archiving a selection did."""

    #: The ids archived now, so a screen can mark exactly those.
    archived: list[str]
    #: How many were archived already, and so were passed over.
    already: int
