"""Provider-agnostic structured LLM calls, plus validate-and-retry.

Configure the model with one env var (LangChain init_chat_model syntax). Examples only;
use your provider's current model ID:
    AI_ARCHITECT_MODEL=anthropic:claude-sonnet-5-5
    AI_ARCHITECT_MODEL=bedrock_converse:<inference profile id>
    AI_ARCHITECT_MODEL=azure_openai:<deployment>        (+ AZURE_OPENAI_* env vars)
    AI_ARCHITECT_MODEL=google_vertexai:<model>

Optional overrides:
    AI_ARCHITECT_TEMPERATURE           unset = provider default (some newer models reject other values)
    AI_ARCHITECT_MAX_TOKENS            default 16000, so long outputs (component designs) are not cut off
    AI_ARCHITECT_STRUCTURED_METHOD     json_schema | function_calling | json_mode
                                       default: json_schema for anthropic, LangChain's default otherwise
"""
import json
import os
from typing import Callable, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    def structured(self, schema: type[T], system: str, user: str) -> T: ...


class LangChainLLM:
    def __init__(self, model: str):
        from langchain.chat_models import init_chat_model  # imported lazily: optional dependency
        kwargs: dict = {"max_tokens": int(os.environ.get("AI_ARCHITECT_MAX_TOKENS", "16000"))}
        temperature = os.environ.get("AI_ARCHITECT_TEMPERATURE")
        if temperature:
            kwargs["temperature"] = float(temperature)
        self._model = init_chat_model(model, **kwargs)
        provider = model.split(":", 1)[0] if ":" in model else ""
        # Newer Claude models don't support structured output via forced tool calls; use native JSON schema.
        self._method = os.environ.get("AI_ARCHITECT_STRUCTURED_METHOD") or (
            "json_schema" if provider == "anthropic" else None)

    def structured(self, schema: type[T], system: str, user: str) -> T:
        kw = {"method": self._method} if self._method else {}
        runnable = self._model.with_structured_output(schema, **kw)
        return runnable.invoke([("system", system), ("human", user)])


class FakeLLM:
    """Test double: returns queued responses per schema name, and records every prompt."""

    def __init__(self, responses: dict[str, list[dict]]):
        self.responses = {k: list(v) for k, v in responses.items()}
        self.calls: list[tuple[str, str, str]] = []

    def structured(self, schema: type[T], system: str, user: str) -> T:
        self.calls.append((schema.__name__, system, user))
        queue = self.responses.get(schema.__name__)
        if not queue:
            raise AssertionError(f"FakeLLM has no response queued for {schema.__name__}")
        return schema.model_validate(queue.pop(0) if len(queue) > 1 else queue[0])


_default: LLM | None = None


def get_llm() -> LLM:
    global _default
    if _default is None:
        model = os.environ.get("AI_ARCHITECT_MODEL")
        if not model:
            raise RuntimeError("Set AI_ARCHITECT_MODEL (e.g. bedrock_converse:<model-id>) to use LLM-backed tools")
        _default = LangChainLLM(model)
    return _default


def set_llm(llm: LLM | None) -> None:
    """Override the model (tests, demos)."""
    global _default
    _default = llm


class ValidationFailed(Exception):
    def __init__(self, tool: str, problems: list[str], output: BaseModel | None):
        self.problems, self.output = problems, output
        super().__init__(f"{tool}: output failed validation after retry: {problems}")


def call_validated(llm: LLM, schema: type[T], system: str, user: str,
                   validator: Callable[[T], list[str]], tool: str, retries: int = 1, strict: bool = True) -> T:
    """Call the model, run the deterministic validator, and retry with the problems listed.
    strict=True: raise ValidationFailed if it still fails (unverified output never leaves the tool).
    strict=False: return the last output; used where a downstream gate (traceability) catches and
    reports the gaps instead of failing the whole run."""
    prompt = user
    out, problems = None, []
    for attempt in range(retries + 1):
        try:
            out = llm.structured(schema, system, prompt)
        except Exception as e:  # malformed or truncated output: retry with the parser error
            if attempt == retries:
                raise ValidationFailed(tool, [f"unparseable output: {str(e)[:500]}"], None) from e
            prompt = (f"{user}\n\nYour previous answer could not be parsed: {str(e)[:800]}\n"
                      "Return complete, valid output for the schema. Be more concise if it was cut off.")
            continue
        problems = validator(out)
        if not problems:
            return out
        prompt = (f"{user}\n\nYour previous answer failed these checks. Fix every one:\n"
                  + "\n".join(f"- {p}" for p in problems)
                  + f"\n\nPrevious answer:\n{json.dumps(out.model_dump(), indent=1)[:6000]}")
    if strict or out is None:
        raise ValidationFailed(tool, problems, out)
    return out
