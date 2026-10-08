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
unhealthy, and nothing compares an age to a threshold. A green dot that is green
because nothing checked is exactly this product's characteristic failure wearing
a UI, and it would be worse than no panel at all because it manufactures
confidence. Each reading says what was found, when, and — when there is nothing
to say — that there is nothing to say.

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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from arrt.library.services.pictures import PictureStore
from arrt.library.sources.loading import PluginReading, PluginState, SourceRoster
from arrt.library.sources.names import museum_name
from arrt.persistence import backup
from arrt.persistence.discovery_records import SourceYield
from arrt.persistence.records import BackupReading
from arrt.programming.display import DisplayService, WallHeartbeat, describe_wall_status


@dataclass(frozen=True, slots=True)
class SourceHealth:
    """One installed source plugin, with the age of its last fault."""

    reading: PluginReading
    #: Seconds since the last contained fault, or `None` when there was none.
    last_fault_age_seconds: float | None

    def describe(self) -> str:
        """What happened to this plugin, in a sentence: an observation, never a verdict."""
        reading = self.reading
        # By the museum, not the plugin id: the id is a key, and a curator
        # reading "smk is loaded" learns nothing about which collection.
        museum = museum_name(reading.name)
        if reading.state is PluginState.DECLINED:
            return f"The {museum} plugin is installed and not configured here: {reading.reason}."
        if reading.state is PluginState.FAILED:
            return f"The {museum} plugin is installed and was not loaded: {reading.reason}."
        if reading.faults == 0:
            return f"The {museum} plugin is loaded, with no faults since startup."
        plural = "fault" if reading.faults == 1 else "faults"
        return (
            f"The {museum} plugin is loaded, with {reading.faults} {plural} since startup, the last "
            f"{self.last_fault_age_seconds:.0f} seconds ago ({reading.last_fault}). Each was recorded as the "
            "source not being reachable, so works it would have answered wait instead of being settled."
        )


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

    def describe(self) -> str:
        """One sentence across every wall, from the readings this panel holds.

        Delegated rather than written here, because the tool surface states the
        same fact from the same readings and two hand-written sentences drift —
        a caller told "the study has not reported" by one surface and "every wall
        has reported" by the other has no way to tell which is lying.
        """
        return describe_wall_status(self.walls)


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
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._display = display
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

    def observe(self) -> HealthReading:
        """Read every signal the panel shows, now.

        One call rather than one per signal, which is what lets the handler above
        stay a dispatch: a surface assembling three reads is a surface deciding
        what the panel is made of, and the next signal would then have to be added
        in two places with nothing to notice if it reached only one.
        """
        return HealthReading(
            walls=self._display.survey_wall_status(),
            backup=backup.read(self._backup_receipt_path),
            sources=self.observe_sources(),
            pictures=self.observe_pictures(),
        )

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
        return [
            SourceHealth(
                reading=reading,
                last_fault_age_seconds=(None if reading.last_fault_at is None else (now - reading.last_fault_at).total_seconds()),
            )
            for reading in self._sources.observe()
        ]
