"""Major 1's programme: the manifest's entries in rotation, and the directive.

Retires with major 1 (wave 4g), when the schedule replaces rotation and a
republished schedule replaces the directive. Until then it is the Frame's
rules, in one place. Where the screen's loop had differed and no screen test
pinned its version, the screen now runs the Frame's (an empty wall retries on
a new manifest; a directive that shows nothing does not restamp the timer);
where each loop's tests pinned its own, the difference is a parameter here:

**A directive is acted on when the sequence advances, and adopted silently when
it moves any other way.** A first start has never acted on anything, so it takes
whatever it finds as its baseline: acting instead would execute, at install time,
a `show_now` somebody issued last week. A sequence that goes *backwards* is a
restored catalogue, not a directive, and replaying a stale pin because a backup
came back is the failure that rule exists to prevent.

**Anything that cannot be shown is skipped, never fatal.** A missing render file,
a work whose upload failed, a pin naming a work the active theme does not carry —
each is a WARNING and the rotation continues. The wall going black is always
worse than the wall being incomplete.

**Where its memory lives is the display's choice** (`Memory`). The Frame keeps
the directive it acted on and the work it showed in its store, because the set
holds the picture across a restart and a restarted process must neither replay a
`show_now` nor step past the picture on the wall. A screen this host draws on is
black after a restart, so it keeps both in memory (`InMemory`) and a restarted
worker starts its rotation again.
"""

import logging
import random
from collections.abc import Sequence
from pathlib import Path

from arrt_player.logs import work_context
from arrt_player.manifest import Entry, Manifest
from arrt_player.programmes.memory import Memory
from arrt_player.wall import Clock, Display, Picture, Shown

log = logging.getLogger(__name__)


