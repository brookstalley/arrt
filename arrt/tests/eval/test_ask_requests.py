"""Whether a cheap model answers what a curator types into Ask, with Ask's tools.

The measurement `build-plan-ask-agent.md` Chunk 02 owes before Chunk 03 builds
on it: each request in `ask.py`, against the real surface, with the real
registry (Wikidata, asked live) and, when `SEARXNG_URL` is set, web search
through 3tears beside it. Deselected by default for the reasons the surface
evaluation next door gives, and because it spends: `-m llm_eval -n0`.

**It records more than it asserts.** Set `ART_EVAL_RECORD` to a file and each run
appends its steps, cost, invalid calls and grounding there, which is what the
artifact's numbers are built from; the assertion is only whether this run did
what its request asked. `ART_EVAL_MODEL` picks the model.
"""

import os

import pytest

pytest.importorskip(
    "threetears.models",
    reason="the model-driven evaluation needs the eval group — run `uv sync --group eval`",
)

from ask import ASK_BUDGET, ASK_SCOPE, ASK_SYSTEM, REQUESTS, passed, record, score
from driver import drive

from arrt.library.registry.wikidata import WikidataRegistry

pytestmark = pytest.mark.llm_eval

#: The model `ask-agent-findings.md` chose for Ask, so a plain run measures what ships.
MODEL_ID = os.environ.get("ART_EVAL_MODEL", "anthropic/claude-haiku-5.5")

#: Who Wikidata is told is asking, as the live suites tell it.
USER_AGENT = "arrt test suite (+https://github.com/brookstalley/arrt) bot"


@pytest.fixture
def registry():
    """Wikidata itself: the agent's answers are only as real as the registry it reads."""
    client = WikidataRegistry(user_agent=USER_AGENT)
    yield client
    client.close()


@pytest.fixture
def model():
    from threetears.models import create_chat_model

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY is unset, so no model can be reached")
    return create_chat_model(MODEL_ID, api_key=api_key, provider="openrouter")


@pytest.fixture
def web_search():
    """3tears' web search over SearXNG, or none when no instance is configured."""
    base_url = os.environ.get("SEARXNG_URL")
    if not base_url:
        return []
    from threetears.agent.tools.builtin.web_search import create_web_search_tool

    return [create_web_search_tool({"base_url": base_url}, "Search the web. Returns titles, addresses and snippets.")]


@pytest.mark.parametrize("request_", REQUESTS, ids=[request.id for request in REQUESTS])
async def test_a_model_answers_an_ask(server_url, seeded_titles, model, web_search, request_):
    outcome = await drive(
        server_url,
        model,
        goal=request_.goal,
        budget=ASK_BUDGET,
        system=ASK_SYSTEM,
        scope=ASK_SCOPE,
        local_tools=web_search,
    )
    found = score(outcome)
    failure = request_.check(found) if outcome.answered else "no answer"
    record(MODEL_ID, request_, found, searched=bool(web_search), failure=failure)

    assert not outcome.provider_failed, f"the provider failed the run. {outcome}"
    assert outcome.answered, f"the model never answered. {outcome}"
    assert not found.invented, f"the answer named items no tool returned: {sorted(found.invented)}. {outcome}"
    assert failure is None, f"{failure}. {outcome}"
    assert passed(found, failure)  # the record and the test must not disagree
