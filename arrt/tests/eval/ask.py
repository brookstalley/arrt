"""Ask-shaped requests, the agent's scope, and how a run is scored.

`build-plan-ask-agent.md` Chunk 02 measures whether the cheap models Arrt runs
use the product's tools well enough to answer a curator in words: the requests
below, offered the tools Ask's agent will be offered, with web search beside
them when a SearXNG instance is configured. The prompt and the scope are
the server's own (`arrt.ask.prompt`), so what is measured is what ships.

Scoring reads the transcript and the answer, never the model's account of
itself: an item the answer names counts as grounded only if a tool returned it.
"""

import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from driver import LOCAL, Outcome

from arrt.ask.cards import items_in
from arrt.ask.prompt import ASK_SCOPE, ASK_SYSTEM

__all__ = ["ASK_SCOPE", "ASK_SYSTEM"]

#: Tool calls a run may make before it is stopped. Generous on purpose: this
#: chunk measures how many a request takes, and Chunk 03's limit is set from it.
ASK_BUDGET = 24

_QID = re.compile(r"\bQ[1-9][0-9]*\b")


@dataclass(frozen=True)
class Request:
    """One thing a curator might type into Ask, and what a good answer has in it."""

    id: str
    goal: str
    #: Given the run's score, whether the answer did what the request asked,
    #: with the reason when it did not.
    check: Callable[[Score], str | None]


@dataclass
class Score:
    """What a run did, read off its transcript and answer."""

    outcome: Outcome
    #: Every item the answer names by QID.
    named: set[str]
    #: Of those, the ones some tool result contained.
    grounded: set[str]
    #: Works (a QID beside a title) the tools returned, and their makers' names.
    works: Mapping[str, str]
    #: Works the library holds, by QID, as the tools marked them.
    held: set[str]
    #: People (a QID beside a name and no title) the tools returned, by name.
    people: Mapping[str, str]

    @property
    def invented(self) -> set[str]:
        return self.named - self.grounded

    @property
    def works_offered(self) -> set[str]:
        return self.named & set(self.works)

    @property
    def gettable(self) -> set[str]:
        return self.works_offered - self.held

    @property
    def refused(self) -> int:
        return sum(1 for call in self.outcome.transcript.calls if "not available here" in str(call.payload.get("error")))

    @property
    def invalid(self) -> int:
        return len(self.outcome.transcript.failures)

    @property
    def registry_unavailable(self) -> int:
        """Calls Wikidata could not answer: the registry's failure, kept apart from the model's."""
        return sum(1 for call in self.outcome.transcript.calls if call.payload.get("state") == "unavailable")


def score(outcome: Outcome) -> Score:
    named = set(_QID.findall(outcome.answer))
    seen: set[str] = set()
    works: dict[str, str] = {}
    held: set[str] = set()
    people: dict[str, str] = {}
    for call in outcome.transcript.calls:
        seen.update(_QID.findall(json.dumps(call.payload, default=str)))
        if call.action == LOCAL:
            continue
        # Read as Ask's cards read it, so a work here is a work a curator is shown.
        for qid, item in items_in(call.payload).items():
            if item.kind == "work":
                works.setdefault(qid, item.detail)
                if item.held:
                    held.add(qid)
            elif item.kind == "artist":
                people.setdefault(qid, item.label)
    return Score(outcome=outcome, named=named, grounded=named & seen, works=works, held=held, people=people)


def _at_least_three_gettable(found: Score) -> str | None:
    return None if len(found.gettable) >= 3 else f"offered {len(found.gettable)} gettable works, wanted 3"


def _more_and_no_haring(found: Score) -> str | None:
    """At least three grounded works or artists, and nothing of Haring's.

    "Help me find more" is answered as well by artists as by works, so this
    counts both. It read "three gettable works" until the first measurement,
    where the best answers named a dozen grounded artists and failed it.
    **Naming is not offering, and this cannot tell them apart**: an answer that
    lists Haring's items as the ones it left out fails it, and a reader passes it.
    """
    if len(found.grounded) < 3:
        return f"offered {len(found.grounded)} grounded works or artists, wanted 3"
    haring = sorted(
        qid
        for qid in found.named
        if "haring" in found.works.get(qid, "").lower() or "haring" in found.people.get(qid, "").lower()
    )
    return f"named Haring or his works {haring}" if haring else None


def _names_the_held_work(found: Score) -> str | None:
    answer = found.outcome.answer.lower()
    if "persistence of memory" not in answer:
        return "did not name The Persistence of Memory, which the library holds"
    return None


#: At least the four the plan names. The library the eval server holds is
#: `seeded_service`'s: Dalí's *The Persistence of Memory* among three works.
REQUESTS: tuple[Request, ...] = (
    Request("early_dali", "Show me Salvador Dalí's early work.", _at_least_three_gettable),
    Request("taste_exclusions", "I like Dalí and Warhol but not Haring. Help me find more.", _more_and_no_haring),
    Request("calm_bedroom", "Something calm for a bedroom.", _at_least_three_gettable),
    Request("held_dali", "What do I already have by Dalí, and what else of his should I look at?", _names_the_held_work),
)


def passed(found: Score, failure: str | None) -> bool:
    """The test's own verdict, every assertion of it: a record that disagreed with the test would be a second scorer."""
    outcome = found.outcome
    return failure is None and outcome.answered and not outcome.provider_failed and not found.invented


def record(model_id: str, request: Request, found: Score, *, searched: bool, failure: str | None) -> None:
    """Append one run to `ART_EVAL_RECORD`, a JSON line each, when it is set; the artifact is built from these."""
    target = os.environ.get("ART_EVAL_RECORD")
    if not target:
        return
    outcome = found.outcome
    line = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": model_id,
        "request": request.id,
        "web_search": searched,
        "passed": passed(found, failure),
        "failure": failure,
        "answered": outcome.answered,
        "provider_failed": outcome.provider_failed,
        "stopped_on_budget": outcome.stopped_on_budget,
        "steps": outcome.steps,
        "calls": len(outcome.transcript.calls),
        "invalid_calls": found.invalid,
        "refused_calls": found.refused,
        "registry_unavailable": found.registry_unavailable,
        "cost_usd": round(outcome.cost_usd, 6),
        "uncosted_replies": outcome.uncosted,
        "named": len(found.named),
        "invented": sorted(found.invented),
        "works_offered": len(found.works_offered),
        "gettable": len(found.gettable),
        "route": outcome.transcript.steps,
        "answer": outcome.answer,
    }
    with Path(target).open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(line, ensure_ascii=False) + "\n")
