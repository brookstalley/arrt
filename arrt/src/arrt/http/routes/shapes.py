"""The shaping two or more resources share: a work, an artist, a theme, a placement, a fit and an instant.

A shape only one resource uses lives in that resource's module. This one holds the rest, so that
no resource module imports a sibling for a formatter that is not the sibling's."""

from datetime import datetime

from arrt.http.models import ArtistOut, FitOut, ImageOut, ThemeOut, ThemePlacementOut, WallRefOut, WorkOut
from arrt.library.services.quality import Fit
from arrt.library.services.survey import WorkSurvey
from arrt.persistence.records import Artist, IdentitySetBy, Theme
from arrt.programming.display import ThemePlacement


def _work(survey: WorkSurvey) -> WorkOut:
    artwork = survey.detail.artwork
    return WorkOut(
        artwork_id=artwork.id,
        title=artwork.title,
        artist=None if survey.detail.artist is None else _artist(survey.detail.artist),
        date_created=artwork.date_created,
        medium=artwork.medium,
        dimensions=artwork.dimensions,
        description=artwork.description,
        commentary=artwork.commentary,
        rights=artwork.rights,
        status=str(artwork.status),
        wikidata_qid=artwork.wikidata_qid,
        wikidata_qid_set_by=_set_by(artwork.wikidata_qid_set_by),
        fit=None if survey.fit is None else _fit(survey.fit),
        fit_note=survey.fit_note,
        image=ImageOut(
            available=survey.image.available,
            note=survey.image.note,
        ),
    )


def _artist(artist: Artist) -> ArtistOut:
    return ArtistOut(
        artist_id=artist.id,
        name=artist.name,
        nationality=artist.nationality,
        born=artist.born,
        died=artist.died,
        lifespan_text=artist.lifespan_text,
        biography=artist.biography,
        family_name=artist.family_name,
        given_name=artist.given_name,
        display_nationality=artist.display_nationality,
        wikidata_qid=artist.wikidata_qid,
        wikidata_qid_set_by=_set_by(artist.wikidata_qid_set_by),
    )


def _set_by(value: IdentitySetBy | None) -> str | None:
    return None if value is None else str(value)


def _theme(theme: Theme) -> ThemeOut:
    return ThemeOut(
        theme_id=theme.id,
        name=theme.name,
        description=theme.description,
        created_at=theme.created_at.isoformat(),
        is_default=theme.is_default,
        hidden=theme.hidden,
    )


def _instant(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat()


def _placement(placement: ThemePlacement) -> ThemePlacementOut:
    return ThemePlacementOut(
        theme=_theme(placement.theme),
        hanging_on=[WallRefOut(wall_id=wall.id, name=wall.name) for wall in placement.walls],
    )


def _fit(fit: Fit) -> FitOut:
    """A quality verdict as every surface that shows one carries it: the work, a scan, a registry picture."""
    return FitOut(verdict=str(fit))
