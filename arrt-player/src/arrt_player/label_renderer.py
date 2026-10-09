"""A label renderer: one label output, captioning whichever wall the server maps it to.

`labels-and-surfaces.md` § The model. The supervisor runs one renderer per label
output that `GET /client` maps (`client.Supervisor`), on whatever client holds
the panel; the wall it captions may be shown by another client entirely. Every
second the renderer asks for its label document (`pull.LabelPull`, through the
one module allowed an HTTP client), applies the label rule (`label_rule.py`) at
its own clock, and redraws only when what the panel would show changes.

**Two objects, because they live for different lengths of time.** `LabelPanel`
is the panel: opened once per process, reported in the client heartbeat whether
or not anything is mapped to it, and it keeps the draw gate and the panel's own
failure episodes, which belong to the device whatever it captions. A
`LabelRenderer` is one mapping, started and stopped with it.

**Nothing in here may stop anything else.** A broken, missing or slow panel costs
the label and nothing more; the walls this client drives carry on. That is the
posture the label had while the Frame loop drew it, kept now that it does not.
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from contextlib import nullcontext
from datetime import datetime
from typing import Final, Protocol

from arrt_player.client import EPAPER_KIND, LabelAssignment, LabelOutputReport
from arrt_player.episodes import ReportOnce
from arrt_player.label_rule import Drawing, LabelDocument, Outcome, drawing_for, offline
from arrt_player.logs import work_context
from arrt_player.panel import Candidate, LabelSurface, Layout, Run, Tier, lay_out, read_label

log = logging.getLogger(__name__)

#: How long a label may spend being drawn before the renderer stops waiting for it.
#:
#: **The whole of the product's label budget rather than a fraction of it.** The
#: label must match what the television is showing within 15 s of the picture
#: changing (`nonfunctional-requirements.md` § Performance), and the panel's own
#: refresh is most of that — so this is the loosest bound that still honours the
#: requirement, and a draw that has passed it has already missed the thing it was
#: for. A healthy 16-level frame takes well under that (`platform-and-dependency-findings.md` § The e-paper panel);
#: what this catches is an SPI transaction that is never coming back, which is the
#: one way a panel could stop a renderer that no `except` clause can reach.
LABEL_DRAW_BUDGET_SECONDS: Final[float] = 15.0


def _forget(draw: "asyncio.Future[Layout]") -> None:
    """Collect an abandoned draw's outcome, so nothing warns about it later."""
    if not draw.cancelled():
        draw.exception()


