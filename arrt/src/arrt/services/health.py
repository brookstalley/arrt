"""Everything the health panel states, composed once, in one call.

**This is the product's only alerting surface.** The operator chose it as such in
2026-07-20 — no push, no email, no external monitor — and the consequence was
recorded honestly rather than left implicit: mean time to detection is bounded by
how often the curator opens the page. What follows from that is the rule this
module exists to hold: *every* observation the panel makes has to be reachable
from here, because a signal with no reader is the silent failure this whole
product is built to refuse, wearing the costume of the mechanism meant to catch
it.

**Observations with ages, never verdicts.** Nothing here computes healthy or
unhealthy. A green dot that is green because nothing checked is exactly this
product's characteristic failure wearing a UI, and it would be worse than no
panel at all because it manufactures confidence. Each reading says what was
found, when, and — when there is nothing to say — that there is nothing to say.

**One health model**: each wall is
read through its display state and each Player through its Player state, the
same states Walls and Players serve, and `HealthReading.troubles` lists the
faults among them by name for the top bar and the System badge to count. The
one threshold any of it applies is the contract's staleness (`timing.json`,
past which a wall or a Player is not reporting), which every surface shares; a
state whose setup flag is true (a wall with no Player, a Player with no token
or no report yet) is never a trouble, because it is a step not yet taken.

**There is no budget balance here; the month's budget is the sidebar's**
(`library/services/spending.py`, `GET /api/budget`, the owner's ruling of
2026-10-07, #290). It stays off this panel because this panel's remedy for a
stale figure is to state its age, and the provider's `limit_remaining` fails by
inversion rather than by staleness: it was observed reporting credit while live
calls were already being refused, so an age beside it would not warn anyone
about the case that bites. The refusal at the cap names the month's budget as
spent, and that is what a curator meets at the edge.

Composed in the service layer rather than in the handler, so both the assembly
and its rules are testable without HTTP, and so the surface stays the thin
binding the architecture requires.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from arrt import observations
from arrt.counting import counted
from arrt.library.acquisition.queue import AcquisitionPhase, AcquisitionState, failure_instant
from arrt.library.services.pictures import PictureStore
from arrt.library.services.watches import WatchesReading
from arrt.library.sources.loading import PluginReading, PluginState, SourceRoster
from arrt.library.sources.names import museum_name
from arrt.persistence import backup
from arrt.persistence.discovery_records import SearchTally, SourceYield
from arrt.persistence.records import BackupReading, Wall
from arrt.programming import display_state, player_state
from arrt.programming.clients import ClientView, DisplayFault, PlacementSurvey
from arrt.programming.display import DisplayService, WallHeartbeat, WallView, describe_wall_status, wall_statuses
from arrt.programming.player_state import PlayerState


@dataclass(frozen=True, slots=True)
class SourceHealth:
    """One installed source plugin, with the age of its last fault and of its last "could not be asked"."""

    reading: PluginReading
    #: Seconds since the last contained fault, or `None` when there was none.
    last_fault_age_seconds: float | None
    #: Seconds since the last call that was "could not be asked", or `None` when there was none.
    last_unasked_age_seconds: float | None = None
    #: What its searches came to, from the search record, which a restart keeps
    #: (`DiscoveryStore.search_tallies`); `None` when it was never searched, or
    #: no record is read here.
    searches: SearchTally | None = None

    @property
    def museum(self) -> str:
        """The museum this plugin is named by: the built-in's `MUSEUM`, else what the plugin itself declared, else its id.

        **The one owner of a source's name** wherever the server states it:
        this answer's sentence and troubles, `GET /api/sources` and
        `art_image(action='sources')`, and a failure cause's museum
        (`HealthService.museum_of`). From the plugin's own reading, never from
        whatever the latest load declared process-wide, so the sentence and the
        `museum` beside it cannot name one plugin two ways.
        """
        return museum_name(self.reading.name, self.reading.identity.museum)

    def describe(self) -> str:
        """What happened to this plugin, in a sentence: an observation, never a verdict.

        **A plugin that has only ever said "could not be asked" is said to have.**
        A parser that no longer recognises a museum's redesigned pages answers
        that, in the interface's own words, for every work, and is no fault; by
        faults alone it read "loaded, with no faults" while every work it would
        have answered waited.
        """
        reading = self.reading
        # By the museum, not the plugin id: the id is a key, and a curator
        # reading "smk is loaded" learns nothing about which collection.
        museum = self.museum
        if reading.state is PluginState.DECLINED:
            return f"The {museum} plugin is installed and not configured here: {reading.reason}."
        if reading.state is PluginState.FAILED:
            return f"The {museum} plugin is installed and was not loaded: {reading.reason}."
        return self._since_startup(museum) + self._searched()

    def _since_startup(self, museum: str) -> str:
        """What its calls since startup ended in: the in-memory counts, which a restart resets."""
        reading = self.reading
        unasked = self._unasked()
        if reading.faults == 0 and reading.unasked and not reading.answered:
            return (
                f"The {museum} plugin is loaded and has answered nothing since startup but that it could not be "
                f"asked: {unasked}. Works it would have answered wait instead of being settled."
            )
        if reading.faults == 0:
            said = f"The {museum} plugin is loaded, with no faults since startup."
            return said if not reading.unasked else f"{said[:-1]}; it could not be asked {unasked}."
        plural = "fault" if reading.faults == 1 else "faults"
        said = (
            f"The {museum} plugin is loaded, with {reading.faults} {plural} since startup, the last "
            f"{self.last_fault_age_seconds:.0f} seconds ago ({reading.last_fault}). Each was recorded as the "
            "source not being reachable, so works it would have answered wait instead of being settled."
        )
        if reading.unasked:
            said += f" It could also not be asked {unasked}."
        if not reading.answered:
            said += " It has answered nothing else since startup."
        return said

    def _searched(self) -> str:
        """What the search record says of its searches, as a sentence with a leading space; empty when nothing is owed or unasked.

        From the record, so it survives a restart where the counts since
        startup do not: a plugin that could not be asked about every work it
        was searched for still reads so the morning after.
        """
        tally = self.searches
        if tally is None or tally.searched == 0 or not (tally.unasked or tally.owed):
            return ""
        works = counted(tally.searched, "work")
        owed = "" if not tally.owed else f", and still owes an answer about {tally.owed}"
        if tally.answered == 0:
            return (
                f" It has answered none of the {works} it was last searched for: it could not be asked about "
                f"{tally.unasked}{owed}."
            )
        return f" Of the {works} it was last searched for, it could not be asked about {tally.unasked}{owed}."

    def _unasked(self) -> str:
        """How many times the plugin could not be asked, when last, and what it said then."""
        reading = self.reading
        times = "once" if reading.unasked == 1 else f"{reading.unasked} times"
        age = "" if self.last_unasked_age_seconds is None else f", the last {self.last_unasked_age_seconds:.0f} seconds ago"
        return f"{times}{age} ({reading.last_unasked})"


@dataclass(frozen=True, slots=True)
class PicturesReading:
    """How much the picture store keeps, and how old that count is.

    Here because the store has no ceiling (owner, 2026-10-06): its growth is
    watched rather than bounded, and this is where it is watched. An observation
    with its age, never a verdict: no size is called too large.
    """

    pictures_bytes: int
    pictures_files: int
    #: Seconds since the walk this count came from. The walk is reused for ten
    #: minutes, so a count can be that old.
    age_seconds: float
    #: Directories and files the walk could not read. Not zero means this
    #: machine's disk is refusing the store, and the count is short by what they
    #: hold: stated apart, so an unreadable store never reads as an empty one.
    unreadable: int = 0

    def describe(self) -> str:
        """The count in a sentence, with its age, and what could not be read when anything could not."""
        counted = f"counted {self.age_seconds:.0f} seconds ago"
        if self.unreadable:
            entries = "entry" if self.unreadable == 1 else "entries"
            return (
                f"The picture store could not be read in full: {self.unreadable:,} {entries} refused, so the "
                f"{self.pictures_files:,} files and {self.pictures_bytes / 1_000_000:,.1f} MB counted are short by "
                f"what they hold ({counted}). Cards whose pictures are there go without them until the disk "
                "answers."
            )
        if self.pictures_files == 0:
            return f"The picture store keeps no pictures yet ({counted})."
        plural = "file" if self.pictures_files == 1 else "files"
        return (
            f"The picture store keeps {self.pictures_files:,} {plural}, {self.pictures_bytes / 1_000_000:,.1f} MB, "
            f"{counted}. Each picture is two files, one per size kept."
        )


@dataclass(frozen=True, slots=True)
class FailedFetches:
    """The works whose picture the queue failed to fetch: how many, and when the newest failed, where known.

    Counted from `AcquisitionQueue.failed_states`, the works Activity › Queue
    lists as failed or given up on, so the badge and the page cannot disagree. A health
    observation, because 2,000 failed fetches once raised nothing anywhere
    (seen 2026-11-19).
    """

    #: Every work the Queue lists as failed: those it will try again and those it gave up on.
    count: int
    #: Of `count`, those the queue tries again on its own.
    will_retry: int
    #: Of `count`, those it gave up on, which wait for Retry.
    given_up: int
    #: The newest failure among the works whose failure instant is known, and its
    #: age; both null when none is known.
    newest_failed_at: datetime | None
    newest_age_seconds: float | None
    #: Of `count`, how many failed at an instant that is not recorded, so
    #: `newest_age_seconds` cannot speak for them: only rows that failed before
    #: the queue recorded `failed_at` and give no retry to read it back from
    #: (`failure_instant`). When it equals `count`, the age of the newest
    #: failure is not known at all.
    age_unknown: int

    def describe(self) -> str:
        """The count in a sentence, with the newest failure's age, or that it is not recorded."""
        works = "1 work" if self.count == 1 else f"{self.count:,} works"
        said = f"The queue holds {works} whose picture could not be fetched"
        if self.newest_age_seconds is None:
            return f"{said}; when the newest failed is not recorded."
        aged = observations.ago(self.newest_age_seconds)
        if not self.age_unknown:
            return f"{said}; the newest failed {aged}."
        return (
            f"{said}; the newest whose time is recorded failed {aged}, and {self.age_unknown:,} failed at a time " "not recorded."
        )


