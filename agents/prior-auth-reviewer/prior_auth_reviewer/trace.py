"""Records each case run as a trace in the agent-evaluator format, so real runs can be graded."""
import json
from typing import Any

from prior_auth_reviewer.context import mask


def deidentify(x: Any) -> Any:
    """Mask identifiers in every string of a trace value (member ids, birth dates, clinician names)."""
    if isinstance(x, str):
        return mask(x)[0]
    if isinstance(x, dict):
        return {k: deidentify(v) for k, v in x.items()}
    if isinstance(x, list):
        return [deidentify(v) for v in x]
    return x


class Recorder:
    def __init__(self, run_id: str, task_id: str, agent_version: str):
        self.run_id, self.task_id, self.agent_version = run_id, task_id, agent_version
        self.steps: list[dict] = []

    def _id(self) -> str:
        return f"s{len(self.steps) + 1}"

    def tool(self, tool: str, args: dict, result: Any = None, error: str | None = None, thought: str = "") -> str:
        sid = self._id()
        self.steps.append({"id": sid, "kind": "tool_call", "thought": thought, "tool": tool, "args": deidentify(args),
                           "result": deidentify(result), "error": error})
        return sid

    def message(self, content: str, thought: str = "") -> str:
        sid = self._id()
        self.steps.append({"id": sid, "kind": "message", "thought": thought, "content": deidentify(content)})
        return sid

    def to_dict(self) -> dict:
        return {"trace_id": self.task_id, "run_id": self.run_id, "task_id": self.task_id,
                "agent_version": self.agent_version, "steps": self.steps}

    def dumps(self) -> str:
        return json.dumps(self.to_dict(), indent=1, default=str) + "\n"
