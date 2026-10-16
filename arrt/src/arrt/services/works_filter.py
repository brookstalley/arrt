"""Which works an Artworks filter selects, composed across the seam, and what each option would count.

**Neither plane reaches the other; this composes them.** The Library answers
what its own narrowings select (`matching_ids`) and each work's size band
(`fit_bands`). Programming answers a theme's members, which works a wall plays
now (`work_ids_on_walls`) and when each work was last shown
(`last_shown_by_work`), all as opaque ids. Here they meet as sets, and the
Library is handed the result as `within`, the restriction it already lists
theme slices by (`architecture.md` seam rule 1). Both surfaces call this, so
`GET /api/works` and `art_catalogue(action='list')` cannot come to select
different works for one filter (`architecture.md` § Direction: operation logic
lives in the service layer).

Four restrictions on top of the Library's own: the theme, the fit bands, *Not on
any wall* and *Last shown*. Each is counted with its own selection dropped and
the others kept, as a facet is (`CatalogueService._facet_groups`), so an option
offered as enabled cannot lead to an empty grid.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

from arrt.library.services.survey import FIT_BANDS
from arrt.services.errors import ServiceError

if TYPE_CHECKING:
    from arrt.services.container import Services

#: *Last shown*'s options, in the rail's order, with how far back each looks.
#: `never` looks back forever. A curator's "month" is thirty days, not calendar
#: arithmetic, and each period counts the never-shown works too: a work never
#: shown has not been shown in the last month either (the owner, 2026-10-15).
SHOWN_PERIODS: Final[Mapping[str, timedelta | None]] = {
    "never": None,
    "month": timedelta(days=30),
    "quarter": timedelta(days=90),
    "year": timedelta(days=365),
}


@dataclass(frozen=True, slots=True)
class FilterOption:
    """One option a filter control offers, counted as a facet value is."""

    value: str
    count: int
    selected: bool
    disabled: bool


def _option(value: str, count: int, *, selected: bool) -> FilterOption:
    return FilterOption(value=value, count=count, selected=selected, disabled=count == 0 and not selected)


def _meet(*restrictions: frozenset[str] | None) -> frozenset[str] | None:
    """The works every restriction allows; None when none restricts anything."""
    present = [restriction for restriction in restrictions if restriction is not None]
    if not present:
        return None
    return frozenset.intersection(*present)


@dataclass(frozen=True)
class Narrowing:
    """Which works a filter selects, with what each of the four restrictions would count."""

    base: frozenset[str]
    theme: frozenset[str] | None
    fit: frozenset[str] | None
    wall: frozenset[str] | None
    shown: frozenset[str] | None
    bands: Mapping[str, str]
    on_walls: frozenset[str]
    last_shown: Mapping[str, datetime]
    now: datetime
    chosen_bands: frozenset[str]
    not_on_wall: bool
    chosen_period: str | None

    def _restrictions(self, but: str | None = None) -> list[frozenset[str] | None]:
        named = (("theme", self.theme), ("fit", self.fit), ("wall", self.wall), ("shown", self.shown))
        return [restriction for name, restriction in named if name != but]

    def within(self) -> frozenset[str] | None:
        """The restriction the Library lists within: every one in force."""
        return _meet(*self._restrictions())

    def among(self, *, but: str) -> frozenset[str]:
        """What every narrowing but `but` selects: the set `but`'s options are counted over."""
        return _meet(self.base, *self._restrictions(but)) or frozenset()

    def fit_options(self) -> list[FilterOption]:
        counts = Counter(self.bands[work_id] for work_id in self.among(but="fit") if work_id in self.bands)
        return [_option(band, counts[band], selected=band in self.chosen_bands) for band in FIT_BANDS]

    def off_wall_option(self) -> FilterOption:
        return _option("not_on_wall", len(self.among(but="wall") - self.on_walls), selected=self.not_on_wall)

    def shown_options(self) -> list[FilterOption]:
        among = self.among(but="shown")
        return [
            _option(period, len(among - shown_since(self.last_shown, self.now, period)), selected=period == self.chosen_period)
            for period in SHOWN_PERIODS
        ]


def shown_since(last_shown: Mapping[str, datetime], now: datetime, period: str) -> frozenset[str]:
    """The works shown within `period` of `now`: for `never`, every work ever shown."""
    back = SHOWN_PERIODS[period]
    if back is None:
        return frozenset(last_shown)
    cutoff = now - back
    return frozenset(work_id for work_id, at in last_shown.items() if at >= cutoff)


def narrowing(
    services: Services,
    *,
    status: str | None,
    q: str | None,
    facets: Mapping[str, Sequence[str]],
    artist_id: str | None,
    theme: str | None,
    fit: Sequence[str],
    not_on_wall: bool,
    shown: str | None,
) -> Narrowing:
    """Compose the Library's narrowings with the theme, the fit bands, *Not on any wall* and *Last shown*."""
    unknown = [band for band in fit if band not in FIT_BANDS]
    if unknown:
        raise ServiceError(f"fit must be one of {', '.join(FIT_BANDS)}; got {', '.join(repr(band) for band in unknown)}.")
    if shown is not None and shown not in SHOWN_PERIODS:
        raise ServiceError(f"shown must be one of {', '.join(SHOWN_PERIODS)}; got {shown!r}.")
    base = services.catalogue.matching_ids(status=status, q=q, facets=facets, artist_id=artist_id)
    chosen_bands = frozenset(fit)
    bands = services.survey.fit_bands(base)
    on_walls = services.display.work_ids_on_walls()
    last_shown = services.display.last_shown_by_work()
    now = datetime.now(UTC)
    return Narrowing(
        base=base,
        # An unknown theme is refused here, by name, as the listing always has.
        theme=None if theme is None else frozenset(services.display.theme_work_ids(theme)),
        fit=None if not chosen_bands else frozenset(work_id for work_id, band in bands.items() if band in chosen_bands),
        wall=None if not not_on_wall else base - on_walls,
        shown=None if shown is None else base - shown_since(last_shown, now, shown),
        bands=bands,
        on_walls=on_walls,
        last_shown=last_shown,
        now=now,
        chosen_bands=chosen_bands,
        not_on_wall=not_on_wall,
        chosen_period=shown,
    )
