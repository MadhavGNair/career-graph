"""The narrow interface nodes use to talk to a model, and the live implementation.

Nodes call `structured()` (schema-constrained output) or `tool_step()` (one ReAct step with
tools bound). The same call works with the fake model in demo mode, so node code is identical
in both modes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, cast

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from careergraph.config import Settings
from careergraph.llm.budget import Budget


class LLMOutputError(RuntimeError):
    """The model returned output that does not match the schema."""


class ChatPort(Protocol):
    """What nodes may ask of a model."""

    tier: str
    model: str

    def structured[T: BaseModel](
        self,
        *,
        task: str,
        schema: type[T],
        system: str,
        prompt: str,
        payload: dict[str, Any],
        run_id: str,
    ) -> T:
        """Return output validated against schema."""
        ...

    def tool_step(
        self,
        *,
        task: str,
        system: str,
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool],
        payload: dict[str, Any],
        run_id: str,
    ) -> AIMessage:
        """Return one assistant message, possibly with tool calls."""
        ...


def usage_from_message(msg: BaseMessage) -> tuple[int, int, int, int]:
    """(input, output, cache_read, cache_write) from LangChain usage_metadata (0 if absent)."""
    meta = getattr(msg, "usage_metadata", None) or {}
    details = meta.get("input_token_details") or {}
    return (
        int(meta.get("input_tokens", 0)),
        int(meta.get("output_tokens", 0)),
        int(details.get("cache_read", 0) or 0),
        int(details.get("cache_creation", 0) or 0),
    )


class LiveChat:
    """A real chat model via LangChain `init_chat_model`, with budgets and prompt caching."""

    def __init__(self, tier: str, model: str, effort: str, settings: Settings, budget: Budget):
        self.tier, self.model, self.budget = tier, model, budget
        self.provider = model.split(":", 1)[0]
        kwargs: dict[str, Any] = {
            "max_tokens": settings.max_output_tokens_per_call,
            "timeout": settings.llm_timeout_seconds,
            "max_retries": 2,
        }
        if self.provider == "anthropic":
            if settings.anthropic_api_key is not None:
                kwargs["api_key"] = settings.anthropic_api_key.get_secret_value()
            if effort:
                kwargs["effort"] = effort
        self._chat: Any = init_chat_model(model, **kwargs)

    def _system(self, text: str) -> SystemMessage:
        if self.provider == "anthropic":
            # Static system prompts are marked cacheable. Prompts shorter than the provider's
            # minimum cacheable length are simply not cached (no error).
            block = {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}
            return SystemMessage(content=[block])
        return SystemMessage(content=text)

    def _record(self, msg: BaseMessage, task: str, run_id: str) -> None:
        inp, out, cr, cw = usage_from_message(msg)
        self.budget.record(
            run_id=run_id,
            task=task,
            tier=self.tier,
            model=self.model,
            input_tokens=inp,
            output_tokens=out,
            cache_read=cr,
            cache_write=cw,
        )

    def structured[T: BaseModel](
        self,
        *,
        task: str,
        schema: type[T],
        system: str,
        prompt: str,
        payload: dict[str, Any],
        run_id: str,
    ) -> T:
        """Call the model with provider-native structured output (json_schema on Anthropic)."""
        self.budget.check(run_id)
        method = "json_schema" if self.provider == "anthropic" else "function_calling"
        runnable = self._chat.with_structured_output(schema, method=method, include_raw=True)
        out = runnable.invoke([self._system(system), HumanMessage(content=prompt)])
        raw = out.get("raw")
        if isinstance(raw, BaseMessage):
            self._record(raw, task, run_id)
        parsed = out.get("parsed")
        if out.get("parsing_error") is not None or parsed is None:
            raise LLMOutputError(f"{task}: {out.get('parsing_error') or 'empty output'}")
        if isinstance(parsed, schema):
            return parsed
        return schema.model_validate(parsed)

    def tool_step(
        self,
        *,
        task: str,
        system: str,
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool],
        payload: dict[str, Any],
        run_id: str,
    ) -> AIMessage:
        """One tool-calling turn (tool choice is left to the model: forced choice is not
        supported on every current model)."""
        self.budget.check(run_id)
        msg = self._chat.bind_tools(list(tools)).invoke([self._system(system), *messages])
        self._record(msg, task, run_id)
        return cast(AIMessage, msg)
