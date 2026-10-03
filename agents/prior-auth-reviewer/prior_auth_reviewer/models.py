"""Schemas. LLM-facing ones are flat and all-required (provider limits on structured output)."""
from typing import Literal

from pydantic import BaseModel, Field

FindingValue = Literal["met", "not_met", "unknown", "waived"]


# ------------------------------------------------------------------ proposer (LLM)
class CriterionFinding(BaseModel):
    criterion_id: str = Field(description="e.g. C2")
    finding: FindingValue
    clause_id: str = Field(description="Policy clause applied, e.g. MP-117#C2; for 'waived' the red-flag clause MP-117#RF")
    sentence_ids: list[str] = Field(description="Note sentences relied on, e.g. ['N5']; [] only when the evidence is an absence")
    rationale: str = Field(description="One sentence tying the cited sentences to the criterion")


class Proposal(BaseModel):
    findings: list[CriterionFinding]
    red_flag: str = Field(description="The red flag found, quoted from the notes, or '' if none")


# ------------------------------------------------------------------ critic (LLM)
class CriticVerdict(BaseModel):
    criterion_id: str
    agree: bool
    problem: str = Field(description="'' when agreeing; otherwise what is wrong with the finding or its citation")


class Critique(BaseModel):
    verdicts: list[CriticVerdict]


# ------------------------------------------------------------------ judge (code) and results
class Decision(BaseModel):
    outcome: Literal["approve", "request_info", "human_review"]
    reason: str
    items: list[str] = Field(default_factory=list, description="Documentation to request, for request_info")


class CaseResult(BaseModel):
    case_id: str
    outcome: str
    reason: str
    findings: list[CriterionFinding] = Field(default_factory=list)
    critique: list[CriticVerdict] = Field(default_factory=list)
    context_kept: int = 0
    context_dropped: int = 0
    llm_calls: int = 0
    error: str = ""
