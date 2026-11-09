"""A chat model that says what it is told to, in order, streamed as a provider streams.

Ask's agent runs LangChain's real `create_agent` loop against this, so a test
exercises the loop, the tools, the stream and the call limit with no provider.
LangChain's own `GenericFakeChatModel` cannot stand in: streamed, a reply
carrying only tool calls produces no chunks and the loop fails with "No
generations found in stream".

Each reply's content streams word by word; its tool calls arrive on the last
chunk with the reply's cost, where OpenRouter puts usage. `seen` keeps the
messages each call was given, so a test can check what the model was shown.
"""

import json
from collections.abc import Iterator, Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

#: What each scripted reply costs, as OpenRouter reports it.
COST_PER_REPLY = 0.0012

#: The model each reply says answered it, as OpenRouter names it in `model_name`.
ANSWERED_BY = "scripted/answering-model"

#: Each reply's token counts, different from each other so a swap shows.
INPUT_TOKENS_PER_REPLY = 120
OUTPUT_TOKENS_PER_REPLY = 7


def calls(*requests: tuple[str, dict[str, Any]]) -> AIMessage:
    """A reply that calls tools and says nothing, as a model mid-search does."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": f"call-{index}"} for index, (name, args) in enumerate(requests)],
    )


def says(text: str) -> AIMessage:
    """A reply that answers."""
    return AIMessage(content=text)


def unpriced(reply: AIMessage) -> AIMessage:
    """The same reply with no cost on it, as a provider that reports none sends it."""
    return reply.model_copy(update={"additional_kwargs": {**reply.additional_kwargs, "unpriced": True}})


def unreported(reply: AIMessage) -> AIMessage:
    """The same reply with no usage and no model name on it, as a provider that reports neither sends it."""
    return reply.model_copy(update={"additional_kwargs": {**reply.additional_kwargs, "unreported": True}})


def _usage(reply: AIMessage) -> dict[str, int] | None:
    return None if reply.additional_kwargs.get("unreported") else USAGE


def _metadata(reply: AIMessage) -> dict[str, Any]:
    unreported_ = reply.additional_kwargs.get("unreported")
    named = {} if unreported_ else {"model_name": reply.additional_kwargs.get("answered_by", ANSWERED_BY)}
    return named if reply.additional_kwargs.get("unpriced") else {**named, "cost": COST_PER_REPLY}


def answered_by(model: str, reply: AIMessage) -> AIMessage:
    """The same reply, said to come from `model`, as a provider routing between models reports it."""
    return reply.model_copy(update={"additional_kwargs": {**reply.additional_kwargs, "answered_by": model}})


#: Each reply's usage, where OpenRouter's LangChain binding puts it.
USAGE = {
    "input_tokens": INPUT_TOKENS_PER_REPLY,
    "output_tokens": OUTPUT_TOKENS_PER_REPLY,
    "total_tokens": INPUT_TOKENS_PER_REPLY + OUTPUT_TOKENS_PER_REPLY,
}


class ScriptedModel(BaseChatModel):
    replies: list[AIMessage]
    seen: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, _tools: Sequence[Any], **_kwargs: Any) -> ScriptedModel:
        return self

    def _next(self, messages: list[BaseMessage]) -> AIMessage:
        self.seen.append(list(messages))
        if not self.replies:
            raise AssertionError("the model was asked more times than the test scripted")
        return self.replies.pop(0)

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **_: Any) -> ChatResult:
        reply = self._next(messages)
        priced = reply.model_copy(update={"response_metadata": _metadata(reply), "usage_metadata": _usage(reply)})
        return ChatResult(generations=[ChatGeneration(message=priced)])

    def _stream(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **_: Any
    ) -> Iterator[ChatGenerationChunk]:
        reply = self._next(messages)
        words = str(reply.content).split(" ") if reply.content else []
        for index, word in enumerate(words):
            yield ChatGenerationChunk(message=AIMessageChunk(content=word if index == 0 else f" {word}"))
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {"name": call["name"], "args": json.dumps(call["args"]), "id": call["id"], "index": index}
                    for index, call in enumerate(reply.tool_calls)
                ],
                response_metadata=_metadata(reply),
                usage_metadata=_usage(reply),
            )
        )


class HeldModel(ScriptedModel):
    """A model that does not answer until the test sets `release`, so a reply can be caught running.

    Streaming runs on a worker thread, so the wait holds the reply and not the event loop.
    """

    release: Any = None

    def _stream(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> Iterator[ChatGenerationChunk]:
        self.release.wait(timeout=20)
        yield from super()._stream(messages, stop, run_manager, **kwargs)
