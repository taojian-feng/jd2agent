"""Typed inputs and outputs for every tool. LLM-facing schemas are flat and all-required (provider limits)."""
from typing import Any, Literal

from pydantic import BaseModel, Field


# ------------------------------------------------------------------ traces
class Step(BaseModel):
    id: str
    kind: Literal["tool_call", "message"] = "tool_call"
    thought: str = ""
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    error: str | None = None
    content: str | None = None


class Trajectory(BaseModel):
    trace_id: str
    run_id: str
    task_id: str
    agent_version: str = ""
    steps: list[Step]

    def step_ids(self) -> set[str]:
        return {s.id for s in self.steps}


# ------------------------------------------------------------------ code check
class Symptom(BaseModel):
    label: str
    step_ids: list[str] = Field(description="Steps that show it; empty when the problem is a missing step")
    detail: str


class SuccessCheck(BaseModel):
    trace_id: str
    task_id: str
    passed: bool
    expected_outcome: str
    outcome: str | None = Field(description="Derived by code from the terminal action; None if there was none")
    steps_used: int
    max_steps: int
    safety_failure: bool = Field(description="Approved something that should not be approved, or took a forbidden action")
    symptoms: list[Symptom]


# ------------------------------------------------------------------ model output (LLM schema)
class ModelLabel(BaseModel):
    label: str = Field(description="A label id from the failure taxonomy")
    step_ids: list[str] = Field(description="Ids of the trace steps that show this failure, e.g. ['s4']")
    evidence: str = Field(description="A short verbatim quote from one of the cited steps")
    explanation: str = Field(description="One or two sentences: what went wrong at those steps")


class FailureAnalysis(BaseModel):
    labels: list[ModelLabel]
    root_cause: str = Field(description="The label id of the root cause; must be one of the labels above")
    summary: str = Field(description="One sentence a reviewer can read on its own")


# ------------------------------------------------------------------ results
class FailureLabel(BaseModel):
    label: str
    step_ids: list[str]
    evidence: str = ""
    explanation: str
    source: Literal["code", "model"]


class Diagnosis(BaseModel):
    root_cause: str
    summary: str
    labels: list[FailureLabel]


class TraceResult(BaseModel):
    trace_id: str
    task_id: str
    passed: bool
    outcome: str | None
    expected_outcome: str
    safety_failure: bool
    root_cause: str | None = None
    summary: str = ""
    labels: list[FailureLabel] = Field(default_factory=list)


class RunResult(BaseModel):
    run_id: str
    suite_id: str
    agent_version: str
    results: list[TraceResult]

    @property
    def success_rate(self) -> float:
        return round(sum(r.passed for r in self.results) / len(self.results), 3) if self.results else 0.0


class Regression(BaseModel):
    baseline_run: str | None
    candidate_run: str
    baseline_rate: float | None
    candidate_rate: float
    fixed: list[str] = Field(description="Tasks that failed in the baseline and pass now")
    broken: list[str] = Field(description="Tasks that passed in the baseline and fail now")
    still_failing: list[str]
    safety_failures: list[str] = Field(description="Candidate tasks with a safety failure: 'task: reason'")
    mix_baseline: dict[str, int]
    mix_candidate: dict[str, int]
    decision: Literal["go", "conditional", "no-go"]
    reasons: list[str]
