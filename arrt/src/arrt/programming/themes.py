"""Themes, what each holds and in what order, what hangs on each wall, and *Not this one again*.

`Themes` is the curator's half of what the walls run on: the themes and their
membership, hanging a theme or a selection on a wall and taking it down, the
offer of a newly accepted work to its theme, and the works kept off every wall.
`DisplayService` (`display.py`) composes it and delegates to it; every surface
still calls `services.display`.

Every act here that changes a wall's feed publishes through the one
`FeedPublisher` the facade built, in its transaction (`feeds.py`). It asks the
Library about works only through `arrt.library.facade`.

Methods are synchronous, for the reason `catalogue.py` gives.
"""

import logging
import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from arrt.library.facade import (
    EventKind,
    LibraryFacade,
    PlayableWork,
    ProgrammingAct,
    Unplayable,
    UnplayableReason,
)
from arrt.persistence.records import (
    Theme,
    ThemeAssignment,
    ThemeMembership,
    Wall,
    WorkExclusion,
)
from arrt.programming.feeds import FeedPublisher
from arrt.programming.lookups import Lookups
from arrt.programming.manifest.builder import ManifestBuild
from arrt.programming.store import ProgrammingStore
from arrt.services.errors import ServiceError
from arrt.services.fields import require_member, require_text
from arrt.services.store import store_write

#: Named for the module these lines were said from before it had a module of its
#: own, and kept, for the reason `feeds.py` gives: a logger's name is what a
#: reader of the journal filters on.
log = logging.getLogger("arrt.programming.display")


class Unset:
    """ "The caller said nothing about this field", as distinct from "set it to null".

    A sentinel type rather than a `None` default, because `None` is a meaningful
    value for every field that takes this: no description, and "inherit the
    global default" for both rotation settings.
    """


UNSET: Final[Unset] = Unset()


@dataclass(frozen=True, slots=True)
class ThemeCount:
    """A theme as a filter option: how many of a given set of works it holds."""

    theme: Theme
    count: int
    #: The theme the listing is filtered by.
    selected: bool

    @property
    def disabled(self) -> bool:
        """True for a theme that would select nothing, unless it is the one chosen.

        The facet rule, applied to themes: a chosen option is never disabled,
        because the option itself is the control that turns it off.
        """
        return self.count == 0 and not self.selected


@dataclass(frozen=True, slots=True)
class ThemePlacement:
    """One theme and every wall showing it.

    Several walls, deliberately: hanging the same theme in two rooms requires no
    duplication, and a shape with room for one wall would have re-made the
    single-wall assumption one layer up from the boolean that was removed.
    """

    theme: Theme
    walls: Sequence[Wall]


@dataclass(frozen=True, slots=True)
class WorkPlacements:
    """Where one work is: the themes holding it, and whether it is kept off every wall."""

    themes: Sequence[ThemePlacement]
    exclusion: WorkExclusion | None


class NotAgainScope(StrEnum):
    """The one question *Not this one again* asks: how far the curator meant it."""

    #: Out of the theme hanging on this wall, and so off every wall hanging it.
    THEME = "theme"
    #: Off every wall, whatever hangs there, until allowed again. The work stays held.
    EVERY_WALL = "every_wall"


@dataclass(frozen=True, slots=True)
class NotAgain:
    """What *Not this one again* did: the theme the work left, or the exclusion now standing."""

    scope: NotAgainScope
    artwork_id: str
    wall_id: str
    #: The theme the work left, for `THEME`; None otherwise.
    left_theme: Theme | None = None
    #: The exclusion now standing, for `EVERY_WALL`; None otherwise.
    exclusion: WorkExclusion | None = None