def failed_fetches(states: Sequence[AcquisitionState], *, now: datetime) -> FailedFetches | None:
    """What the queue holds as failed (`AcquisitionQueue.failed_states`), or None when it holds none: no observation."""
    if not states:
        return None
    instants = [instant for instant in map(failure_instant, states) if instant is not None]
    newest = max(instants, default=None)
    return FailedFetches(
        count=len(states),
        will_retry=sum(1 for state in states if state.phase is AcquisitionPhase.FAILED),
        given_up=sum(1 for state in states if state.phase is AcquisitionPhase.GAVE_UP),
        newest_failed_at=newest,
        newest_age_seconds=None if newest is None else (now - newest).total_seconds(),
        age_unknown=len(states) - len(instants),
    )


class TroubleKind(StrEnum):
    """What a trouble is about, so a screen can link it to where it is mended."""

    WALL = "wall"
    PLAYER = "player"
    DISPLAY_FAULT = "display_fault"
    BACKUP = "backup"
    SOURCE = "source"
    WATCH = "watch"
    FAILED_FETCHES = "failed_fetches"
    #: A wall keeping the feed it has because its next would be larger than a
    #: Player reads, and no person asked for that feed, so nobody else was told
    #: (`FeedPublisher.feeds_over_bound`); its subject is the wall.
    FEED = "feed"


