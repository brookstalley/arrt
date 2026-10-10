"""Ask's agent starts and answers a turn without NATS or Postgres.

3tears' agent-tools declares agent-memory (pgvector), agent-audit and a NATS
client as install dependencies, and Arrt accepted that because the tools it uses
reach none of them at runtime (`build-plan-ask-agent.md`, the agent-tools
decision). This holds that claim. A 3tears release that turns the install-time
coupling into a runtime one fails here, by name, rather than as an Ask that
hangs on a connection the server has nowhere to make.

It runs in a fresh interpreter so nothing another test imported or connected
counts, with the usual addresses for both pointed at a port nothing listens on,
and every socket connection the process attempts recorded through an audit
hook. The model is scripted, so an answered turn makes no connection at all.
"""

import json
import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent.parent

TURN = """
import asyncio, json, sys
sys.path.insert(0, sys.argv[1])
attempted = []
sys.addaudithook(lambda event, args: attempted.append(repr(args[1])) if event == "socket.connect" else None)

from scripted_model import ScriptedModel, calls, says
from threetears.agent.tools.builtin.web_search import create_web_search_tool
from arrt.ask.agent import Ask

def dispatch(name, arguments):
    return {"success": True, "works": [{"qid": "Q500985", "title": "The Hunters in the Snow", "held_artwork_ids": []}]}

async def main():
    model = ScriptedModel(replies=[calls(("art_discovery", {"action": "search", "q": "bruegel"})), says("[Q500985]")])
    search = create_web_search_tool({"base_url": "http://127.0.0.1:9"}, "Search the web.")
    ask = Ask(dispatch, model, step_limit=8, local_tools=[search])
    thread = ask.threads.open()
    return [json.loads(line) async for line in ask.reply(thread, "Bruegel")]

events = asyncio.run(main())
print(json.dumps({"types": [event["type"] for event in events], "last": events[-1], "connects": attempted}))
"""

#: The addresses 3tears' NATS client and Postgres-backed packages read, pointed
#: at a port nothing listens on: if one is reached for, it cannot succeed quietly.
UNREACHABLE = {
    "NATS_URL": "nats://127.0.0.1:9",
    "NATS_SERVERS": "nats://127.0.0.1:9",
    "DATABASE_URL": "postgresql://nobody@127.0.0.1:9/none",
    "POSTGRES_DSN": "postgresql://nobody@127.0.0.1:9/none",
    "PGHOST": "127.0.0.1",
    "PGPORT": "9",
}


def test_a_turn_is_answered_with_no_nats_and_no_postgres_and_no_connection_attempted(monkeypatch):
    for name, value in UNREACHABLE.items():
        monkeypatch.setenv(name, value)

    finished = subprocess.run(  # noqa: S603 -- a fixed argv: this interpreter and a script in this file
        [sys.executable, "-c", TURN, str(TESTS)], capture_output=True, text=True, timeout=120, check=False
    )

    assert finished.returncode == 0, finished.stderr
    outcome = json.loads(finished.stdout.strip().splitlines()[-1])
    assert outcome["types"][0] == "stream_start"
    assert outcome["types"][-1] == "stream_end", outcome["last"]
    assert [card["qid"] for card in outcome["last"]["metadata"]["cards"]] == ["Q500985"]
    assert outcome["connects"] == [], f"the turn tried to connect to {outcome['connects']}"
