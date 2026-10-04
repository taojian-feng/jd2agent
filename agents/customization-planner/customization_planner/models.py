"""Typed records for the planner. The memo schema (the only model-facing one) is flat and all-required."""
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["first_pass", "failing_run"]


class Finding(BaseModel):
    criterion_id: str
    finding: str
    sentence_ids: list[str]
    rationale: str


class DecisionRecord(BaseModel):
    """What one trace tells us about the model's decisions, next to the code's verdict on the run."""
    run_id: str
    task_id: str
    passed: bool
    expected_outcome: str
    outcome: str | None
    safety_failure: bool
    symptoms: list[str]
    first_pass: list[Finding] = Field(default_factory=list)
    disputed: list[str] = Field(default_factory=list, description="Criteria the critic disagreed with")
    final: list[Finding] = Field(default_factory=list, description="Findings the run acted on (revised if revised)")
    first_red_flag: str = ""
    red_flag: str = ""
    model_calls: int = 0
    prompt: str = ""
    context_matches_trace: bool = True


class DecisionChange(BaseModel):
    """A model decision that differs from the verified answer for the same task and criterion."""
    task_id: str
    criterion_id: str
    run_id: str
    source: Source
    got: str
    verified: str
    evidence_in_context: bool
    route: str


class FailureRoute(BaseModel):
    run_id: str
    task_id: str
    label: str
    route: str
    fix: str


class SFTExample(BaseModel):
    id: str
    task_id: str
    expected_outcome: str
    runs: list[str]
    system: str
    prompt: str
    completion: str


class PreferencePair(BaseModel):
    id: str
    task_id: str
    criteria: list[str] = Field(description="Criteria where chosen and rejected differ")
    source: Source
    runs: list[str]
    system: str
    prompt: str
    chosen: str
    rejected: str


class Gate(BaseModel):
    name: str
    target: str
    actual: str
    passed: bool


class Plan(BaseModel):
    plan_id: str
    runs: list[str]
    traces: int
    passed: int
    routes: list[FailureRoute]
    changes: list[DecisionChange]
    unverifiable_changes: int
    sft: list[SFTExample]
    pairs: list[PreferencePair]
    stats: dict
    split: dict[str, list[str]]
    gates: list[Gate]
    verdict: Literal["ready", "not_ready", "fix_first"]
    recommendation: list[str]


# ------------------------------------------------------------------ model output (LLM schema)
class Memo(BaseModel):
    headline: str = Field(description="One sentence: the answer to 'should we fine-tune?'")
    body: str = Field(description="Markdown, under 250 words: what the traces show, the fix route, what data is still needed")
    numbers_used: list[str] = Field(description="Every number that appears in headline or body, as written")
