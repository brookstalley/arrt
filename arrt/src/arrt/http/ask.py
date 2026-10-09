"""Ask's routes: open a thread, read it back, and send it words.

Internal to the browser client and unversioned. A reply streams as
`application/x-ndjson`, one 3tears stream event per line (`arrt/ask/agent.py`).
A refusal made before the stream opens is an ordinary JSON error with a status;
once the stream opens, it closes with exactly one terminal event.
"""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from arrt.ask.agent import Ask, Thread

router = APIRouter(prefix="/api/ask")

NDJSON = "application/x-ndjson"


class Said(BaseModel):
    #: At least one character that is not white space: blank words would be an
    #: empty message the model is paid to answer.
    words: str = Field(min_length=1, max_length=4000, pattern=r"\S")


def _ask(request: Request) -> Ask:
    return request.app.state.ask


def _refused(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


def _thread_out(ask: Ask, thread: Thread) -> dict[str, Any]:
    return {
        "thread_id": thread.id,
        "available": ask.available,
        "replying": thread.replying,
        "turns": [{"asked": turn.asked, "events": turn.events} for turn in thread.turns],
    }


@router.get("")
def ask_status(request: Request) -> dict[str, bool]:
    """Whether Ask can answer here: false on a server with no key. Read by the page before any thread is open."""
    return {"available": _ask(request).available}


@router.post("/threads", status_code=201)
def open_thread(request: Request) -> dict[str, Any]:
    """A new, empty thread. Spends nothing: no model is asked until words are sent."""
    ask = _ask(request)
    return _thread_out(ask, ask.threads.open())


@router.get("/threads/{thread_id}", response_model=None)
def read_thread(request: Request, thread_id: str) -> dict[str, Any] | JSONResponse:
    """A thread's turns, each with the events its reply sent, so a returning page repaints through one renderer."""
    ask = _ask(request)
    thread = ask.threads.get(thread_id)
    if thread is None:
        return _refused(404, "That thread has gone; threads are forgotten when the server restarts.")
    return _thread_out(ask, thread)


@router.post("/threads/{thread_id}/replies", responses={200: {"content": {NDJSON: {}}}}, response_model=None)
async def reply(request: Request, thread_id: str, said: Said) -> StreamingResponse | JSONResponse:
    """Send the curator's words; the reply streams back as it is written.

    Spends without asking (the owner, 2026-10-08), and says what it cost when it ends.
    """
    ask = _ask(request)
    thread = ask.threads.get(thread_id)
    if thread is None:
        return _refused(404, "That thread has gone; threads are forgotten when the server restarts.")
    if not ask.available:
        return _refused(503, "Ask needs OPENROUTER_API_KEY to answer; nothing was spent.")
    if thread.replying:
        return _refused(409, "Ask is still answering the last thing you said.")
    return StreamingResponse(ask.reply(thread, said.words.strip()), media_type=NDJSON)