@dataclass(frozen=True, slots=True)
class Trouble:
    """One thing the household is told of on the top bar and the System badge: a fault, never a setup step."""

    about: TroubleKind
    #: The wall's or Player's id (the wall's for a feed), the plugin's name, the
    #: display's identity; null for the backup, a Watch and the failed fetches.
    subject: str | None
    #: The wall's display state or the Player's state, for those two; null otherwise.
    state: str | None
    #: A short phrase, in the household's words, for the top bar's list.
    words: str


class SetupKind(StrEnum):
    """What a setup step is about, so a screen can link it to where it is taken."""

    #: The catalogue holds no wall at all: nothing can be hung, and nothing reports.
    NO_WALL = "no_wall"
    #: A wall no Player shows (`display_state.SETUP`).
    WALL = "wall"
    #: A Player with no token or no report yet (`player_state.SETUP`), naming
    #: the walls that wait for it, which make no step of their own.
    PLAYER = "player"


@dataclass(frozen=True, slots=True)
class SetupStep:
    """One step of setting the household up that is not yet taken: never a fault, and never all well.

    Stated by the server, as `Trouble` is, so the top bar reads what remains to
    be set up rather than deciding it from the walls and Players itself.
    """

    about: SetupKind
    #: The wall's or Player's id; null for `no_wall`.
    subject: str | None
    #: A setup state, never a fault's; null for `no_wall`: the Player's state for
    #: a Player (`no_token`, `awaiting_report`); `unassigned` for a wall.
    state: str | None
    #: A short phrase, in the household's words, for the top bar's list.
    words: str


