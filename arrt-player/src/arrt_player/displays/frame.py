"""The Frame: a television that holds its own pictures, behind the `TvClient` seam.

Uploads go into the set's own store, a picture is selected by the set's content
id, and the set is asked whether it is in art mode before anything touches it.
The binding table that joins a work to its content id lives in the device's own
store (`state.DisplayState`), which outlives the process because the set holds
the picture between restarts.

Three behaviours are worth reading before changing anything here, because each
was chosen against an alternative that looks more obvious:

**Uploads are spread across passes rather than done in a batch on adoption.** A
fresh install has an empty binding table and a theme of forty works, and each
upload costs the set the better part of ten seconds. Doing them all before the
first `select_image` leaves the wall on yesterday's picture for five minutes and,
worse, leaves a curator pressing "next" with nothing happening for five minutes —
against a poll interval that is one second precisely because that wait is the one
the product may not have. So the wall shows what it can as soon as it can, and
carries one pending upload per pass until the theme is complete.

**The television going away is an expected operating condition.** The set is
asleep most of the time; a connection failure is a backoff, not an incident, and
the picture stays up regardless because the television holds it.

**It draws no label.** It reports what the screen is doing (`display_state`),
and every label of the wall — on this client or any other — follows that report
through the server (`labels-and-surfaces.md`; `label_renderer.py`).
"""

import logging
import random
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from arrt_player import brightness as brightness_module
from arrt_player.config import Settings
from arrt_player.episodes import Backoff, ReportOnce
from arrt_player.heartbeat import DisplayReport, ScreenState
from arrt_player.logs import work_context
from arrt_player.manifest import Watcher
from arrt_player.programmes.rotation import Rotation
from arrt_player.programmes.schedule import Schedule
from arrt_player.state import Binding, DisplayState, UploadStatus
from arrt_player.tv import (
    PowerStateUnreadable,
    RemovalOutcome,
    SelectionAnnouncement,
    TvClient,
    TvRemovalUnconfirmed,
    TvUnavailable,
    TvUploadFailed,
)
from arrt_player.wall import Capabilities, Clock, DisplayRecord, Picture, Shown, Wall

log = logging.getLogger(__name__)


def frame_wall(
    *,
    settings: Settings,
    tv: TvClient,
    state: DisplayState,
    watcher: Watcher,
    clock: Clock,
    rng: random.Random | None = None,
) -> Wall:
    """A wall on the Frame: the shared loop, this driver, and a programme per major, remembering in the store."""
    return Wall(
        wall=settings,
        display=FrameDisplay(settings=settings, tv=tv, state=state, clock=clock),
        programmes={
            1: Rotation(wall_id=settings.wall_id, render_root=settings.render_root, memory=state, clock=clock, rng=rng),
            2: Schedule(wall_id=settings.wall_id, render_root=settings.render_root, memory=state, clock=clock),
        },
        watcher=watcher,
        clock=clock,
    )


