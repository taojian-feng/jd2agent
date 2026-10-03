"""MCP client for the health plan systems: bounded retries with backoff, typed failures, every attempt traced."""
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable

from prior_auth_reviewer.trace import Recorder

RETRYABLE = ("TimeoutError", "HTTP 503", "timed out")


class ToolFailed(Exception):
    def __init__(self, tool: str, error: str, attempts: int):
        self.tool, self.error, self.attempts = tool, error, attempts
        super().__init__(f"{tool} failed after {attempts} attempt(s): {error}")


@asynccontextmanager
async def connect(server):
    """In-process MCP session to a server (SDK 2.x Client, or the 1.x memory transport)."""
    try:
        from mcp import Client  # 2.x
        async with Client(server) as c:
            yield c
    except ImportError:
        from mcp.shared.memory import create_connected_server_and_client_session
        async with create_connected_server_and_client_session(server._mcp_server) as c:
            yield c


def _parse(result) -> tuple[Any, str | None]:
    is_error = bool(getattr(result, "is_error", getattr(result, "isError", False)))
    text = "".join(getattr(c, "text", "") for c in (result.content or []))
    if is_error:
        return None, text.replace("Error executing tool ", "").strip() or "unknown error"
    sc = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if sc is not None:
        return (sc["result"] if set(sc) == {"result"} else sc), None
    try:
        return json.loads(text), None
    except ValueError:
        return text, None


class SystemsClient:
    def __init__(self, session, recorder: Recorder, retries: int = 2, backoff: tuple[float, ...] = (0.5, 1.0),
                 sleep: Callable[[float], Awaitable] = asyncio.sleep):
        self.session, self.rec, self.retries, self.backoff, self.sleep = session, recorder, retries, backoff, sleep

    async def call(self, tool: str, args: dict, thought: str,
                   redact: Callable[[Any], Any] | None = None) -> Any:
        """Call a system tool. Retryable errors (timeouts, 503) are retried with backoff; others fail at once.
        redact: applied to the result before it is written to the trace (the caller still gets the full result)."""
        error, prev = "", ""
        for attempt in range(self.retries + 1):
            result, error = _parse(await self.session.call_tool(tool, args))
            self.rec.tool(tool, args, redact(result) if (redact and result is not None) else result, error,
                          thought if attempt == 0 else f"Retry {attempt} after: {prev}")
            if error is None:
                return result
            prev = error
            if not any(m in error for m in RETRYABLE) or attempt == self.retries:
                break
            await self.sleep(self.backoff[min(attempt, len(self.backoff) - 1)])
        raise ToolFailed(tool, error, attempt + 1)