@dataclass(frozen=True, slots=True)
class WallWait:
    """A wall that has not reported because the Player that shows it is still being set up.

    **Not a state of the wall's own.** Its display state stays `silent`, the
    contract's word for a wall with no readable report (`vocabulary.json`,
    `label.v1`), which is true of it and which a Player captioning it reads; what
    the household is told is why, in the Player's setup state, so the wall's
    panel says it waits, with a setup step's mark, rather than that it is not
    reporting. One cause is one step, and it is the Player's
    (`HealthReading.setup_steps`).
    """

    #: The Player that shows the wall.
    client_id: str
    name: str
    #: The Player's setup state: `no_token` or `awaiting_report`.
    state: PlayerState
    #: The wall's wait, in the household's words, for the wall's own panel.
    words: str


@dataclass(frozen=True, slots=True)
class WallsNow:
    """Each wall as a walls answer says it, every part of it from one reading (`HealthService.observe_walls`).

    A wall's view (`views`, with its display state and whether its Player
    reads the feed), its wait (`waiting.get(id)`) and who shows it, its
    display and its labels (`survey`) are one read of the store and of each
    report file, so an answer built from them cannot say a wall waits while
    saying it shows a work, nor that it is unassigned beside the Player that
    shows it. **A wall's display state is held once, in its view**, and its
    wait is judged from that one: a second copy built beside it is a second
    place for the two to part.
    """

    #: Every wall read, or the one asked for, in the order walls are listed.
    views: Sequence[WallView]
    #: Each wall's wait, by wall id, judged from its view's display state.
    waiting: Mapping[str, WallWait]
    #: Who shows each wall, its display and its labels, from the same read.
    survey: PlacementSurvey
    #: Why each wall's report cannot be read, by wall id, for the walls whose
    #: report cannot be (`HeartbeatReading.problem`): from the read its view's
    #: display state was judged from, so what made a report unreadable is said
    #: beside the state it made silent. The reason alone, never the reading, so
    #: no reader can judge a wall's state a second time from it.
    report_problems: Mapping[str, str]


def walls_waiting(walls: Sequence[WallHeartbeat], players: Sequence[ClientView]) -> dict[str, WallWait]:
    """Every wall not reporting because its Player is being set up, by wall id: the one rule every surface reads.

    A wall is waiting when its display state is a fault's (`silent`) and the
    Player that shows it is in a setup state (`player_state.SETUP`) that
    explains the silence: it has no token, so it can report nothing; or it has
    one and has not yet reported, and nothing was ever written for this wall
    either. A wall such a Player shows that reads anything else (a report left
    from before its token was withdrawn, still young) is not waiting, and says
    what it reports; nor is a wall whose own reports have arrived and stopped
    while its Player has sent none of its own, which is a wall gone quiet, the
    trouble it always was.
    """
    by_wall = {shown.wall.id: view for view in players if view.player.state in player_state.SETUP for shown in view.walls}
    return {
        seen.wall.id: WallWait(
            client_id=view.client.id,
            name=view.client.name,
            state=view.player.state,
            words=_waiting_words([seen.wall.name], view),
        )
        for seen in walls
        if seen.state.state in display_state.TROUBLES
        and (view := by_wall.get(seen.wall.id)) is not None
        and (view.player.state is PlayerState.NO_TOKEN or seen.heartbeat.absent)
    }