class FrameDisplay:
    """One television, as a wall's display."""

    unavailable: tuple[type[Exception], ...] = (TvUnavailable,)
    journal_name = "daemon"
    description = "the Frame"

    def __init__(self, *, settings: Settings, tv: TvClient, state: DisplayState, clock: Clock) -> None:
        self._settings = settings
        self._tv = tv
        self._state = state
        self._clock = clock

        #: What the set last announced about its own wall, which is the only
        #: honest account of it this product has. Written from the television's
        #: reader task, read here — a plain assignment either way, so no lock:
        #: it is one reference, and a reader that catches the previous value gets
        #: a stale id rather than a torn one.
        self._announced_content_id: str | None = None
        #: The announcement itself, kept so the wall's own task can tell a new
        #: one from one it has already taken — by identity, so the same picture
        #: announced twice is still two pieces of news.
        self._announcement: SelectionAnnouncement | None = None
        self._announcement_taken: SelectionAnnouncement | None = None
        tv.observe_selections(self._note_announcement)

        #: The set's id for the picture on the wall: this plane's own confirmed
        #: selection, or one the set announced as shown that somebody chose with
        #: the remote. None until either has happened.
        self._wall_content_id: str | None = None
        #: What the wall's screen is doing. **Unreachable until the set has been
        #: asked**, which is the contract's word for "the controller cannot tell"
        #: — a fresh process has not asked anything yet, and a guess would be a
        #: reading nobody took.
        self.record = DisplayRecord(
            clock,
            wall_id=settings.wall_id,
            initial=DisplayReport(state=ScreenState.UNREACHABLE, work_id=None, since=clock.now()),
        )
        #: `PowerState` would not answer while `get_artmode` did. The wall is
        #: reported in use (every label blanks either way); said once per episode.
        self._power_unreadable = ReportOnce()

        #: Whether the set was showing art the last time it was actually asked.
        #: **None until it has been**, rather than defaulting to either answer: the
        #: gate is only consulted when something is about to happen, so a fresh
        #: process genuinely does not know, and a heartbeat that guessed would be
        #: reporting a read nobody performed.
        self._showing_art: bool | None = None

        self._last_error: str | None = None

        #: The wall is taking selections and displaying none of them. A television
        #: whose panel is dark stays dark for hours, and a line per rotation would
        #: be a hundred a night saying the one thing that has not changed.
        self._wall_unchanged = ReportOnce()

        #: Somebody is watching their own television. Reported at INFO rather than
        #: WARNING because that is not a fault — but still reported, because "the
        #: wall stopped" otherwise has no explanation in the journal at all.
        self._not_our_wall = ReportOnce()

        #: When the wall may next be asked to change, once it has been found not
        #: changing. **Rotation has a timer and the directive path does not**, so
        #: without this a `show_now` left unconsumed — which is the right thing to
        #: do with a jump that never happened — would be re-asked on every poll: a
        #: selection a second, each waiting out the confirmation window, all night
        #: at a set that will ignore every one. It backs off on the same ladder as an unreachable
        #: television, because "the set is not doing what it is told" is that same
        #: situation arriving by a route that raises nothing.
        self._wall_retry = Backoff(
            minimum=settings.tv_retry_min_seconds,
            maximum=settings.tv_retry_max_seconds,
            monotonic=clock.monotonic,
        )

        #: Reconciling the binding table against the set is **owed until it is
        #: done**, not attempted once when a manifest lands. A new manifest is
        #: reported by the watcher on exactly one pass; if the set is asleep on
        #: that pass — which this module's own note says is most of them — the
        #: pass aborts, and tying the work to that one flag drops orphan removal
        #: entirely rather than deferring it.
        self._reconciliation_owed = False
        #: When reconciliation may next be attempted. It stays *owed* through a
        #: television that cannot say what it removed, and without this it would
        #: then be retried at the poll rate — one listing, one removal request and
        #: one INFO line a second.
        #:
        #: **The same `Backoff` the connection and the upload retry use**, at a
        #: fixed wait rather than a doubling one — equal bounds make `hold`'s
        #: ladder a constant.
        self._reconcile_wait = Backoff(
            minimum=settings.tv_retry_max_seconds,
            maximum=settings.tv_retry_max_seconds,
            monotonic=clock.monotonic,
        )
        self._brightness_at: float | None = None
        self._brightness_value: int | None = None

        #: The set could not be reached at all. Its own ladder, separate from the
        #: wall's: a television that is asleep and one that is awake and ignoring
        #: selections are different conditions, and recovering from one says
        #: nothing about the other.
        self._connection_retry = Backoff(
            minimum=settings.tv_retry_min_seconds,
            maximum=settings.tv_retry_max_seconds,
            monotonic=clock.monotonic,
        )
        self._unavailable = ReportOnce()

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def start_lines(self) -> dict[str, object]:
        return self._settings.startup_lines()

    # -- the pass ----------------------------------------------------------

    def adopted(self, pictures: Sequence[Picture]) -> None:  # noqa: ARG002 -- the wall.Display protocol's signature
        self._reconciliation_owed = True
        # A new manifest clears any wait: it is new information, and it is
        # usually what arrives after somebody has fixed whatever the set was
        # unhappy about. The wait exists to stop a *retry* loop, not to make
        # the wall ignore news.
        self._reconcile_wait.clear()

    async def prepare(self, pictures: Sequence[Picture]) -> None:
        await self._connected()
        await self._take_the_sets_news()
        if self._reconciliation_owed and self._reconcile_wait.is_due():
            # Cleared only when the work actually settled: a set that goes
            # away halfway through raises, and one that cannot say what it
            # removed reports so — both leave the work owed for a later pass
            # rather than recorded as done.
            self._reconciliation_owed = not await self._reconcile_with_the_set(pictures)
            if self._reconciliation_owed:
                self._reconcile_wait.hold()
            else:
                self._reconcile_wait.clear()
        await self._apply_brightness()

    async def after(self, pictures: Sequence[Picture]) -> None:
        await self._upload_one_pending(pictures)

    async def idle(self) -> None:
        return

    def went_away(self, exc: Exception) -> float:
        """Report the television going away once, then wait longer each time.

        Once, because an asleep set is the normal overnight condition and one
        WARNING a second until morning buries every other line in the journal. The
        recovery is logged too, so the pair reads as an episode with a length.
        """
        # **Not cleared by a good pass.** A plane that dropped its error the
        # moment anything succeeded would report itself fine while failing every
        # other minute. It is overwritten by the next failure, so it is always
        # the latest rather than the first.
        self._last_error = str(exc)
        self.record.moved_to(ScreenState.UNREACHABLE)
        if self._unavailable.begin():
            log.warning("%s; holding the wall where it is and retrying", exc, extra={"event": "tv.unavailable"})
        return self._connection_retry.hold()

    def answering(self) -> None:
        if self._unavailable.end():
            log.info("the television is answering again", extra={"event": "tv.recovered"})
        self._connection_retry.clear()

    def heartbeat_fields(self, *, reachable: bool | None) -> dict[str, Any]:
        return {
            "announced_content_id": self._announced_content_id,
            "television_reachable": reachable,
            "television_showing_art": self._showing_art,
            # **The Frame draws no label**, so it reports none, as a screen does.
            # A client's panel is reported as a label output in the client
            # heartbeat, connected or not (`label_renderer.LabelPanel`).
            "has_label_surface": False,
            "label_surface_working": None,
        }

    def capabilities(self) -> Capabilities:
        """The Frame's size is not this Player's to know until its geometry moves here from the server.

        So its screen is None and the heartbeat leaves capabilities out. It
        draws no text of its own until this Player composes a caption into the
        picture it uploads, so `none` is the only label mode it can claim.
        """
        return Capabilities(screen=None, backend="frame", label_modes=("none",))

    async def close(self) -> None:
        await self._tv.close()

    # -- changing the wall -------------------------------------------------

    def may_attempt(self) -> bool:
        """Whether the wall may be asked to change again yet.

        False after an attempt the television took and did not act on, and after
        finding somebody else using the set. A television behaving normally in art
        mode has no wait, so nothing here delays a rotation or a jump in normal
        operation.

        **An announcement from the set clears the wait**, because it is news
        rather than a retry — the same rule a new manifest gets. Without it,
        somebody switching from a programme back to art mode would watch a blank
        wall for the remainder of a backoff that had grown to five minutes; with
        it, the next poll asks again and the picture comes back in about a second.
        The clearing happens in `_take_the_sets_news`, at the top of every pass
        that reaches the set, so this only reads the wait.
        """
        return self._wall_retry.is_due()

    async def is_ours(self) -> bool:
        """Whether the set is showing art, and may therefore be asked to change it.

        **The television belongs to whoever is using it**
        (`nonfunctional-requirements.md`). Selecting an image on a set showing a
        programme does not fail politely: it switches the set into art mode and
        takes the screen off the person watching. So nothing reaches the wall
        without asking first, and a no freezes everything — no selection, no
        advance through the theme, no directive consumed — exactly as a wall that
        would not change does.

        **Asked only when something is about to happen**, which is what keeps a
        one-second poll from becoming a request per second: rotation consults this
        when its interval is up, and the directive path only when a sequence has
        actually moved. A no then backs off on the shared ladder, so a whole
        evening of television costs a handful of reads rather than thousands.
        """
        showing = await self._read_art_mode()
        if showing:
            if self._not_our_wall.end():
                log.info(
                    "the television is showing art again; resuming the rotation",
                    extra={"event": "rotation.wall_returned"},
                )
            return True

        if self._not_our_wall.begin():
            # Said once for the same reason a dark wall is: somebody watches
            # television for hours, and a line per attempt would bury the ERRORs
            # that are this plane's only failure channel.
            log.info(
                "the television is not in art mode; leaving the wall alone until it is",
                extra={"event": "rotation.wall_not_ours"},
            )
        self._hold_off_the_wall()
        return False

    async def show(self, picture: Picture) -> Shown:
        """Select one picture on the set, uploading it first if it has no binding."""
        content_id = await self._content_id_for(picture)
        if content_id is None:
            return Shown.SKIP

        try:
            shown = await self._tv.show(content_id)
        except TvUnavailable:
            content_id = await self._rebind_or_reraise(picture, content_id)
            if content_id is None:
                return Shown.SKIP
            shown = await self._tv.show(content_id)

        if not shown:
            await self._report_wall_unchanged(content_id)
            self._hold_off_the_wall()
            return Shown.WALL_UNCHANGED
        self._wall_is_answering()

        self._wall_content_id = content_id
        self._showing_art = True
        self.record.moved_to(ScreenState.SHOWING_ART, picture.work_id)
        if self._wall_unchanged.end():
            log.info(
                "the television is changing what it displays again",
                extra={"event": "rotation.wall_recovered"},
            )
        log.info(
            "showing %s",
            picture.title,
            extra={
                "event": "rotation.selected",
                "tv_content_id": content_id,
                "theme_id": picture.theme_id,
            },
        )
        return Shown.YES

    def _hold_off_the_wall(self) -> None:
        """Back off before asking again, and lengthen the wait each time.

        Bounded by the same ceiling as a reconnection, so a night with the panel
        off costs a handful of attempts rather than one a second — and the wall
        resumes within that ceiling of somebody switching the set back on.
        """
        self._wall_retry.hold()

    def _wall_is_answering(self) -> None:
        """Forget the backoff, because the set is acting on what it is told."""
        self._wall_retry.clear()

    async def _report_wall_unchanged(self, content_id: str) -> None:
        """Say once that the set is taking selections and displaying none of them.

        **The flag is read here for the operator, and separately before every
        selection for the wall's own safety.** The two readings answer different
        questions and neither replaces the other: the gate asks *may this
        television be touched at all*, and this line answers *why is it not
        changing* for somebody reading the journal. This one costs a call on a
        rotation that has already failed, so it is free in the ordinary case.
        """
        if not self._wall_unchanged.begin():
            return
        mode = await self._tv.reported_art_mode()
        log.warning(
            "the television accepted %s and is not displaying it; "
            "it reports art mode %s. Rotation is deferred until the wall changes",
            content_id,
            mode if mode is not None else "nothing at all",
            extra={
                "event": "rotation.wall_unchanged",
                "tv_content_id": content_id,
                "art_mode": mode,
            },
        )

    # -- what the set says -------------------------------------------------

    def _note_announcement(self, announcement: SelectionAnnouncement) -> None:
        """Remember what the set says is on its wall. Runs on the client's reader task.

        Deliberately the cheapest thing that could work: one assignment, no I/O,
        no lock, nothing that can raise. Everything this could trigger happens on
        the wall's own task instead — see `_take_the_sets_news`.

        **It records announcements this plane did not cause**, which is the point
        of subscribing at all: somebody using the remote changes the wall, and
        the display state — which every label of the wall follows — should say
        what is actually up rather than what we last put there.
        """
        self._announced_content_id = announcement.content_id
        self._announcement = announcement

    async def _take_the_sets_news(self) -> None:
        """Act, on the wall's own task, on what the set has said since the last pass.

        Two kinds of news, both already heard and neither a new question put to
        the set on a timer. **A picture announced as shown** is the wall changing
        — this plane's own selection echoed back, or somebody with the remote —
        and it is art on the wall, resolved to a work through the bindings. **An
        art-mode announcement** (which connecting also counts as) is the set
        saying its mode may have changed: it clears the wall's wait, as it always
        has, and is now also answered with one fresh `get_artmode` read, so the
        display state follows the set within a pass of the set saying so rather
        than at the next rotation. One read per announcement, never per poll.
        """
        announcement = self._announcement
        if announcement is not None and announcement is not self._announcement_taken:
            self._announcement_taken = announcement
            if announcement.is_shown:
                self._wall_content_id = announcement.content_id
                self._showing_art = True
                self.record.moved_to(ScreenState.SHOWING_ART, self._work_bound_to(announcement.content_id))
        if self._tv.art_mode_announcement_pending():
            self._wall_is_answering()
            await self._read_art_mode()

    def _work_bound_to(self, content_id: str) -> str | None:
        """The work this device put on the set under `content_id`, or None for a picture it did not put there."""
        for binding in self._state.bindings():
            if binding.tv_content_id == content_id:
                return binding.artwork_id
        return None

    async def _read_art_mode(self) -> bool:
        """Ask the set whether it is showing art, and let the display state follow the answer.

        A yes is art on the wall: the picture last known to be there, which may
        be one nothing here can name. A no is somebody else's screen or a dark
        one, and only `PowerState` tells those apart — see `_screen_is_not_ours`.
        """
        showing = await self._tv.showing_art()
        self._showing_art = showing
        if showing:
            content_id = self._wall_content_id
            self.record.moved_to(ScreenState.SHOWING_ART, self._work_bound_to(content_id) if content_id is not None else None)
        else:
            await self._screen_is_not_ours()
        return showing

    async def _screen_is_not_ours(self) -> None:
        """`get_artmode` said no: report the set in use, or dark if `PowerState` says standby.

        **Read only here, straight after a `get_artmode` no**, so it adds no
        cadence of its own: it rides a read this loop was already taking. Both
        states blank the label, so the read decides only what Walls says; a
        failed read therefore reports `in_use` — the screen is somebody's or off,
        and of the two, "in use" is the one that cannot wrongly tell a curator a
        lit screen is off — and says so once per episode.
        """
        try:
            power = await self._tv.power_state()
        except PowerStateUnreadable as exc:
            if self._power_unreadable.begin():
                log.info(
                    "could not read whether the television's panel is lit (%s); reporting it in use",
                    exc,
                    extra={"event": "display.power_unreadable"},
                )
            self.record.moved_to(ScreenState.IN_USE)
            return
        if self._power_unreadable.end():
            log.info("the television's panel power can be read again", extra={"event": "display.power_readable"})
        self.record.moved_to(ScreenState.DARK if power == "standby" else ScreenState.IN_USE)

    # -- bindings ----------------------------------------------------------

    async def _content_id_for(self, picture: Picture) -> str | None:
        """This work's id on the television, uploading it now if it has none."""
        binding = self._state.binding_for(picture.work_id)
        if binding is not None and _is_current(binding, picture.path):
            return binding.tv_content_id
        if self._too_soon_to_retry(binding):
            return None
        return await self._upload(picture)

    def _too_soon_to_retry(self, binding: Binding | None) -> bool:
        """Whether a work that failed to upload should be left alone this pass.

        **A set that is reachable and refuses one image does not back off with the
        connection**, which is the other failure and has its own retry. Without
        this, one bad render is a round trip, a WARNING and a rewritten row every
        second for as long as it stays in the theme — an unbounded small-write
        source on the SD card that `observability-strategy.md` says not to build,
        and a journal in which the rate limiter starts dropping the lines that
        matter.

        Measured against wall time, because the failure is recorded in the store
        and must outlive the process: under `Restart=always` an elapsed-time wait
        would reset on every restart, so a crash loop would become a retry loop.
        """
        if binding is None or binding.upload_status is not UploadStatus.FAILED:
            return False
        waited = (self._clock.now() - binding.uploaded_at).total_seconds()
        return waited < self._settings.upload_retry_seconds

    async def _rebind_or_reraise(self, picture: Picture, refused: str) -> str | None:
        """Work out whether the set is gone or the *binding* is, and fix the second.

        **A refused selection is ambiguous and the library cannot disambiguate
        it** — a dead websocket and an id the set has never heard of arrive as the
        same failure. Guessing "outage" is the expensive mistake: somebody
        removing one image from the phone app would freeze the wall on a backoff
        that retries the same doomed id forever, because the manifest never
        changes and nothing else would ever re-check that binding.

        So the question is put to the television, which is this codebase's
        standing answer to a client whose return values cannot be trusted in
        either direction: if the set still lists the id, the fault is not the
        binding and the original failure stands. If the listing itself fails,
        that is a real outage and it propagates from here.

        **The connection is re-established first, and without that this whole
        method is unreachable.** The failure that sends us here arrives from the
        television client, which drops and closes its connection on *any* failure
        — it holds a websocket whose state after an error is not knowable, so it
        refuses to reason on it. The very next request would therefore raise "not
        connected" rather than reaching the set, the outage arm would swallow it,
        and every branch below would be dead code. Reconnecting costs nothing when
        the set is there and raises the real outage when it is not, which is
        exactly the distinction being drawn.
        """
        await self._connected()
        listed = await self._tv.listed_content_ids()
        if refused in listed:
            raise TvUnavailable(f"the television refused to select {refused}, which it says it is holding")

        self._state.mark_orphaned(picture.work_id)
        log.warning(
            "the television refused %s and does not list it; re-uploading %s",
            refused,
            picture.work_id,
            extra={"event": "binding.orphaned", "tv_content_id": refused},
        )
        return await self._upload(picture)

    async def _upload(self, picture: Picture) -> str | None:
        """Send one render to the television and record what happened.

        A failure is recorded, not merely logged: the store keeps `failed` apart
        from "no row at all", so a work that fails every pass is visible in the
        device's own state rather than only in a journal that does not survive a
        reboot.
        """
        fingerprint = _fingerprint(picture.path)
        try:
            content_id = await self._tv.upload(picture.path)
        except TvUploadFailed as exc:
            self._state.record_upload_failure(picture.work_id)
            log.warning(
                "could not put %s on the television (%s)",
                picture.work_id,
                exc,
                extra={"event": "binding.upload_failed"},
            )
            return None

        self._state.record_upload(picture.work_id, content_id, render_fingerprint=fingerprint)
        log.info(
            "uploaded %s to the television as %s",
            picture.work_id,
            content_id,
            extra={"event": "binding.uploaded", "tv_content_id": content_id},
        )
        return content_id

    async def _upload_one_pending(self, pictures: Sequence[Picture]) -> None:
        """Carry one not-yet-uploaded work per pass, so the theme fills in behind us.

        Deliberately one, not all: see this module's opening note. A pass that
        uploaded the whole theme would hold the loop — and every directive — for
        as long as the theme is long.
        """
        for picture in pictures:
            binding = self._state.binding_for(picture.work_id)
            if _is_current(binding, picture.path):
                continue
            if self._too_soon_to_retry(binding):
                continue
            if not picture.path.is_file():
                # Not a failure to record: nothing was attempted, and writing a
                # `failed` row for a file curation has not produced yet would make
                # the store report an upload problem for a preparation one.
                continue
            with work_context(picture.work_id):
                await self._upload(picture)
            return

    async def _reconcile_with_the_set(self, pictures: Sequence[Picture]) -> bool:
        """Compare what this device believes against what the television lists.

        Runs when a manifest is adopted, not every pass. The comparison costs a
        real request to the set, and at a one-second poll that would be a call per
        second forever — traffic that buys nothing, since nothing changes what the
        television holds except this process.
        """
        listed = await self._tv.listed_content_ids()

        for picture in pictures:
            binding = self._state.binding_for(picture.work_id)
            if binding is None or not binding.is_on_the_television:
                continue
            if binding.tv_content_id in listed:
                continue
            # The set stopped listing an image this device uploaded — removed from
            # the phone app, or forgotten across a factory reset. Recorded as
            # orphaned so the row cannot be mistaken for a live binding, which
            # would otherwise send `select_image` at an id the set does not know.
            self._state.mark_orphaned(picture.work_id)
            log.warning(
                "the television no longer lists %s for work %s; it will be uploaded again",
                binding.tv_content_id,
                picture.work_id,
                extra={"event": "binding.orphaned", "tv_content_id": binding.tv_content_id, "work_id": picture.work_id},
            )

        return await self._remove_orphans(listed)

    async def _remove_orphans(self, listed: frozenset[str]) -> bool:
        """Take off the television everything this device cannot account for.

        **The binding table is the whole authority**, which is why a fresh install
        clears the set: images uploaded by a previous generation of this product
        are not assets to adopt, because nothing joins them to a work — the 2024
        tree addressed images by source URL and by a resized filename, and a
        manifest entry names an artwork id and a UUID render. Adopting one would
        bind a work to a picture that is not the render its entry names, and the
        wall would show one composition while the catalogue recorded another.

        The television has exactly one user-upload category, so the alternative to
        removing them is two generations of the same corpus accumulating in it.
        """
        accounted = self._state.accounted_content_ids()
        orphans = sorted(listed - accounted)
        if not orphans:
            return True

        try:
            outcome: RemovalOutcome = await self._tv.remove(orphans)
        except TvRemovalUnconfirmed as exc:
            # Unknown is reported as unknown. The images stay listed and the next
            # pass tries again; claiming either outcome here would be a guess, and
            # this is the verb whose reply the library discards.
            log.warning(
                "could not establish whether %d unaccounted-for images were removed (%s)",
                len(orphans),
                exc,
                extra={"event": "tv.orphan_removal_unconfirmed", "requested": orphans},
            )
            return False

        log.info(
            "removed %d image(s) the binding table does not account for",
            len(outcome.removed),
            extra={
                "event": "tv.orphans_removed",
                "removed": list(outcome.removed),
                "surviving": list(outcome.surviving),
            },
        )
        # **Settled even when some survived.** An incomplete removal is a *known*
        # outcome — the set was asked, answered, and is keeping them — and it is
        # already reported at WARNING by the client. Asking again immediately
        # learns nothing; the next manifest re-arms the work. Only an outcome
        # nobody could establish stays owed.
        return True

    # -- the television ----------------------------------------------------

    async def _connected(self) -> None:
        """Ensure there is a live connection, and that the set's own slideshow is off."""
        await self._tv.connect()
        if not self._state.native_slideshow_disabled:
            await self._tv.disable_native_slideshow()
            self._state.mark_native_slideshow_disabled()
            log.info(
                "disabled the television's own slideshow, which would otherwise change the picture underneath us",
                extra={"event": "tv.native_slideshow_disabled"},
            )

    async def _apply_brightness(self) -> None:
        """Follow the sun, and write to the set only when the value actually changes."""
        elapsed = self._clock.monotonic()
        if self._brightness_at is not None and elapsed - self._brightness_at < self._settings.brightness_interval_seconds:
            return
        self._brightness_at = elapsed

        state = brightness_module.sun_state(
            self._clock.now(),
            latitude=self._settings.latitude,
            longitude=self._settings.longitude,
            location_name=self._settings.location_name,
            location_region=self._settings.location_region,
        )
        value = brightness_module.television_brightness(
            state.relative_brightness,
            minimum=self._settings.tv_min_brightness,
            maximum=self._settings.tv_max_brightness,
        )
        if value == self._brightness_value:
            return

        await self._tv.set_brightness(value)
        self._brightness_value = value
        log.info(
            "set panel brightness to %d",
            value,
            extra={
                "event": "brightness.set",
                "brightness": value,
                "solar_angle": round(state.solar_angle_degrees, 2),
            },
        )