class LabelPanel:
    """One label output: the panel, whether it works, and the gate on drawing to it.

    `surface` is None for a panel that would not open, and `error` then says
    why. **Reported in the client heartbeat either way**, connected or not,
    because a configured panel that would not open is a device meant to have a
    label that has none, and the server is where a curator can see that.
    """

    def __init__(self, *, name: str, surface: LabelSurface | None, error: str | None, size: tuple[int, int] | None) -> None:
        self.name = name
        self.surface = surface
        self.error = error
        self._size = size
        #: Whether the surface accepted the last drawing it was given. None until
        #: it has been given one; False from the outset for a panel that would not
        #: open, because that one has already failed.
        self.working: bool | None = False if surface is None else None
        self._failed = ReportOnce()
        #: The surface has area and not enough of it to place anything: a
        #: geometry setting, so it lasts until somebody changes one.
        self._unusable = ReportOnce()
        #: The draw handed to a worker thread, kept until it finishes. **A
        #: one-at-a-time gate rather than a queue**, held by the panel rather than
        #: by a renderer: the budget stops a renderer waiting on a hung panel, but
        #: it cannot stop the thread, and a renderer restarted for a new mapping
        #: must not dispatch a second draw into a driver the first is still in.
        self._draw: asyncio.Future[Layout] | None = None

    def report(self) -> LabelOutputReport:
        """This panel as the client heartbeat states it."""
        return LabelOutputReport(
            name=self.name,
            kind=EPAPER_KIND,
            connected=self.surface is not None and self.working is not False,
            size=self._size,
        )

    def close(self) -> None:
        """Release the panel. **On e-paper this is the sleep/power-down**, not bookkeeping."""
        if self.surface is not None:
            self.surface.close()

    async def draw(  # noqa: C901, PLR0912 -- every way a draw can fail is answered in place
        self, drawing: Drawing, *, label_id: str
    ) -> None:
        """Put one drawing on the panel, and say what became of it. Never raises.

        Laid out and drawn on a worker thread, bounded by the label budget: an
        e-paper redraw is seconds of rasterising and SPI, and on the event loop
        it would delay every wall's poll on this client.
        """
        surface = self.surface
        if surface is None:
            return
        if self._draw is not None and not self._draw.done():
            self._would_not_take_it("the previous label is still being drawn", label_id)
            return
        # **The gate is the draw's own state, not a flag somebody remembers to
        # clear.** If the budget runs out while the work item is still *queued*,
        # the thread never starts, so a flag cleared inside it would close the
        # gate for good. Asking the task whether it is finished is right for both
        # the queued case and the running one.
        draw = asyncio.ensure_future(asyncio.to_thread(_lay_out_and_show, surface, drawing))
        self._draw = draw
        finished, _ = await asyncio.wait({draw}, timeout=LABEL_DRAW_BUDGET_SECONDS)
        if not finished:
            # Not cancelled: that would open the gate onto a panel still being
            # written to. Left running, it opens the gate when the panel comes back.
            draw.add_done_callback(_forget)
            self._would_not_take_it(f"the draw ran past the {LABEL_DRAW_BUDGET_SECONDS:g}s label budget", label_id)
            return
        try:
            layout = draw.result()
        # **Not `SurfaceUnavailable` alone**: `measure` on the e-paper surface
        # reaches a text stack through C bindings, which raise GLib errors related
        # to nothing this module can name, outside the `show` that converts them.
        except Exception as exc:  # noqa: BLE001  # prawduct:allow prawduct/broad-except -- a panel never stops anything else
            self._would_not_take_it(str(exc), label_id)
            return

        self.working = True
        if self._failed.end():
            log.info("the label surface is taking labels again", extra={"event": "label.recovered", "label_id": label_id})
        extra = {"label_id": label_id, "display_state": drawing.state}
        if drawing.outcome is Outcome.BLANK:
            # Blank on purpose, and said so by the state that asked for it: the
            # screen in use, dark or absent, or a wall silent past the hold.
            log.info("the panel was drawn blank: the wall is %s", drawing.state, extra={"event": "label.blanked", **extra})
        elif drawing.outcome is Outcome.CARD:
            log.info(
                "the panel shows the card for %s: the wall is %s",
                drawing.wall_name,
                drawing.state,
                extra={"event": "label.card", **extra},
            )
        elif layout.is_empty and layout.dropped:
            # **The whole label had somewhere to be and nowhere to go**: margins
            # that consume the surface place nothing, and "captioning" would name
            # a work whose label is not there. Once per episode, because it is a
            # fact about the device's geometry and holds until somebody changes it.
            if self._unusable.begin():
                log.warning(
                    "the label surface has no usable area at this geometry, so %s was not captioned at all",
                    _title(drawing),
                    extra={"event": "label.unusable", **extra},
                )
        elif layout.is_empty:
            # A record with no label text: a blank surface is right, and it does
            # not prove the surface has usable area, so the episode above stays.
            log.info(
                "%s carries no label text, so the panel was left blank",
                _title(drawing),
                extra={"event": "label.absent", **extra},
            )
        else:
            # **The only line that says the panel is working**, and the edge that
            # ends the unusable episode: a label actually placed is the proof.
            self._unusable.end()
            log.info("the panel is captioning %s", _title(drawing), extra={"event": "label.drawn", **extra})
        if layout.dropped:
            log.info(
                "the label surface had no room for %d line(s) of this label",
                len(layout.dropped),
                extra={"event": "label.truncated", "dropped": list(layout.dropped), "label_id": label_id},
            )
        if layout.shrunk:
            # **The condition the type floor's one exception rests on**: the facts
            # that identify the work shrink rather than vanish, and only this line
            # says so. Warning, because only the operator can fix the device.
            log.warning(
                "the label surface is too small for this label at a legible size; %d line(s) were set below the %d px floor",
                len(layout.shrunk),
                surface.type_scale.floor_px,
                extra={
                    "event": "label.shrunk",
                    "shrunk": list(layout.shrunk),
                    "floor_px": surface.type_scale.floor_px,
                    "smallest_px": min(block.size_px for block in layout.blocks),
                    "label_id": label_id,
                },
            )
        if layout.wrapped:
            # The fault a person found by standing in front of the panel: a name
            # broken mid-phrase by the line breaker, which nothing else reports.
            log.warning(
                "the label surface is too narrow for this name; the line breaker split %r across rows",
                layout.wrapped[0].text,
                extra={
                    "event": "label.name_wrapped",
                    "wrapped": [block.text for block in layout.wrapped],
                    "rows": layout.wrapped[0].rows,
                    "wrap_px": layout.wrapped[0].wrap_px,
                    "label_id": label_id,
                },
            )

    def _would_not_take_it(self, why: str, label_id: str) -> None:
        """Every way a drawing fails to reach the panel: said once per episode, nothing else stops."""
        self.working = False
        if self._failed.begin():
            log.warning(
                "could not put the label on this device's surface (%s)",
                why,
                extra={"event": "label.failed", "label_id": label_id},
            )