@dataclass(frozen=True, slots=True)
class HealthReading:
    """Every observation the panel makes, gathered at one instant."""

    #: What the display serving each wall last said about itself, including
    #: whatever else it chose to report. `observability-strategy.md`'s failure
    #: table maps TV connectivity, panel state and the last error onto this
    #: document, and the panel showing it is what gives those rows a reader.
    #:
    #: **A list rather than one reading**, because with a display per wall the
    #: interesting question stopped being "has the display plane reported" and
    #: became "which wall has not". One shared reading could not have answered it.
    walls: Sequence[WallHeartbeat]
    #: When the catalogue was last safely copied, or that nothing has copied it.
    backup: BackupReading
    #: Every picture fetched from outside, kept for good: how many files and how
    #: many bytes, and how old the count is.
    pictures: PicturesReading
    #: Every installed source plugin: loaded, declined or failed, with the faults
    #: a loaded one has had. Here because a plugin missing or failing in silence
    #: looks like works nobody holds, which reads as a fact about art rather than
    #: about this deployment.
    sources: Sequence[SourceHealth] = ()
    #: Whether any Watch needs a person: overdue, or held by a spent allowance.
    watches: WatchesReading = field(default_factory=WatchesReading)
    #: Every Player with its state and each output's (`player_state.py`).
    players: Sequence[ClientView] = ()
    #: What the queue holds as failed, or None when it holds nothing failed.
    failed_fetches: FailedFetches | None = None
    #: Each wall held back because its next feed would be larger than a Player
    #: reads, with that feed's size in bytes, by wall id: a refusal no person
    #: was told of (a roll, a reconcile, a neighbour's rebuild), and the wall
    #: keeps the feed it has until one of its feeds is written
    #: (`FeedPublisher.feeds_over_bound`).
    feeds_over_bound: Mapping[str, int] = field(default_factory=dict)

    def troubles(self) -> tuple[Trouble, ...]:
        """Every fault this reading holds, in one list: what the top bar and the System badge count.

        **Derived only from states whose setup flag is false** (`display_state.SETUP`,
        `player_state.SETUP`): a wall with no Player, and a Player with no token or
        no report yet, are steps not yet taken and never a trouble, nor is a wall
        waiting for such a Player (`walls_waiting`: its Player's step names it). A wall is one
        when its state is in `display_state.TROUBLES`, a Player when its state is
        in `player_state.TROUBLES`. A display two Players report is one too,
        though its wall reads `unassigned`: that is a configuration fault, not a
        step not yet taken (`clients.DisplayFault`).

        **One trouble for one cause.** A Player not heard from is one trouble,
        stated on the Player and naming the walls it shows that are not
        reporting with it; those walls are not listed again on their own. A
        wall that is not reporting for any other reason (its Player is heard
        from, or cannot be read) is still a trouble of its own.
        """
        states = {seen.wall.id: seen.state.state for seen in self.walls}
        found: list[Trouble] = []
        # A wall whose Player is still being set up is named by that Player's
        # setup step (`setup_steps`), never a trouble of its own: it has not
        # reported because its Player has not yet been able to.
        with_their_player: set[str] = set(walls_waiting(self.walls, self.players))
        faults: dict[str, DisplayFault] = {}
        for view in self.players:
            if view.player.state in player_state.TROUBLES:
                quiet = [
                    shown.wall
                    for shown in view.walls
                    if view.player.state is PlayerState.NOT_HEARD_FROM and states.get(shown.wall.id) in display_state.TROUBLES
                ]
                with_their_player.update(wall.id for wall in quiet)
                found.append(Trouble(TroubleKind.PLAYER, view.client.id, str(view.player.state), _player_words(view, quiet)))
            for fault in view.faults:
                faults.setdefault(fault.identity, fault)
        found[:0] = [
            Trouble(TroubleKind.WALL, seen.wall.id, str(seen.state.state), _wall_words(seen))
            for seen in self.walls
            if seen.state.state in display_state.TROUBLES and seen.wall.id not in with_their_player
        ]
        for identity, fault in faults.items():
            names = " and ".join(client.name for client in fault.clients)
            found.append(Trouble(TroubleKind.DISPLAY_FAULT, identity, None, f"{names} both report one display"))
        found.extend(
            Trouble(TroubleKind.FEED, seen.wall.id, None, _feed_words(seen.wall))
            for seen in self.walls
            if seen.wall.id in self.feeds_over_bound
        )
        found.extend(_backup_troubles(self.backup))
        found.extend(_source_troubles(self.sources))
        found.extend(Trouble(TroubleKind.WATCH, None, None, f"Watch “{words}” is overdue") for words in self.watches.overdue)
        if self.watches.allowance_spent:
            found.append(Trouble(TroubleKind.WATCH, None, None, "Watches wait: the unattended allowance is spent"))
        if self.failed_fetches is not None:
            count = self.failed_fetches.count
            works = "1 work" if count == 1 else f"{count:,} works"
            found.append(Trouble(TroubleKind.FAILED_FETCHES, None, None, f"{works} could not fetch a picture"))
        return tuple(found)

    def setup_steps(self) -> tuple[SetupStep, ...]:
        """Every step of setting up not yet taken: what the top bar states beside the troubles.

        **A household with no wall is never all well**: it is told that no wall
        is recorded. Then each wall no Player shows (`display_state.SETUP`),
        but not one whose display two Players report, which is a trouble
        (`clients.DisplayFault`); then each Player whose state is a setup state
        (`player_state.SETUP`): no token yet, or no report yet.

        **One step for one cause.** A wall that has not reported because its
        Player is being set up (`walls_waiting`) is no step of its own: the
        Player's step names it, so a Player with no token that shows two walls
        is one step, not three.
        """
        waiting = walls_waiting(self.walls, self.players)
        if not self.walls:
            found = [SetupStep(SetupKind.NO_WALL, None, None, "No wall is recorded yet")]
        else:
            in_fault = {fault.wall.id for view in self.players for fault in view.faults if fault.wall is not None}
            found = [
                SetupStep(SetupKind.WALL, seen.wall.id, str(seen.state.state), f"{seen.wall.name} has no Player yet")
                for seen in self.walls
                if seen.state.state in display_state.SETUP and seen.wall.id not in in_fault
            ]
        for view in self.players:
            if view.player.state in player_state.SETUP:
                names = [seen.wall.name for seen in self.walls if _waits_for(waiting.get(seen.wall.id), view)]
                found.append(SetupStep(SetupKind.PLAYER, view.client.id, str(view.player.state), _setup_words(view, names)))
        return tuple(found)

    def describe(self) -> str:
        """One sentence across every wall, from the readings this panel holds.

        Delegated rather than written here, because the tool surface states the
        same fact from the same readings and two hand-written sentences drift —
        a caller told "the study has not reported" by one surface and "every wall
        has reported" by the other has no way to tell which is lying.

        **A wall waiting for its Player is said to wait** (`walls_waiting`), and
        never counted among the walls that have not reported: the sentence over
        the rest is `describe_wall_status`'s, and the waiting walls follow it,
        named with the Player each waits for.
        """
        waiting = walls_waiting(self.walls, self.players)
        if not waiting:
            return describe_wall_status(self.walls)
        rest = [seen for seen in self.walls if seen.wall.id not in waiting]
        waits = " ".join(
            f"{_waiting_words([seen.wall.name for seen in self.walls if _waits_for(waiting.get(seen.wall.id), view)], view)}."
            for view in self.players
            if any(_waits_for(wait, view) for wait in waiting.values())
        )
        if all(seen.state.state in display_state.SETUP for seen in rest):
            return waits
        # The rest's sentence speaks only of the walls it was given, so the
        # waiting walls are said after it as not among them.
        return f"{describe_wall_status(rest)} {waits[:-1]}, so {'it is' if len(waiting) == 1 else 'they are'} not counted there."


