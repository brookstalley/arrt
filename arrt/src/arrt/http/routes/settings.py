"""The routes for the server's settings and the standing of unattended spending."""

from fastapi import APIRouter, Request

from arrt.http.models import SetSetting, SettingListOut, SettingOut, UnattendedOut
from arrt.http.routes.common import API_PREFIX, _services
from arrt.library.services.settings import SettingState
from arrt.library.services.unattended import Standing
from arrt.persistence.discovery_records import InitiatedBy

router = APIRouter(prefix=API_PREFIX)


@router.get("/settings")
def list_settings(request: Request) -> SettingListOut:
    """Every household setting, its value and where that came from."""
    return SettingListOut(settings=[_setting(state) for state in _services(request).settings.describe()])


@router.post("/settings/{key}")
def set_setting(request: Request, key: str, body: SetSetting) -> SettingOut:
    """Change one setting. Refused, by name, for an unknown key, a value it cannot take, or one the environment locks."""
    return _setting(_services(request).settings.set(key, body.value, surface=InitiatedBy.WEB_UI))


@router.get("/unattended")
def unattended_standing(request: Request) -> UnattendedOut:
    """Whether unattended work may start now, and what it has spent this UTC month against its allowance."""
    return _unattended(_services(request).unattended.standing())


def _unattended(standing: Standing) -> UnattendedOut:
    return UnattendedOut(
        switched_on=standing.switched_on,
        allowance_usd=f"{standing.allowance_usd:.2f}",
        spent_usd=f"{standing.spent_usd:.2f}",
        remaining_usd=f"{standing.remaining_usd:.2f}",
        may_start=standing.may_start,
        refusal=None if standing.refusal is None else str(standing.refusal),
        sentence=standing.sentence,
        summary=standing.summary,
    )


def _setting(state: SettingState) -> SettingOut:
    setting = state.setting
    return SettingOut(
        key=setting.key,
        label=setting.label,
        value=state.value,
        default=setting.render(setting.default),
        source=str(state.source),
        locked=state.locked,
        environment_variable=setting.environment_variable,
        description=setting.description,
        choices=list(setting.choices),
        kind=str(setting.kind),
        section=setting.section,
        updated_at=None if state.updated_at is None else state.updated_at.isoformat(),
        updated_by=None if state.updated_by is None else str(state.updated_by),
        set_aside_reason=state.set_aside_reason,
    )