class Rotation:
    """Major 1's programme for one wall."""

    def __init__(
        self,
        *,
        wall_id: str,
        render_root: Path,
        memory: Memory,
        clock: Clock,
        rng: random.Random | None = None,
        say_missing_once: bool = False,
    ) -> None:
        self._wall_id = wall_id
        self._render_root = render_root
        self._memory = memory
        self._clock = clock
        self._rng = rng if rng is not None else random.Random()  # noqa: S311 -- it orders artworks, it guards nothing
        #: **The two displays report a missing render differently, and each is
        #: pinned by its own tests.** The Frame says it on every attempt, which
        #: the rotation timer bounds to once an interval; a screen says it once
        #: per manifest. Kept apart rather than settled, because this code
        #: retires with major 1.
        self._say_missing_once = say_missing_once
        self._missing: set[str] = set()
        self._manifest: Manifest | None = None

        #: Positions into the current manifest's entries, in the order they will
        #: be shown. Held apart from the entries themselves so that shuffling is
        #: a property of this run rather than something written back anywhere.
        self._order: list[int] = []
        self._cursor: int = 0

        #: **Two facts that were one field until they were told apart.** When the
        #: last rotation was *attempted* governs the timer; whether anything has
        #: ever reached the wall governs whether a restart re-shows or steps past.
        #: Sharing one nullable float made a pass that showed nothing look like a
        #: process that had just started, so the timer never armed and a theme with
        #: no renders walked its whole list once a second, for ever.
        self._attempted_at: float | None = None
        self._has_shown = False

    @property
    def pictures(self) -> Sequence[Picture]:
        if self._manifest is None:
            return ()
        return tuple(self._picture(entry) for entry in self._manifest.entries)

    @property
    def current_work_id(self) -> str | None:
        return self._memory.last_selected_work_id

    @property
    def scene_id(self) -> str | None:
        """Major 1 has no scenes."""
        return None

    def entered(self) -> None:
        """The wall has just switched to major 1 from another major.

        **Treated as a restart**: the wall holds the other major's picture of
        whatever work is up, so the rotation points at that work and shows its
        own render of it at once, as a restarted process re-selects what is
        already on the wall rather than stepping past it. It takes effect in
        the adoption the wall makes straight after this, which is where the
        rotation reads it.
        """
        self._has_shown = False

    def adopt(self, manifest: Manifest) -> None:
        """Take a new manifest's entry list as the rotation, keeping our place.

        Keeping the place matters more than it looks: `sync` rewrites the manifest
        on every catalogue edit, and a rotation that restarted at the first work
        each time would show the same handful of pictures forever on a busy day.
        """
        self._manifest = manifest
        self._missing.clear()
        self._order = list(range(len(manifest.entries)))
        if manifest.shuffle:
            self._rng.shuffle(self._order)

        # **Only when the wall is empty.** A wall with nothing on it should try
        # again the moment a new manifest lands — renders appearing normally comes
        # with curation republishing, and the alternative is a blank wall sitting
        # out three minutes it has no reason to. A wall that *is* showing
        # something must not have its timer restarted by a rewrite: `sync` fires
        # on every catalogue edit, and resetting here would step the wall on each
        # one, which is the same defect as the cursor rule below in a different
        # coat.
        if not self._has_shown:
            self._attempted_at = None

        self._cursor = 0
        resumed_from = self._memory.last_selected_work_id
        if resumed_from is None:
            return
        position = manifest.index_of(resumed_from)
        if position is None:
            return
        found_at = self._order.index(position)

        # **A restarted process points at the work already on the wall; a running
        # one points past it.** The two cases share this method and want opposite
        # things, and getting it wrong is visible either way.
        #
        # A restart that advanced would change the picture every time the unit
        # bounced — and under `Restart=always` a crash loop would strobe the wall
        # rather than freeze it, which is the worse of the two failures by a long
        # way. Re-selecting what is already showing costs one idempotent call and
        # nobody in the room sees anything happen.
        #
        # A `sync` mid-interval, on the other hand, rewrites the manifest while
        # this process is running and holding its place in memory; pointing back
        # at the current work there would hand it a second full interval on every
        # catalogue edit, which on a busy afternoon is a wall that stops moving.
        self._cursor = found_at if not self._has_shown else (found_at + 1) % len(self._order)

    async def step(self, display: Display) -> None:
        manifest = self._manifest
        if manifest is None:
            return
        if not await self._act_on_directive(manifest, display):
            await self._rotate_if_due(manifest, display)

    # -- directives --------------------------------------------------------

    async def _act_on_directive(  # noqa: PLR0911 -- one return per directive outcome, each named where it happens
        self, manifest: Manifest, display: Display
    ) -> bool:
        """Execute at most one directive, and report whether the wall moved."""
        observed = manifest.directive_sequence
        acted_on = self._memory.last_acted_sequence

        if acted_on is None:
            self._memory.set_last_acted_sequence(observed)
            log.info(
                "adopting directive sequence %d as this device's baseline without acting on it",
                observed,
                extra={"event": "directive.baselined", "wall_id": self._wall_id, "sequence": observed},
            )
            return False

        if observed == acted_on:
            return False

        if observed < acted_on:
            # The counter lives in the catalogue, and a restore can bring back an
            # older one. That is not a directive, and treating it as one would
            # replay whatever pin was current when the backup was taken.
            self._memory.set_last_acted_sequence(observed)
            log.warning(
                "the manifest's directive sequence went backwards (%d after %d); re-baselining without acting, "
                "which is what a catalogue restore looks like from here",
                observed,
                acted_on,
                extra={"event": "directive.regressed", "wall_id": self._wall_id, "sequence": observed, "previous": acted_on},
            )
            return False

        # Latest-wins coalescing needs no code: two `next` calls inside one poll
        # interval advance the counter twice and are observed once, which is one
        # step. That is the intended behaviour and not an approximation of it.
        #
        # **The sequence is consumed after the attempt, never before.** Every path
        # below can raise the display's unavailable error, and a directive marked
        # acted-on while the set was asleep is a `show_now` the curator never
        # gets: the manifest does not change, so nothing would ever present it
        # again. Recording it afterwards means an outage delays the jump instead
        # of eating it.
        #
        # An attempt that *completes* and shows nothing — a pin whose render is
        # missing — is still an attempt, and is consumed. Retrying that one every
        # second would fill the journal with a failure that will not change until
        # a file appears.
        #
        # **A jump onto a television somebody is watching is not attempted at
        # all**, and is therefore not consumed: the curator gets their picture
        # when the set comes back to art mode, by the same rule that makes an
        # outage delay a jump rather than eat it. Checked here rather than in
        # `_advance`, so the baselining and regression arms above still keep this
        # device's sequence honest while the wall is somebody else's.
        #
        # **The wait is read before the display is asked, and that order is the
        # whole point.** This path has no timer of its own: an unconsumed
        # directive is still unconsumed on the next poll, so anything downstream
        # of a question put to the television is asked again a second later, all
        # evening. Asking whether the wall is ours costs a real request, so
        # putting that question in front of the wait would spend thousands of
        # them across one programme.
        if not display.may_attempt():
            return False
        if not await display.is_ours():
            return False

        if manifest.pinned_work_id is None:
            outcome = await self._advance(manifest, display)
            if outcome is Shown.WALL_UNCHANGED:
                # Left unconsumed, exactly as the pinned branch below leaves a
                # jump the wall never made. A `next` the television took and did
                # not act on has not stepped anything, and the manifest does not
                # change when a directive fails — so consuming it here would
                # evaporate the curator's press and log a step that never
                # happened.
                return False
            self._memory.set_last_acted_sequence(observed)
            log.info(
                "directive %d: stepping to the next work",
                observed,
                extra={"event": "directive.acted", "wall_id": self._wall_id, "sequence": observed, "directive": "next"},
            )
            return outcome is Shown.YES

        position = manifest.index_of(manifest.pinned_work_id)
        if position is None:
            self._memory.set_last_acted_sequence(observed)
            # `show_now` refuses a work that could not reach the wall, but it does
            # not check theme membership — only this plane can know what to do
            # with a pin it cannot resolve. Carrying on rotating is the same
            # posture as a missing render file: say so once, never stall the wall.
            log.warning(
                "directive %d pins work %s, which the active theme does not carry; continuing to rotate",
                observed,
                manifest.pinned_work_id,
                extra={
                    "event": "directive.pin_unresolvable",
                    "wall_id": self._wall_id,
                    "sequence": observed,
                    "pinned_work_id": manifest.pinned_work_id,
                },
            )
            return False

        # Rotation continues *from* the pin rather than resuming where it was, so
        # the next step is the work after the pinned one.
        self._cursor = (self._order.index(position) + 1) % len(self._order)
        outcome = await self._show(manifest.entries[position], display)
        if outcome is Shown.WALL_UNCHANGED:
            # Left unconsumed, by the same rule that leaves it unconsumed through
            # an outage: the jump is delayed rather than eaten. A television that
            # took the request and displayed nothing has not performed the jump,
            # and recording it here would mean the curator's pin evaporated while
            # the panel was dark and the wall came back on some other picture.
            return False
        self._memory.set_last_acted_sequence(observed)
        log.info(
            "directive %d: jumping to work %s",
            observed,
            manifest.pinned_work_id,
            extra={"event": "directive.acted", "wall_id": self._wall_id, "sequence": observed, "directive": "show_now"},
        )
        return outcome is Shown.YES

    # -- rotation ----------------------------------------------------------

    async def _rotate_if_due(self, manifest: Manifest, display: Display) -> None:
        """Step the wall on when the interval is up — and only then.

        **The clock is stamped before the attempt, not after a success**, which is
        what bounds a theme nothing can be shown from. Every entry logs one
        WARNING as it is skipped, so a forty-work theme with a pruned image tree
        costs forty lines *per interval* rather than forty lines per second. The
        second cadence is not a tidiness problem: journald rate-limits, and the
        lines it drops are the ERRORs this plane's only failure channel exists to
        carry.
        """
        due_after = manifest.rotation_interval_seconds
        if self._attempted_at is not None and self._clock.monotonic() - self._attempted_at < due_after:
            return
        if not display.may_attempt():
            # Gated by the same wait as a jump. The rotation interval is normally
            # the longer of the two, so this only bites where the backoff has
            # grown past it — a set left dark for hours.
            return
        if not await display.is_ours():
            # **The clock is deliberately not stamped.** An interval the wall was
            # never allowed to use has not been spent, so when the set comes back
            # to art mode the picture should change at once rather than sit out
            # the remainder of a rotation nobody could see.
            return
        self._attempted_at = self._clock.monotonic()
        await self._advance(manifest, display)

    async def _advance(self, manifest: Manifest, display: Display) -> Shown:
        """Show the next work that can be shown, skipping the ones that cannot.

        Bounded by the length of the list, so a theme whose every render is
        missing logs its warnings once per pass and returns, rather than spinning
        on a loop that can never succeed.

        **Returns the outcome rather than a boolean, and the distinction is load
        bearing.** "Nothing here could be shown" and "the wall would not change"
        are both failures to move the picture and they want opposite answers from
        a caller holding a directive: the first is the curator's own theme having
        no usable render, which is consumed and reported, while the second is the
        jump never having been attempted, which must be left for the wall coming
        back.
        """
        if not self._order:
            return Shown.SKIP
        for _ in range(len(self._order)):
            resume_at = self._cursor
            position = self._order[self._cursor]
            self._cursor = (self._cursor + 1) % len(self._order)
            if self._cursor == 0 and manifest.shuffle:
                # A new order for each pass through the theme. Shuffling once and
                # keeping it would give the household the same "random" sequence
                # every day, which reads as a bug in the shuffle.
                self._rng.shuffle(self._order)
            outcome = await self._show(manifest.entries[position], display)
            if outcome is Shown.YES:
                return Shown.YES
            if outcome is Shown.WALL_UNCHANGED:
                # The place is given back rather than consumed. A television that
                # displayed nothing has not shown this work, so the wall coming
                # back should show it — not the one after it. Without this, an
                # evening with the panel dark would walk the whole theme and the
                # first picture of the morning would be wherever that landed.
                self._cursor = resume_at
                return Shown.WALL_UNCHANGED
        return Shown.SKIP

    async def _show(self, entry: Entry, display: Display) -> Shown:
        """Put one work on the wall through the display, or say why it could not be."""
        picture = self._picture(entry)
        with work_context(entry.work_id):
            if not picture.path.is_file():
                if not self._say_missing_once or entry.work_id not in self._missing:
                    self._missing.add(entry.work_id)
                    log.warning(
                        "skipping %s: its render is not at %s",
                        entry.work_id,
                        picture.path,
                        extra={"event": "rotation.render_missing", "wall_id": self._wall_id, "render_path": str(picture.path)},
                    )
                return Shown.SKIP
            outcome = await display.show(picture)
        if outcome is Shown.YES:
            # Recorded only once the display is showing it. A work written here on
            # the strength of the request alone would make a restart re-show
            # something that was never on the wall, and would tell every label of
            # the wall to caption a picture nobody can see.
            self._memory.set_last_selected_work_id(entry.work_id)
            self._attempted_at = self._clock.monotonic()
            self._has_shown = True
        return outcome

    def _picture(self, entry: Entry) -> Picture:
        theme_id = self._manifest.theme_id if self._manifest is not None else None
        return Picture(
            work_id=entry.work_id,
            path=self._render_root / entry.render_path,
            title=entry.label.get("title") or entry.work_id,
            theme_id=theme_id,
        )