class Themes:
    """Read and write the themes and their membership, what hangs where, and the works kept off every wall."""

    def __init__(self, store: ProgrammingStore, library: LibraryFacade, lookups: Lookups, feeds: FeedPublisher) -> None:
        self._store = store
        self._library = library
        #: The facade's one set of lookups (`lookups.py`).
        self._lookups = lookups
        #: The facade's one publisher: every act here that changes a feed opens its transaction.
        self._feeds = feeds

    # -- reads: themes --------------------------------------------------------

    def list_themes(self) -> Sequence[Theme]:
        """Return every theme."""
        return self._store.list_themes()

    def get_listed_theme(self, theme_id: str) -> Theme:
        """A theme a curator can name: any theme but a hung selection.

        A selection lives only as long as it hangs (`retire_selection`), so a
        Get that sent its works there, a default that pointed at it, a work
        added to it or a name given it would all be lost the day the wall
        changes. Each names a theme from a picker that never offers a
        selection; this refuses the id arriving another way. Taking a work out
        of one stays allowed: *Not this one again* does it on the wall's behalf.
        """
        theme = self._lookups.get_theme(theme_id)
        if theme.hidden:
            raise ServiceError(
                f"{theme.name!r} is the selection hanging on a wall, not a theme, so it cannot be renamed, "
                "made the default, or have works sent or added to it. Choose a theme from Themes."
            )
        return theme

    def default_theme(self) -> Theme | None:
        """The theme new works join, or None while the curator has marked none."""
        return self._store.get_default_theme()

    # -- reads: walls and what hangs on them -----------------------------------

    def walls_hanging(self, theme_id: str) -> Sequence[Wall]:
        """Every wall showing this theme, in the order walls are listed.

        Several, deliberately: two walls may hang the same theme and that
        requires no duplication, which is the property the old boolean could not
        have. This is what the delete refusal counts and what it names.
        """
        hung = {assignment.wall_id for assignment in self._store.list_assignments() if assignment.theme_id == theme_id}
        # Keyed off the wall listing rather than off the assignment order, so the
        # walls come back in the order every other surface shows them in.
        return [wall for wall in self._store.list_walls() if wall.id in hung]

    def survey_themes(self) -> Sequence[ThemePlacement]:
        """Every theme with every wall showing it.

        One pass over the assignments rather than one lookup per theme: the
        question "where is each of these hanging" is asked about the whole list
        every time it is asked at all.
        """
        walls = {wall.id: wall for wall in self._store.list_walls()}
        hung: dict[str, list[str]] = {}
        for assignment in self._store.list_assignments():
            hung.setdefault(assignment.theme_id, []).append(assignment.wall_id)
        return [
            ThemePlacement(
                theme=theme,
                # Ordered by the wall listing so every surface names walls the
                # same way round, whatever order the assignments came back in.
                walls=[wall for wall in walls.values() if wall.id in set(hung.get(theme.id, ()))],
            )
            # A selection is not a theme the curator made, so the Themes index
            # leaves it out; the wall it hangs on is where it is seen.
            for theme in self._store.list_themes()
            if not theme.hidden
        ]

    def theme_counts(self, work_ids: Iterable[str], *, selected: str | None = None) -> Sequence[ThemeCount]:
        """Every theme, by name, with how many of `work_ids` it holds.

        The ids are the Library's answer to "which works does this filter
        select", taken as opaque references: Artworks' *Filter* rail prints each
        theme's count beside it and disables a theme that would select nothing,
        as it does a facet value. One read scope, so the counts agree with one
        another; they cannot share a scope with the Library's read that produced
        the ids, which is the price of the seam.
        """
        among = set(work_ids)
        with self._store.reading():
            return [
                ThemeCount(
                    theme=theme,
                    count=sum(1 for membership in self._store.list_memberships(theme.id) if membership.artwork_id in among),
                    selected=theme.id == selected,
                )
                for theme in self._store.list_themes()
                # A selection is no filter a curator would look for, unless it
                # is the one they followed a link to.
                if not theme.hidden or theme.id == selected
            ]

    def work_ids_on_walls(self) -> frozenset[str]:
        """The ids of every work some wall plays now, through the theme or selection hanging there.

        What Artworks' *Not on any wall* facet leaves out (the owner's ruling of
        2026-10-08 on #288): a work is on a wall when a theme or selection
        hanging on one holds it and it is not kept off every wall. **Not what a
        wall has shown**, which is `last_shown_by_work`'s, from the Players'
        reports. Nor is it readiness: a held work a wall would skip for want of a
        render still counts as on it, since the curator's act — hanging the
        theme — is what this answers for.

        Ids, opaque to Programming, for the bindings to hand the Library, as
        `theme_work_ids` are. One read scope.
        """
        with self._store.reading():
            hung = {assignment.theme_id for assignment in self._store.list_assignments()}
            kept_off = {exclusion.artwork_id for exclusion in self._store.list_exclusions()}
            playing = {membership.artwork_id for theme_id in hung for membership in self._store.list_memberships(theme_id)}
        return frozenset(playing - kept_off)

    def theme_work_ids(self, theme_id: str) -> Sequence[str]:
        """The ids of the theme's works, in curated order.

        Ordered because the entries carry a curator's placement; the ones nobody
        placed follow the ones somebody did. **Ids and not works**, because what a
        work *is* is the Library's to say: a surface listing a theme resolves
        these through the Library, which is the composition the bindings are
        allowed to do and this service is not.
        """
        with self._store.reading():
            self._lookups.get_theme(theme_id)
            return [membership.artwork_id for membership in self._store.list_memberships(theme_id)]

    # -- writes: themes and membership ----------------------------------------

    def add_theme(self, *, name: str, description: str | None = None) -> Theme:
        """Record a theme and return it.

        **It hangs nowhere.** A theme is created globally and hanging it is a
        separate act — `activate_theme` — because with more than one wall there
        is no wall a new theme could be put on without the curator having chosen
        one. This method arrived active-if-none-else-is, which was the same
        automatic promotion `reconcile` did and is dropped for the same reason.
        """
        theme = Theme(
            id=str(uuid.uuid4()),
            name=require_text(name, field="name"),
            created_at=datetime.now(UTC),
            description=description,
        )
        store_write(self._store.add_theme, theme)
        return theme

    def make_default(self, theme_id: str) -> Theme:
        """Make this the theme new works join, taking the mark off whichever had it.

        **Only works accepted from now on join it.** Every work already in the
        catalogue has been offered to the default once, whatever was the default
        then, and marking a theme is not a request to fill it with everything
        accepted before; a curator who wants that adds them from Library › Works.
        """
        # The check, the mark and the theme returned in one transaction: a theme
        # deleted between a check and its mark was refused in the store's words,
        # with nothing a curator could act on.
        with self._store.transaction():
            self.get_listed_theme(theme_id)
            store_write(self._store.mark_default_theme, theme_id)
            return self._lookups.get_theme(theme_id)

    def offer_destinations(self, work_ids: Iterable[str]) -> Sequence[str]:
        """Offer each work the theme it was accepted into, once, and return the ones that joined.

        **Where a work goes is the Library's to say and this service's to
        apply.** The facade answers, for each work, the theme its Get named, or
        None. None means the default theme, the owner's ruling 8: what is
        accepted lands there, at the end of its order. A named theme takes the
        default's place, so a work the curator sent somewhere else never enters
        the everyday rotation (ruling 5a, as the owner recast it on 2026-10-02).

        **A named theme that has since been deleted is joined by nothing.** The
        curator chose "not the rotation" when they started the Get, and deleting
        the theme does not reverse that. The work is recorded as offered all the
        same, so the next start does not sweep it into the default either, and
        the log says which work and which theme.

        **Once per work, ever**, and that is what the offer record is for: the
        Library announces a restored work as accepted, exactly as it announces a
        new one, and startup offers every accepted work with no offer recorded.
        Without the record either would put back a work the curator took out of
        its theme by hand. A work offered while no theme was the default is
        recorded too, so marking one later does not sweep in everything accepted
        before it.

        A work already in its theme, placed there by hand before its
        announcement arrived, is recorded and left where the curator put it.
        Offer and membership commit together, so a work is never recorded as
        offered without having joined, or joined without the record that stops a
        second join.

        **Nothing is published here.** A work is offered when it is accepted,
        before it is prepared, so it has nothing a feed could send yet: the
        announcement of its master puts it on any wall hanging its theme, and
        failing that the next roll does (`FeedPublisher.roll_v2`).
        """
        already = self._store.offered_work_ids()
        unoffered = [work_id for work_id in dict.fromkeys(work_ids) if work_id not in already]
        if not unoffered:
            return []
        # Asked before the transaction, and once for every work: the facade is
        # written as if remote, so it is one coarse question, never one per work
        # and never with the store's lock held.
        destinations = self._library.destinations(unoffered)
        joined: list[str] = []
        joined_by_theme: Counter[str] = Counter()
        vanished: list[tuple[str, str]] = []
        with self._store.transaction():
            default = self._store.get_default_theme()
            offered = self._store.offered_work_ids()
            for work_id in unoffered:
                if work_id in offered:
                    continue
                named = destinations[work_id]
                target = default if named is None else self._store.get_theme(named)
                if named is not None and target is None:
                    vanished.append((work_id, named))
                if target is not None and self._store.get_membership(target.id, work_id) is None:
                    self._insert(theme_id=target.id, artwork_id=work_id, position=None)
                    joined.append(work_id)
                    joined_by_theme[target.name] += 1
                store_write(self._store.record_offer, work_id, datetime.now(UTC))
        for name, count in joined_by_theme.items():
            log.info("Added %d newly accepted work(s) to theme %r.", count, name)
        for work_id, theme_id in vanished:
            # Said out loud, because the work is now in no theme at all, which is
            # exactly what the curator would come looking for.
            log.warning(
                "Work %s was accepted from a Get that named theme %s, which has since been deleted. "
                "It joins no theme, and not the default either; add it to one from Library › Works.",
                work_id,
                theme_id,
            )
        return joined

    def catch_up_offers(self) -> Sequence[str]:
        """Offer every accepted work that was never offered the theme it was accepted into. Run at start.

        For an announcement lost between the Library's commit and Programming's
        handler. It goes through `offer_destinations`, so a work whose
        announcement was lost lands where a delivered one would. Every work the
        catalogue held before the default existed was recorded as offered when
        the file was migrated, so this finds only what a crash dropped.
        """
        return self.offer_destinations(self._library.accepted_work_ids())

    def activate_theme(self, theme_id: str, *, wall_id: str) -> ManifestBuild:
        """Hang this theme on this wall, and publish what follows.

        **The wall is named even while there is one and the answer is obvious.**
        A confirmation that reads correctly today only because there is one
        possible target is a sentence that silently becomes wrong the day a
        second display arrives, and this is the call every such sentence is built
        from.

        **Hanging rewrites the manifest**, so switching themes changes the wall
        rather than arming a later `sync`. A curator who chose a theme and found
        the wall unchanged would reasonably conclude the product was broken, and
        the two-step alternative exists only as an artefact of how the operations
        decompose.

        **Here, the switch is a file rewrite**: the server writes the wall's feed
        and nothing else. What it costs at the wall is the Player's: it reads the
        feed on its next poll and fetches, or for a Frame uploads to the
        television, any work of the new theme it does not hold, which can take a
        while. Nothing here writes to a television.

        It returns the build, not the theme, because the theme alone cannot say
        how much of itself reached the wall — and a switch that silently put up
        four of a theme's twelve works is the failure this report exists for.
        """
        # One act around the hang, the publish and the retirement, and it holds
        # both ways (`FeedPublisher.publishing`). A feed that cannot be written takes the hang
        # back: recording the hang and then failing to publish left the
        # catalogue naming a theme the wall was not showing, with nothing to say
        # the two disagreed. And a step after the publish that raises (the
        # selection replaced cannot be retired) writes no feed, so the walls do
        # not show a hang the catalogue rolled back. The theme, the wall and what
        # it replaces are read inside, so a theme deleted meanwhile is refused in
        # this service's words and a hang made meanwhile is the one retired.
        with self._feeds.publishing():
            self._lookups.get_theme(theme_id)
            self._lookups.get_wall(wall_id)
            replaced = self._store.get_assignment(wall_id)
            store_write(
                self._store.set_assignment,
                ThemeAssignment(wall_id=wall_id, theme_id=theme_id, assigned_at=datetime.now(UTC)),
            )
            build = self._feeds.sync(wall_id)
            self.retire_selection(replaced)
        self._record_hang(build)
        return build

    def hang_selection(self, artwork_ids: Sequence[str], *, wall_id: str) -> ManifestBuild:
        """Hang these works on this wall, until something else is hung there.

        **A selection is stored as a theme with the hidden flag**, made here and
        holding these works in the order given, so the feed and readiness work
        on it exactly as on any theme. It is left off the
        Themes index and the theme pickers, because the curator chose works, not
        a theme, and would not recognise it in a list of theirs.

        Every id has to name a work the Library holds, and the whole hang is
        refused otherwise, in the catalogue's words. A work the Library holds
        but will not show is hung all the same and named in the build's
        exclusions, as hanging a theme does, so the curator learns why the wall
        is short rather than finding the act refused.
        """
        chosen = list(dict.fromkeys(artwork_ids))
        if not chosen:
            raise ServiceError("A selection needs at least one work to hang.")
        now = datetime.now(UTC)
        theme_id = str(uuid.uuid4())
        # One act, the wall and what it replaces read inside it, as `activate_theme`
        # says, and the Library asked there too, in the order the refusals have
        # always come in, as the build inside the act asks it.
        with self._feeds.publishing():
            wall = self._lookups.get_wall(wall_id)
            # One question for every work, as the manifest build asks it: the facade
            # is written as if remote.
            for answer in self._library.playable(chosen).values():
                if not isinstance(answer, PlayableWork) and answer.reason is UnplayableReason.NOT_IN_CATALOGUE:
                    raise ServiceError(answer.detail)
            theme = Theme(
                id=theme_id,
                # Names are unique across themes, hidden or not, so the id's head
                # keeps two selections for one wall apart.
                name=f"Selection for {wall.name} ({theme_id[:8]})",
                created_at=now,
                hidden=True,
            )
            replaced = self._store.get_assignment(wall_id)
            store_write(self._store.add_theme, theme)
            for position, artwork_id in enumerate(chosen):
                store_write(
                    self._store.add_membership,
                    ThemeMembership(theme_id=theme_id, artwork_id=artwork_id, added_at=now, position=position),
                )
            store_write(self._store.set_assignment, ThemeAssignment(wall_id=wall_id, theme_id=theme_id, assigned_at=now))
            build = self._feeds.sync(wall_id)
            self.retire_selection(replaced)
        self._record_hang(build)
        return build

    # -- writes: not this one again -------------------------------------------

    def not_this_one_again(self, artwork_id: str, *, wall_id: str, scope: NotAgainScope | str) -> NotAgain:
        """The Walls card's *Not this one again*, answered *from this theme* or *from every wall*.

        One method for both answers, so a click and an agent asking the same
        question reach the same act; each answer is its own method below.
        """
        resolved = require_member(scope, enum=NotAgainScope, field="scope")
        if resolved is NotAgainScope.THEME:
            left = self.leave_theme(artwork_id, wall_id=wall_id)
            return NotAgain(scope=resolved, artwork_id=artwork_id, wall_id=wall_id, left_theme=left)
        exclusion = self.exclude_work(artwork_id, wall_id=wall_id)
        return NotAgain(scope=resolved, artwork_id=artwork_id, wall_id=wall_id, exclusion=exclusion)

    def leave_theme(self, artwork_id: str, *, wall_id: str) -> Theme:
        """*Not this one again*, from this theme: take the work out of what hangs on this wall.

        The work leaves the theme, so it leaves every wall hanging that theme,
        and the published feeds of those walls lose it now rather than at the
        next sync: a curator who said "not this one" and saw it again a minute
        later would conclude the act did nothing. A wall showing it now starts
        fresh. Nothing else changes, on any wall: no work arrives with the
        patch, and the work stays held and in every other theme.

        Returns the theme it left, so the answer can say which.
        """
        # Read inside, so the theme it leaves is the one hanging when it leaves.
        with self._feeds.publishing():
            wall = self._lookups.get_wall(wall_id)
            theme = self._lookups.require_hanging(wall)
            if self._store.get_membership(theme.id, artwork_id) is None:
                raise ServiceError(
                    f"Artwork {artwork_id!r} is not in {theme.name!r}, which is what hangs on {wall.name!r}, "
                    "so there is nothing to take it out of."
                )
            store_write(self._store.remove_membership, theme.id, artwork_id)
            walls = self.walls_hanging(theme.id)
            self._feeds.withdraw(artwork_id, [hung.id for hung in walls], cause="leaving its theme")
        self._record_left(theme, [artwork_id], walls)
        return theme

    def exclude_work(self, artwork_id: str, *, wall_id: str | None = None) -> WorkExclusion:
        """*Not this one again*, from every wall: keep the work off every wall until it is allowed again.

        **Not Archive.** The work stays in the Library and in every theme that
        holds it; what changes is that no feed carries it. Every published feed
        loses it now, for the reason `leave_theme` gives.

        `wall_id` is the wall the curator was looking at, recorded in the
        history so that wall's history shows the act. It changes nothing else.
        """
        # Checked inside the act, so a second *Not this one again* landing
        # meanwhile is told so rather than refused by the file.
        with self._feeds.publishing():
            self._require_held(artwork_id)
            looking_at = self._lookups.get_wall(wall_id) if wall_id is not None else None
            if any(exclusion.artwork_id == artwork_id for exclusion in self._store.list_exclusions()):
                raise ServiceError(f"Artwork {artwork_id!r} is already kept off every wall.")
            exclusion = WorkExclusion(artwork_id=artwork_id, excluded_at=datetime.now(UTC))
            store_write(self._store.add_exclusion, exclusion)
            self._feeds.withdraw(artwork_id, [wall.id for wall in self._store.list_walls()], cause="being kept off every wall")
        self._library.record(
            ProgrammingAct(
                kind=EventKind.EXCLUDED,
                wall_id=wall_id,
                work_id=artwork_id,
                # Named for the reason `leave_theme` names it.
                detail={"wall_name": looking_at.name} if looking_at else {},
            )
        )
        return exclusion

    def allow_work(self, artwork_id: str) -> None:
        """Undo *Not this one again* from every wall: the work may go on walls again.

        Every wall whose hung theme holds it gets it back now, if the Library
        will show it (`reconcile`, the owner's ruling of 2026-10-10).
        """
        # Checked inside the act, so of two allows landing together one allows
        # and the other is told there is nothing to allow.
        with self._feeds.publishing():
            if not any(exclusion.artwork_id == artwork_id for exclusion in self._store.list_exclusions()):
                raise ServiceError(f"Artwork {artwork_id!r} is not kept off the walls, so there is nothing to allow.")
            store_write(self._store.remove_exclusion, artwork_id)
            self._feeds.reconcile([artwork_id], cause="being allowed back")
        self._library.record(ProgrammingAct(kind=EventKind.ALLOWED, work_id=artwork_id))

    def excluded_works(self) -> Sequence[WorkExclusion]:
        """Every work kept off every wall, oldest first."""
        return self._store.list_exclusions()

    def placements_of(self, artwork_id: str) -> WorkPlacements:
        """Every theme holding this work, with the walls hanging each, and whether it is kept off every wall.

        **Selections included.** A hidden theme is how one work hangs on a wall
        by itself, so leaving them out would hide the very hang the Work page
        exists to show; the caller decides which of them a curator would
        recognise. Read in one scope, so the themes, the walls and the exclusion
        describe one instant.
        """
        with self._store.reading():
            walls = list(self._store.list_walls())
            hung: dict[str, set[str]] = {}
            for assignment in self._store.list_assignments():
                hung.setdefault(assignment.theme_id, set()).add(assignment.wall_id)
            themes = [
                ThemePlacement(theme=theme, walls=[wall for wall in walls if wall.id in hung.get(theme.id, ())])
                for theme in self._store.list_themes()
                if any(membership.artwork_id == artwork_id for membership in self._store.list_memberships(theme.id))
            ]
            exclusion = next((kept for kept in self._store.list_exclusions() if kept.artwork_id == artwork_id), None)
        return WorkPlacements(themes=themes, exclusion=exclusion)

    def clear_wall(self, wall_id: str) -> None:
        """Take down whatever is hanging, leaving the wall holding nothing.

        The inverse of `activate_theme`, and the operation that keeps a theme
        deletable: the delete refusal below is absolute about a theme that hangs
        somewhere, so without a way to take one down a curator could never empty
        the catalogue.

        **It deliberately does not rewrite the feed.** The wall keeps showing
        what it was showing, which is the same posture as curation being stopped
        entirely and the same one deleting the last theme already had. Publishing
        an empty feed would blank the wall as a side effect of tidying up.
        """
        # Read inside, so a hang made meanwhile is the one taken down and retired.
        with self._store.transaction():
            wall = self._lookups.get_wall(wall_id)
            assignment = self._store.get_assignment(wall_id)
            if assignment is None:
                raise ServiceError(f"Nothing is hanging on wall {wall_id!r}, so there is nothing to take down.")
            taken_down = self._lookups.get_theme(assignment.theme_id)
            store_write(self._store.remove_assignment, wall_id)
            self.retire_selection(assignment)
        # The only operation in Programming that deliberately leaves the catalogue
        # and the wall disagreeing for an unbounded time, so it is the one an
        # operator asking "why is the set showing a theme that hangs nowhere"
        # comes to the journal for. `sync`'s two lines are the precedent: what a
        # wall shows changing is worth a line, and this is the change that
        # writes no manifest to record it anywhere else.
        log.info(
            "Took theme %r down from wall %r. The wall goes on showing it until a theme is hung.",
            taken_down.name,
            wall.name,
        )

    def add_to_theme(self, *, theme_id: str, artwork_id: str, position: int | None = None) -> ThemeMembership:
        """Put a work in a theme, at a place in the order or at the end of it.

        **`position` is an index here for the same reason it is one on a move**,
        and saying nothing means the end rather than nowhere. Ruled by the
        operator on 2026-08-12, when the two had drifted apart: an add wrote the
        number it was handed into the column as a sort key while a move had
        become an index, so one MCP parameter description was covering two
        meanings — and, worse, every work added through a screen or a tool came
        out *unplaced*, because nothing a curator touches sends a number. The
        list a surface renders is placed-then-unplaced; the list a move renumbers
        was the placed ones alone. Two different lists, indexed against each
        other, which is a reorder that does nothing or moves the work the way it
        was not asked to go.

        Making an add place the work is what collapses them into one list, for
        every caller rather than for the one screen that noticed. `position=None`
        on a *move* still means unplaced — that is a curator saying they have no
        opinion, which is a thing to be able to say; an add has no opinion to
        express yet, and the end of the order is where a work with nothing said
        about it goes.

        The insert renumbers what it displaces, in one transaction: writing the
        number and stopping is what left two rows tied on a position with
        `added_at` picking the winner, and an add can produce that tie exactly as
        a move could.

        **A wall hanging the theme gets the work at once**, if the Library will
        show it (`reconcile`, the owner's ruling of 2026-10-10).
        """
        # The theme read inside the act that adds to it, so a theme deleted
        # meanwhile is refused in this service's words, not the file's.
        with self._feeds.publishing():
            self.get_listed_theme(theme_id)
            self._require_held(artwork_id)
            target = self._require_position(position)
            membership = self._insert(theme_id=theme_id, artwork_id=artwork_id, position=target)
            self._feeds.reconcile([artwork_id], cause="joining its theme")
        return membership

    def _insert(self, *, theme_id: str, artwork_id: str, position: int | None) -> ThemeMembership:
        """Write the membership at `position` (the end for None), renumbering what it displaces. Publishes nothing."""
        membership = ThemeMembership(theme_id=theme_id, artwork_id=artwork_id, added_at=datetime.now(UTC), position=None)
        with self._store.transaction():
            others = list(self._store.list_memberships(theme_id))
            index = len(others) if position is None else min(position, len(others))
            self._renumber([*others[:index], membership, *others[index:]], new=membership)
        return replace(membership, position=index)

    def add_works_to_theme(self, *, theme_id: str, artwork_ids: Sequence[str]) -> tuple[int, int]:
        """Put many works at the end of a theme's order, in the order given, in one transaction.

        Answers how many joined and how many the theme already held. A work
        already in the theme is passed over rather than refused, unlike
        `add_to_theme`: a selection made by a filter routinely holds some, and
        refusing the act for them would make *Add to theme* on a whole filter
        fail exactly when it is most useful.

        **One renumber, not one per work.** `add_to_theme` renumbers the whole
        theme on every insert, which over a few thousand works is millions of
        row writes. Here the existing order is made dense once and the newcomers
        are written after it, which is the same order a loop of single adds
        would leave, reached in one pass.

        Every id has to name a work the Library holds, asked of the facade in
        one question, and the whole act is refused otherwise, in the catalogue's
        words — so nothing is half-added. Walls hanging the theme get what
        joined, once, as `add_to_theme` says.
        """
        chosen = list(dict.fromkeys(artwork_ids))
        now = datetime.now(UTC)
        # The theme read inside, as `add_to_theme` says.
        with self._feeds.publishing():
            self.get_listed_theme(theme_id)
            for answer in self._library.playable(chosen).values():
                if not isinstance(answer, PlayableWork) and answer.reason is UnplayableReason.NOT_IN_CATALOGUE:
                    raise ServiceError(answer.detail)
            others = list(self._store.list_memberships(theme_id))
            held = {membership.artwork_id for membership in others}
            joining = [artwork_id for artwork_id in chosen if artwork_id not in held]
            self._renumber(others)
            for place, artwork_id in enumerate(joining, start=len(others)):
                store_write(
                    self._store.add_membership,
                    ThemeMembership(theme_id=theme_id, artwork_id=artwork_id, added_at=now, position=place),
                )
            if joining:
                self._feeds.reconcile(joining, cause="joining its theme")
        return len(joining), len(chosen) - len(joining)

    def remove_works_from_theme(self, *, theme_id: str, artwork_ids: Sequence[str]) -> Sequence[str]:
        """Take many works out of a theme in one transaction, and answer which left.

        A work the theme does not hold is passed over: the selection was made
        by a filter, and the theme is what it is now. The order left behind is
        not renumbered, as a single removal does not renumber it. Walls hanging
        the theme lose what left, as `remove_from_theme` says.
        """
        removed: list[str] = []
        with self._feeds.publishing():
            theme = self._lookups.get_theme(theme_id)
            for artwork_id in dict.fromkeys(artwork_ids):
                if self._store.get_membership(theme_id, artwork_id) is None:
                    continue
                store_write(self._store.remove_membership, theme_id, artwork_id)
                removed.append(artwork_id)
            walls = self.walls_hanging(theme_id)
            for wall in walls:
                self._feeds.withdraw_v2(wall.id, set(removed), cause="leaving its theme")
        self._record_left(theme, removed, walls)
        return removed

    def move_in_theme(self, *, theme_id: str, artwork_id: str, position: int | None) -> ThemeMembership:
        """Move a work to a place in the curated order, or return it to unplaced.

        **`position` is an index into the order, not a value written to a
        column** — the work ends up *at* that place and the works around it are
        renumbered to make room. Writing the number and stopping there is what
        this replaced, and it made the ordinary move silently do nothing:
        `list_memberships` breaks a tie on `added_at`, so a work sent from
        position 0 to position 1 landed level with the work already there and
        sorted ahead of it again, being the older row. Moving a work *up* worked
        and moving it *down* did not, which is the shape a defect takes when
        nothing renumbers — and the Theme screen's ↓ button had never once
        reordered anything.

        The renumber leaves the order dense from zero, so the index a surface
        reads off the list it was given is the index it can send back. An index
        past the end lands at the end rather than being refused: the list a
        curator is looking at is the one they are moving within, and there is no
        wrong answer to "put this last" worth a refusal.

        **The whole list is renumbered, not the placed part of it.** `theme_work_ids`
        hands a surface the placed works and then the unplaced ones as one list,
        and a surface can only index against what it was handed — so renumbering
        the placed subset alone made the index mean something the sender never
        meant. Anything sitting unplaced therefore acquires the place it was
        already being shown at, which changes no order anybody can see.

        **Unplaced is still a real destination**, and it is not the same as last.
        `None` means the curator has said nothing about where this work goes;
        `theme_work_ids` puts those after the placed ones, and returning a work to
        it renumbers what is left rather than leaving a hole in the sequence.

        One transaction, and the read of the order is inside it: a partial
        renumber is an order no curator asked for and no error message would
        describe, and an order read before the lock is one another move may
        already have replaced.
        """
        target = self._require_position(position)
        with self._store.transaction():
            membership = self._store.get_membership(theme_id, artwork_id)
            if membership is None:
                raise ServiceError(f"Artwork {artwork_id!r} is not in theme {theme_id!r}.")
            # Everything else, in the order a surface would have been handed it.
            others = [entry for entry in self._store.list_memberships(theme_id) if entry.artwork_id != artwork_id]
            if target is None:
                moved = replace(membership, position=None)
                self._renumber(others)
                # The moved row is not in that list, so nothing above writes it.
                store_write(self._store.update_membership, moved)
            else:
                index = min(target, len(others))
                self._renumber([*others[:index], membership, *others[index:]])
                moved = replace(membership, position=index)
        return moved

    def _renumber(self, order: Sequence[ThemeMembership], *, new: ThemeMembership | None = None) -> None:
        """Write a theme's entries out as dense positions from zero.

        Dense is what makes an index a round trip: a gap or a repeat still reads
        as a sensible order for a while and then loses a tie to `added_at`, which
        looks like a move that did nothing rather than like a corrupted sequence.

        `new` is the one entry that has never been stored, told apart by identity
        rather than by id because a duplicate add puts *two* entries here with the
        same `artwork_id` — the row already in the theme and the row being added.
        Either match refuses that add, since one of the two inserts always
        collides; identity is used because it describes which row is meant rather
        than relying on the refusal to make the ambiguity moot. Callers hold this
        inside a transaction, which is what turns that refusal into a rollback
        rather than a half-renumbered order.
        """
        for place, entry in enumerate(order):
            if entry is new:
                store_write(self._store.add_membership, replace(entry, position=place))
            elif entry.position != place:
                store_write(self._store.update_membership, replace(entry, position=place))

    def remove_from_theme(self, *, theme_id: str, artwork_id: str) -> None:
        """Take a work out of a theme. The work itself is untouched.

        Walls hanging the theme lose it now, as *Not this one again* from the
        theme takes it off (`leave_theme`): the feed follows the hung theme both
        ways, or a restart, which publishes what the theme lacks, would be the
        only thing that moved the wall.
        """
        # Checked inside the act, so of two removals landing together one
        # removes and the other is told the work is not there.
        with self._feeds.publishing():
            if self._store.get_membership(theme_id, artwork_id) is None:
                raise ServiceError(f"Artwork {artwork_id!r} is not in theme {theme_id!r}.")
            # A membership names a theme the store holds, so this finds it.
            theme = self._lookups.get_theme(theme_id)
            store_write(self._store.remove_membership, theme_id, artwork_id)
            walls = self.walls_hanging(theme_id)
            self._feeds.withdraw(artwork_id, [wall.id for wall in walls], cause="leaving its theme")
        self._record_left(theme, [artwork_id], walls)

    def update_theme(
        self,
        theme_id: str,
        *,
        name: str | None = None,
        description: str | Unset | None = UNSET,
    ) -> Theme:
        """Change a theme's name or description.

        The description takes a sentinel rather than defaulting to `None`,
        because `None` is a meaningful value — "no description" — and a caller
        changing only the name would otherwise silently clear it.
        """
        # The row read inside the transaction that writes it back whole, so a
        # description, a name or the default's mark written meanwhile is kept.
        with self._store.transaction():
            theme = self.get_listed_theme(theme_id)
            updated = replace(
                theme,
                name=theme.name if name is None else require_text(name, field="name"),
                description=theme.description if isinstance(description, Unset) else description,
            )
            store_write(self._store.update_theme, updated)
        return updated

    def delete_theme(self, theme_id: str) -> None:
        """Remove a theme and its membership rows. The works themselves are untouched.

        **A theme hanging on any wall is refused**, and the count that matters is
        walls rather than themes: a theme hung in three rooms is three rooms that
        lose their picture, so "it is the only theme" is not a reason to permit
        it. The curator hangs something else, or takes it down, and then deletes
        — either way what happens to those walls is a choice.

        This generalises a narrower rule. Until 2026-08-12 the refusal was "the
        active theme, while another theme exists", and the last theme was
        deletable *even while active* because there was no way to take one down
        and a curator has to be able to empty the catalogue. `clear_wall` is that
        way, which is what lets this be absolute.

        **A deletion that is permitted does not rewrite any manifest.** A theme
        that hangs nowhere is on no wall to take a picture off, and a wall whose
        theme was taken down keeps showing what it was showing — the same posture
        as the server being stopped entirely: a Player runs off the last
        manifest indefinitely, and that is normal operation rather than
        degradation. Publishing an empty manifest instead would blank the wall as
        a side effect of tidying up the catalogue.
        """
        # Both refusals decided inside the transaction that deletes, so a theme
        # hung or made the default meanwhile is refused, not deleted under a wall.
        with self._store.transaction():
            theme = self._lookups.get_theme(theme_id)
            if theme.is_default:
                raise ServiceError(
                    f"Theme {theme.name!r} is the default, which new works join, so it cannot be deleted. "
                    "Make another theme the default first, and then delete this one."
                )
            hanging = self.walls_hanging(theme_id)
            if hanging:
                where = ", ".join(repr(wall.name) for wall in hanging)
                raise ServiceError(
                    f"Theme {theme.name!r} is hanging on {where}. Hang another theme there first, or take this one "
                    "down, so that what those walls show next is a choice rather than whatever was on them before."
                )
            for membership in self._store.list_memberships(theme_id):
                store_write(self._store.remove_membership, theme_id, membership.artwork_id)
            store_write(self._store.remove_theme, theme_id)

    # -- internals ------------------------------------------------------------

    def retire_selection(self, replaced: ThemeAssignment | None) -> None:
        """Delete the selection a wall stopped hanging, if no other wall still hangs it.

        A selection is made for one hang and has no name a curator chose, so
        once nothing hangs it nobody can find it to hang again, and keeping it
        would leave one hidden theme behind per hang for good. History does not
        need the row: a hang event carries the selection's name and id itself.
        Called inside the caller's transaction, after the new assignment is
        written, so `walls_hanging` already sees the wall as moved on.
        """
        if replaced is None:
            return
        theme = self._store.get_theme(replaced.theme_id)
        if theme is None or not theme.hidden or self.walls_hanging(theme.id):
            return
        for membership in self._store.list_memberships(theme.id):
            store_write(self._store.remove_membership, theme.id, membership.artwork_id)
        store_write(self._store.remove_theme, theme.id)

    def _record_left(self, theme: Theme, artwork_ids: Sequence[str], walls: Sequence[Wall]) -> None:
        """Tell each wall's history that these works left the theme it hangs, once the removal has committed.

        **One line per work for every wall the theme hangs on, whichever way
        the work left**: *Not this one again* from the theme, a theme's Remove,
        a selection removed from a theme. Each of those walls lost the work, so
        each wall's history says so; a theme hanging nowhere is in no wall's
        history, and says nothing. The one place these lines are written, so
        no way of taking a work out of a theme is the one that forgets to.
        After the commit, as `LibraryFacade.record` requires; `walls` was read
        inside the removal's transaction.
        """
        for wall in walls:
            for artwork_id in artwork_ids:
                self._library.record(
                    ProgrammingAct(
                        kind=EventKind.LEFT_THEME,
                        wall_id=wall.id,
                        theme_id=theme.id,
                        work_id=artwork_id,
                        # The wall's name too, as a hang carries it: a history
                        # outlives the wall it names, and once that wall is
                        # deleted this is the only place its name is kept.
                        detail={"theme_name": theme.name, "selection": theme.hidden, "wall_name": wall.name},
                    )
                )

    def _record_hang(self, build: ManifestBuild) -> None:
        """Tell the Library's history what was hung where, once the hang has committed."""
        self._library.record(
            ProgrammingAct(
                kind=EventKind.HUNG,
                wall_id=build.wall.id,
                theme_id=build.theme.id,
                detail={
                    "theme_name": build.theme.name,
                    "selection": build.theme.hidden,
                    "works": build.considered,
                    "wall_name": build.wall.name,
                },
            )
        )

    def require_showable(self, artwork_id: str) -> PlayableWork:
        """The work, if a wall may be told to show it by hand: displayable, and not kept off every wall.

        Show now and a scene's pin ask the same question, so they refuse in the
        same words.
        """
        answer = self._require_held(artwork_id)
        if not isinstance(answer, PlayableWork):
            raise ServiceError(f"Artwork {artwork_id!r} cannot be shown on the wall: {answer.detail}")
        if any(exclusion.artwork_id == artwork_id for exclusion in self._store.list_exclusions()):
            raise ServiceError(f"Artwork {answer.title!r} is kept off every wall. Allow it again from its page first.")
        return answer

    def _require_held(self, artwork_id: str) -> PlayableWork | Unplayable:
        """The Library's answer about one work, refusing an id it does not hold.

        Refused in the catalogue's own words, so a curator adding an unknown id to
        a theme hears what they would have heard before the facade existed.
        """
        answer = self._library.playable([artwork_id])[artwork_id]
        if not isinstance(answer, PlayableWork) and answer.reason is UnplayableReason.NOT_IN_CATALOGUE:
            raise ServiceError(answer.detail)
        return answer

    @staticmethod
    def _require_position(position: int | None) -> int | None:
        if position is not None and position < 0:
            raise ServiceError(f"A position cannot be negative, got {position}.")
        return position