def _waits_for(wait: WallWait | None, view: ClientView) -> bool:
    """Whether a wall's wait (`walls_waiting`) is for this Player."""
    return wait is not None and wait.client_id == view.client.id


def _wall_words(seen: WallHeartbeat) -> str:
    """A wall that is not reporting, as the top bar says it: never written, unreadable, or for how long."""
    name = seen.wall.name
    if seen.state.last is not None and seen.heartbeat.age_seconds is not None:
        return f"{name} has not reported for {observations.in_words(seen.heartbeat.age_seconds)}"
    if seen.heartbeat.problem is not None:
        return f"{name}'s last report cannot be read"
    return f"{name} has not reported"


def _feed_words(wall: Wall) -> str:
    """A wall whose next feed was too large, as the top bar says it, with what makes it smaller (`FeedTooLarge`'s remedy)."""
    return (
        f"{wall.name}'s new feed is too large for its Player, so it keeps the one it has; "
        "a longer time for each work on it makes the feed smaller"
    )


def _player_words(view: ClientView, quiet: Sequence[Wall] = ()) -> str:
    """A Player in fault, as the top bar says it, naming the walls not reporting with it."""
    name = view.client.name
    if view.player.state is PlayerState.REPORT_UNREADABLE:
        return f"{name}'s report cannot be read"
    said = f"{name} has not been heard from for {observations.in_words(view.heartbeat.age_seconds or 0.0)}"
    if not quiet:
        return said
    return f"{said}, nor {'has' if len(quiet) == 1 else 'have'} {_listed([wall.name for wall in quiet])}"


