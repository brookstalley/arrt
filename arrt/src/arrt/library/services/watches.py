"""A household's Watches: standing requests in words, which Arrt re-runs with nobody watching.

A Watch is the *arr apps' monitored list (Radarr's Lists), and the product's first
unattended agent work (`agents-and-memory.md` ruling 5). This module is the record
and its rules. The scheduler that runs a Watch is `scheduler.py`, and each run is
an ordinary discovery run, so it spends, dedups and is reviewed as an Ask is.

**One policy: what a Watch finds goes to To review.** Auto-accept is not offered
(the owner, 2026-11-09; `security-model.md` § The unattended trigger fired), so
there is no field for it, and nothing here writes a verdict.

**A Watch's cap is a share of the unattended allowance**, as the allowance is a
share of the month's budget. A cap above the allowance is refused when written,
and one the allowance has since fallen below reads as the allowance
(`effective_cap`), the same fail-closed rule the allowance follows under a lowered
budget. Neither replaces the provider's key limit, which is what stops the bill.

**Every write names its surface** (`created_by`, `updated_by`, and the log line),
because an agent on MCP can write a Watch, and a surprise in the month's spend has
to be traceable to whoever made it.
"""

import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final

from arrt.library.services.settings import (
    UNATTENDED_ALLOWANCE,
    UNATTENDED_CADENCE,
    Cadence,
    SettingRefused,
    SettingsService,
    dollars,
)
from arrt.persistence.discovery import DiscoveryStore
from arrt.persistence.discovery_records import InitiatedBy, Watch
from arrt.services.errors import ServiceError
from arrt.services.fields import require_member, require_text
from arrt.services.store import store_write

log = logging.getLogger(__name__)

#: The longest a Watch's words may be. An Ask's request is a sentence or two; a
#: bound keeps a pasted page from becoming a standing prompt resent every pass.
MAX_INTENT_CHARS: Final[int] = 1000


class WatchService:
    """Reads and writes the household's Watches."""

    def __init__(
        self,
        store: DiscoveryStore,
        settings: SettingsService,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._settings = settings
        self._now = now

    # -- reads ----------------------------------------------------------------

    def list(self) -> Sequence[Watch]:
        """Every Watch, in the order the household wrote them."""
        return self._store.list_watches()

    def get(self, watch_id: str) -> Watch:
        found = self._store.get_watch(watch_id)
        if found is None:
            raise ServiceError(f"No Watch with id {watch_id!r}.")
        return found

    def cadence_of(self, watch: Watch) -> Cadence:
        """How often this Watch runs: its own cadence, or the household's default for unattended work."""
        if watch.cadence is None:
            return self._settings.value(UNATTENDED_CADENCE)
        return Cadence(watch.cadence)

    def effective_cap(self, watch: Watch) -> Decimal:
        """What this Watch may spend this month: its cap, never more than the allowance, or the allowance."""
        allowance = self._settings.value(UNATTENDED_ALLOWANCE)
        if watch.monthly_cap_usd is None:
            return allowance
        return min(watch.monthly_cap_usd, allowance)

    # -- writes ---------------------------------------------------------------

    def create(
        self,
        *,
        intent_text: str,
        surface: InitiatedBy,
        cadence: str = "",
        monthly_cap_usd: str = "",
        enabled: bool = True,
    ) -> Watch:
        """Write a new Watch. An empty cadence follows the household's default; an empty cap leaves only the allowance."""
        by = require_member(surface, enum=InitiatedBy, field="surface")
        now = self._now()
        watch = Watch(
            id=str(uuid.uuid4()),
            intent_text=_intent(intent_text),
            enabled=bool(enabled),
            created_at=now,
            created_by=by,
            updated_at=now,
            updated_by=by,
            cadence=_cadence(cadence),
            monthly_cap_usd=self._cap(monthly_cap_usd),
        )
        store_write(self._store.add_watch, watch)
        log.info(
            "watch %s written by %s",
            watch.id,
            by,
            extra={"event": "watch.created", "watch_id": watch.id, "surface": str(by), "enabled": watch.enabled},
        )
        return watch

    def update(
        self,
        watch_id: str,
        *,
        surface: InitiatedBy,
        intent_text: str | None = None,
        cadence: str | None = None,
        monthly_cap_usd: str | None = None,
        enabled: bool | None = None,
    ) -> Watch:
        """Change what is given and leave the rest. An empty cadence or cap clears it, as on `create`."""
        by = require_member(surface, enum=InitiatedBy, field="surface")
        before = self.get(watch_id)
        after = replace(
            before,
            intent_text=before.intent_text if intent_text is None else _intent(intent_text),
            cadence=before.cadence if cadence is None else _cadence(cadence),
            monthly_cap_usd=before.monthly_cap_usd if monthly_cap_usd is None else self._cap(monthly_cap_usd),
            enabled=before.enabled if enabled is None else bool(enabled),
            updated_at=self._now(),
            updated_by=by,
        )
        store_write(self._store.update_watch, after)
        changed = sorted(
            name
            for name in ("intent_text", "cadence", "monthly_cap_usd", "enabled")
            if getattr(before, name) != getattr(after, name)
        )
        log.info(
            "watch %s changed (%s) by %s",
            watch_id,
            ", ".join(changed) or "nothing",
            by,
            extra={"event": "watch.updated", "watch_id": watch_id, "surface": str(by), "changed": changed},
        )
        return after

    def delete(self, watch_id: str, *, surface: InitiatedBy) -> Watch:
        """Remove a Watch and return what was removed. Its runs and their finds stay."""
        by = require_member(surface, enum=InitiatedBy, field="surface")
        going = self.get(watch_id)
        store_write(self._store.delete_watch, watch_id)
        log.info(
            "watch %s deleted by %s",
            watch_id,
            by,
            extra={"event": "watch.deleted", "watch_id": watch_id, "surface": str(by)},
        )
        return going

    def _cap(self, raw: str) -> Decimal | None:
        if not raw.strip():
            return None
        try:
            cap = dollars(raw)
        except SettingRefused as exc:
            raise ServiceError(f"A Watch's monthly cap {exc}") from exc
        allowance = self._settings.value(UNATTENDED_ALLOWANCE)
        if cap > allowance:
            raise ServiceError(
                f"A Watch's monthly cap is a share of the unattended allowance, ${allowance:.2f}, and cannot be more "
                f"than it; got ${cap:.2f}. Raise the allowance in Settings › General first, or leave the cap empty."
            )
        return cap


def _intent(raw: str) -> str:
    text = require_text(raw, field="intent_text")
    if len(text) > MAX_INTENT_CHARS:
        raise ServiceError(f"A Watch's words are at most {MAX_INTENT_CHARS} characters, got {len(text)}.")
    return text


def _cadence(raw: str) -> str | None:
    text = raw.strip().lower()
    if not text:
        return None
    try:
        return str(Cadence(text))
    except ValueError as exc:
        allowed = ", ".join(str(member) for member in Cadence)
        raise ServiceError(f"A Watch's cadence is one of {allowed}, or empty for the household's default; got {raw!r}.") from exc