def _lay_out_and_show(surface: LabelSurface, drawing: Drawing) -> Layout:
    """Lay a drawing out and put it on the surface. **Runs on a worker thread.**

    Measuring and drawing are one unit of work because both reach the same text
    stack. Nothing here touches shared state; the caller reads the outcome
    through the task it holds.
    """
    layout = lay_out(_facts(drawing), surface.geometry, surface.measure, surface.type_scale)
    surface.show(layout)
    return layout


def _facts(drawing: Drawing) -> tuple[Candidate, ...]:
    """What a drawing sets: the label's facts, the wall's name as one line, or nothing."""
    if drawing.outcome is Outcome.CAPTION:
        return read_label(drawing.label).candidates()
    if drawing.outcome is Outcome.CARD and drawing.wall_name:
        return (Candidate(runs=(Run(drawing.wall_name),), tier=Tier.MANDATORY),)
    return ()


def _title(drawing: Drawing) -> str | None:
    title = (drawing.label or {}).get("title")
    return title if isinstance(title, str) and title else drawing.work_id


class LabelLink(Protocol):
    """A label's document, as a renderer needs it. `pull.LabelPull` is the real one."""

    async def fetch(self) -> "LabelAnswerLike": ...

    async def close(self) -> None: ...


class LabelAnswerLike(Protocol):
    reachable: bool
    document: LabelDocument | None


class LabelRenderer:
    """Keeps one panel showing what the label rule asks of its wall."""

    def __init__(
        self,
        *,
        assignment: LabelAssignment,
        link: LabelLink,
        panel: LabelPanel,
        now: Callable[[], datetime],
        poll_seconds: float,
    ) -> None:
        self._assignment = assignment
        self._link = link
        self._panel = panel
        self._now = now
        self._poll = poll_seconds
        #: The last document the server sent, kept through every failure.
        self._document: LabelDocument | None = None
        #: When the server last answered at all; the hold runs from here once it
        #: stops answering.
        self._last_answer: datetime | None = None
        #: What the panel was last asked to show. **Recorded on the attempt
        #: rather than the success**, so a refusing panel is not re-asked every
        #: second: it gets its next chance when the drawing next changes.
        self._attempted: Drawing | None = None

    async def run(self, stop: asyncio.Event, retired: asyncio.Event) -> None:
        """Poll and draw until stopped; a retired renderer leaves its panel blank."""
        log.info(
            "label %s on %s captions wall %s",
            self._assignment.label_id,
            self._assignment.output,
            self._assignment.wall_id,
            extra={
                "event": "label.renderer_started",
                "label_id": self._assignment.label_id,
                "output": self._assignment.output,
                "wall_id": self._assignment.wall_id,
            },
        )
        try:
            while not stop.is_set():
                await self.tick()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self._poll)
        finally:
            if retired.is_set():
                # **The mapping went, so the panel captions no wall.** Left as it
                # was, it would go on naming a picture on a wall it no longer
                # belongs to, confidently and for good.
                await self._show(Drawing(Outcome.BLANK, state="unmapped"))
            await self._link.close()

    async def tick(self) -> None:
        """One poll: ask for the document, decide, and draw if the decision changed."""
        answer = await self._link.fetch()
        now = self._now()
        if answer.reachable:
            self._last_answer = now
            if answer.document is not None:
                self._document = answer.document
            reading = self._document
        else:
            reading = offline(self._document, self._last_answer)
        await self._show(drawing_for(reading, now))

    async def _show(self, drawing: Drawing) -> None:
        if drawing == self._attempted:
            return
        self._attempted = drawing
        with work_context(drawing.work_id) if drawing.work_id is not None else nullcontext():
            await self._panel.draw(drawing, label_id=self._assignment.label_id)