def _setup_words(view: ClientView, walls: Sequence[str] = ()) -> str:
    """A Player being set up, as the top bar says it, naming the walls that wait for it."""
    name = view.client.name
    one = len(walls) == 1
    if view.player.state is PlayerState.NO_TOKEN:
        said = f"{name} has no token yet"
        return said if not walls else f"{said}, so {_listed(walls)} {'waits' if one else 'wait'} for it"
    said = f"{name} is waiting for its first report"
    return said if not walls else f"{said}, and so {'is' if one else 'are'} {_listed(walls)}"


def _waiting_words(walls: Sequence[str], view: ClientView) -> str:
    """Walls that have not reported because their Player is being set up, as the wall's panel says it."""
    name = view.client.name
    wait = "waits" if len(walls) == 1 else "wait"
    if view.player.state is PlayerState.NO_TOKEN:
        return f"{_listed(walls)} {wait} for {name}, which has no token yet"
    return f"{_listed(walls)} {wait} for {name}'s first report"


def _listed(names: Sequence[str]) -> str:
    """Names in a sentence: "A", "A and B", "A, B and C"."""
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _backup_troubles(reading: BackupReading) -> list[Trouble]:
    if reading.problem is not None:
        return [Trouble(TroubleKind.BACKUP, None, None, "The backup record cannot be read")]
    if reading.absent:
        return [Trouble(TroubleKind.BACKUP, None, None, "The Library has never been backed up")]
    return []


def _source_troubles(sources: Sequence[SourceHealth]) -> list[Trouble]:
    """A plugin that failed to load or has faulted; one that declined is configured off on purpose and is none."""
    found = []
    for source in sources:
        reading = source.reading
        museum = source.museum
        if reading.state is PluginState.FAILED:
            found.append(Trouble(TroubleKind.SOURCE, reading.name, None, f"The {museum} source could not be loaded"))
        elif reading.faults > 0:
            found.append(Trouble(TroubleKind.SOURCE, reading.name, None, f"The {museum} source has faulted since startup"))
    return found