def _fingerprint(render: Path) -> str | None:
    """What this render file looks like right now, cheaply.

    **Modification time and size rather than a hash.** The rotation reads this on
    every pass over every entry; hashing forty 2 MB composites a second would be
    real I/O on an SD card, to answer a question a `stat` answers. The pipeline
    that writes these files always rewrites them wholesale, so a change that keeps
    both the size and the nanosecond timestamp is not a case this deployment can
    produce.

    None when the file cannot be read, which is treated as "unknown" and never as
    "unchanged" — see `_render_changed`.
    """
    try:
        stat = render.stat()
    except OSError:
        return None
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def _is_current(binding: Binding | None, render: Path) -> bool:
    """Whether this work's picture is already on the television, and still right.

    **One question with two callers**, which is why it is a function rather than
    a condition written twice: one caller decides whether a content id can be
    reused, the other whether an upload still needs carrying, and they are the
    same question asked from opposite ends. Written out twice they drifted once
    already — the fingerprint half was added because the first reading was
    incomplete, and had it been added to only one of the two the wall would show
    a stale composition for exactly as long as nobody looked.
    """
    return binding is not None and binding.is_on_the_television and not _render_changed(binding, render)


def _render_changed(binding: Binding, render: Path) -> bool:
    """Whether the file on disk is no longer the one the television was given.

    **The defect this closes is invisible from the wall.** `render_path` is
    `ready/{artwork_id}.jpg` and stable across re-renders, so a curator changing a
    mat colour rewrites the bytes under an unchanged name; the binding still reads
    `uploaded`, and the television goes on showing the old composition for ever.
    Both `set_mat_color` and `regenerate` are live actions, so this is reachable
    by ordinary use rather than by mishap. A pulled render is named by its
    hash, so a re-render arrives under a new name instead; the fingerprint is
    what notices a change either way.

    A binding with no recorded fingerprint — every row written before the column
    existed — counts as changed. That costs one re-upload per work on the first
    pass after an upgrade, which is the honest price of never having looked.
    """
    return binding.render_fingerprint != _fingerprint(render)