class HealthService:
    """Gather what the panel states. Decides nothing about any of it."""

    def __init__(
        self,
        display: DisplayService,
        *,
        backup_receipt_path: Path,
        sources: SourceRoster,
        yields: Callable[[], Mapping[str, SourceYield]],
        pictures: PictureStore,
        searches: Callable[[Sequence[str]], Mapping[str, SearchTally]] | None = None,
        watches: Callable[[], WatchesReading],
        queue: Callable[[], Sequence[AcquisitionState]] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        #: The walls, the Players and who shows what, read together
        #: (`DisplayService.read_wall_reports`, `read_walls`): every Player's
        #: state is judged from the read the walls' states are.
        self._display = display
        #: The queue's failed works (`AcquisitionQueue.failed_states`), which the
        #: failed fetches are counted from: a read of no work's title, because
        #: the top bar reads this on every page. None observes none, for a
        #: caller testing another part of the panel; `container.py` always gives
        #: one, and `test_browser_surface.py` reads it through the real server.
        self._queue = queue
        #: What the Watches need a person to know (`WatchService.reading`).
        self._watches = watches
        self._pictures = pictures
        self._sources = sources
        self._now = now
        #: Where the backup job records that it succeeded. Passed in rather than
        #: resolved here, for the reason every settings object in this layer
        #: gives: a service that read its own configuration could not be tested
        #: against two deployments and would make every caller share one.
        self._backup_receipt_path = backup_receipt_path
        #: What each provider has offered and what the library holds from it,
        #: counted from the records (`DiscoveryStore.source_yields`).
        self._yields = yields
        #: What each source's newest searches came to, from the search record
        #: (`DiscoveryStore.search_tallies`), asked for the installed plugins by
        #: name: a bounded read of that table alone, since the top bar reads the
        #: sources on every page. None reads none, and each source states its
        #: counts since startup only.
        self._searches = searches

    def observe(self) -> HealthReading:
        """Read every signal the panel shows, now.

        One call rather than one per signal, which is what lets the handler above
        stay a dispatch: a surface assembling three reads is a surface deciding
        what the panel is made of, and the next signal would then have to be added
        in two places with nothing to notice if it reached only one.
        """
        # One reading for the walls and the Players, so whom a wall waits for,
        # and which Player shows it, are said of the instant its state is.
        walls = self._display.read_wall_reports()
        return HealthReading(
            walls=wall_statuses(walls),
            backup=backup.read(self._backup_receipt_path),
            sources=self.observe_sources(),
            pictures=self.observe_pictures(),
            watches=self._watches(),
            players=tuple(walls.players()),
            failed_fetches=self.observe_failed_fetches(),
            feeds_over_bound=self._display.feeds_over_bound(),
        )

    def observe_walls(self, wall_id: str | None = None) -> WallsNow:
        """Every wall, or the one named, as a walls answer says it: one read of the store and of each report.

        The rule `observe()`'s reading applies, over the same kind of read, so
        the walls answer and the health answer cannot disagree about whom a
        wall waits for. **An answer says everything it says of a wall from
        this one reading**: its state, its wait, who shows it, its display and
        labels, whether its Player reads the feed. A first report landing
        between two reads made one answer say the wall waits beside a badge
        showing a work, and a Player assigned between two made one say the
        wall is unassigned beside the Player that shows it.

        **One wall's answer reads its own report and every Player's, and no
        other wall's** (`Placements.read_walls` says why every Player's). A
        wall named that the catalogue does not hold is refused (`NotFound`).
        """
        seen = self._display.read_walls(wall_id)
        # Each wall's state as its view holds it, never judged again.
        walls = [
            WallHeartbeat(wall=view.wall, heartbeat=seen.reading.reports[view.wall.id], state=view.display_state)
            for view in seen.views
        ]
        return WallsNow(
            views=seen.views,
            waiting=walls_waiting(walls, seen.reading.players()),
            survey=seen.reading.survey,
            report_problems={
                wall_id: report.problem for wall_id, report in seen.reading.reports.items() if report.problem is not None
            },
        )

    def observe_failed_fetches(self) -> FailedFetches | None:
        """What the queue holds as failed now, or None when it holds nothing failed (or no queue was given)."""
        if self._queue is None:
            return None
        return failed_fetches(self._queue(), now=self._now())

    def observe_pictures(self) -> PicturesReading:
        """The picture store's size and file count, from a walk at most ten minutes old."""
        size = self._pictures.size()
        return PicturesReading(
            pictures_bytes=size.pictures_bytes,
            pictures_files=size.pictures_files,
            age_seconds=max(0.0, (self._now() - size.measured_at).total_seconds()),
            unreadable=size.unreadable,
        )

    def observe_sources(self) -> tuple[SourceHealth, ...]:
        """Every installed source plugin, now, most preferred first: the part of the panel Settings › Sources shows."""
        return tuple(self._source_health())

    def museum_of(self, plugin: str) -> str:
        """The museum an installed plugin is named by (`SourceHealth.museum`); one no longer installed by its id.

        For an answer that holds a plugin's name and not its reading, such as a
        failure cause, so it names the museum as the sources answer does.
        """
        reading = next((each for each in self._sources.observe() if each.name == plugin), None)
        return museum_name(plugin, None if reading is None else reading.identity.museum)

    def observe_yields(self) -> tuple[SourceYield, ...]:
        """What each installed source plugin has given the library, most preferred first.

        **Not part of `observe()`**, which the top bar reads on every page: these
        are counts across the whole library, and only Status's sources table
        reads them. One row per installed plugin, so a source that has offered
        nothing reads as zeros rather than going missing; a provider the records
        name that is no longer installed has no row, as it has none in `sources`.
        """
        found = self._yields()
        return tuple(
            found.get(reading.name) or SourceYield(provider=reading.name, offered=0, chosen=0, only_here=0, median_long_edge=None)
            for reading in self._sources.observe()
        )

    def _source_health(self) -> list[SourceHealth]:
        now = self._now()
        readings = self._sources.observe()
        searches = {} if self._searches is None else self._searches([reading.name for reading in readings])
        return [
            SourceHealth(
                reading=reading,
                last_fault_age_seconds=(None if reading.last_fault_at is None else (now - reading.last_fault_at).total_seconds()),
                last_unasked_age_seconds=(
                    None if reading.last_unasked_at is None else (now - reading.last_unasked_at).total_seconds()
                ),
                searches=searches.get(reading.name),
            )
            for reading in readings
        ]
