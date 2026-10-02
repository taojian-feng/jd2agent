"""Shared schemas for tools, graphs, and evals."""
from typing import Literal

from pydantic import BaseModel, Field

Cloud = Literal["azure", "aws", "gcp"]
Severity = Literal["blocker", "major", "minor"]


# ------------------------------------------------------------------ W1 inputs/outputs
class Requirement(BaseModel):
    id: str = Field(description="FR-n for functional, NFR-n for non-functional")
    kind: Literal["functional", "non_functional"]
    text: str = Field(description="The requirement, stated as a testable 'shall' sentence")
    source_quote: str = Field(description="Verbatim quote from the brief this requirement comes from")


class Signal(BaseModel):
    name: str = Field(description="A signal name from the pattern catalog")
    value: bool
    evidence_quote: str = Field(description="Verbatim quote from the brief supporting the value, or '' if false")


class Requirements(BaseModel):
    items: list[Requirement]
    signals: list[Signal]


class PatternScore(BaseModel):
    id: str
    name: str
    score: int
    contributions: dict[str, int]


class PatternFit(BaseModel):
    ranked: list[PatternScore]
    modifiers: list[str] = Field(default_factory=list, description="Modifier ids that apply, e.g. M1")
    rationale: str = ""


class Component(BaseModel):
    id: str = Field(description="Short snake_case id")
    name: str
    type: str = Field(description="A component type from the platform catalog, or 'custom'")
    responsibility: str
    satisfies: list[str] = Field(description="Requirement ids this component helps satisfy")


class Flow(BaseModel):
    source: str
    target: str
    label: str = ""


class DataSource(BaseModel):
    name: str
    owner: str
    freshness: str
    sensitivity: Literal["public", "internal", "confidential", "restricted"]


class ComponentDesign(BaseModel):
    pattern_id: str
    components: list[Component]
    flows: list[Flow]
    data_sources: list[DataSource]
    identity_access: str
    human_oversight: str
    failure_modes: list[str]
    cost_estimate: str
    pattern_justification: str = Field("", description="Why this pattern rather than a simpler one (optional)")


class PlatformMapping(BaseModel):
    cloud: Cloud
    services: dict[str, str] = Field(description="component id -> cloud service")
    unmapped: list[str] = Field(default_factory=list, description="component ids with no catalog entry")


class Test(BaseModel):
    id: str
    name: str
    kind: Literal["offline_eval", "unit", "online_monitor"]
    covers: list[str] = Field(description="Component ids this test or metric covers")
    metric: str
    threshold: str


class LLMOpsPlan(BaseModel):
    tests: list[Test]
    monitoring: list[str]
    versioning: str
    governance: list[str]


class TraceReport(BaseModel):
    requirement_coverage: float
    component_coverage: float
    unmapped_requirements: list[str]
    untested_components: list[str]
    unknown_references: list[str]
    passed: bool


class ADR(BaseModel):
    number: int
    title: str
    context: str
    options: list[str]
    decision: str
    consequences: str
    requirement_refs: list[str]


class ADRList(BaseModel):
    adrs: list[ADR]


class ExecSummary(BaseModel):
    markdown: str


class Change(BaseModel):
    rule_id: str = Field(description="The review rule this change resolves")
    section: str = Field(description="Design doc section where the change shows up")
    change: str = Field(description="What was changed, in one or two sentences")


class Revision(BaseModel):
    """Merged result after applying a RevisionPatch (built in code, not by the LLM)."""
    design: ComponentDesign
    llmops: LLMOpsPlan
    changes: list[Change]


class RevisionPatch(BaseModel):
    """What the LLM returns: only the parts it changes. "" / [] = unchanged.
    Every field is required (no defaults): providers limit optional properties in structured-output schemas."""
    changes: list[Change] = Field(description="One entry per finding resolved")
    identity_access: str = Field(description="Full replacement text, or \"\" to keep")
    human_oversight: str = Field(description="Full replacement text, or \"\" to keep")
    failure_modes: list[str] = Field(description="Full replacement list, or [] to keep")
    cost_estimate: str = Field(description="Full replacement text, or \"\" to keep")
    pattern_justification: str = Field(description="Why this pattern over a simpler one, or \"\" to keep")
    monitoring: list[str] = Field(description="Full replacement list, or [] to keep")
    governance: list[str] = Field(description="Full replacement list, or [] to keep")
    versioning: str = Field(description="Full replacement text, or \"\" to keep")
    update_components: list[Component] = Field(description="Existing components to replace, matched by id, or []")
    add_components: list[Component] = Field(description="New components with new ids, or []")
    add_tests: list[Test] = Field(description="New tests or monitors with new ids, or []")


EMPTY_PATCH = {"changes": [], "identity_access": "", "human_oversight": "", "failure_modes": [], "cost_estimate": "",
               "pattern_justification": "", "monitoring": [], "governance": [], "versioning": "",
               "update_components": [], "add_components": [], "add_tests": []}


# ------------------------------------------------------------------ W2 inputs/outputs
class DesignDoc(BaseModel):
    title: str
    sections: dict[str, str] = Field(description="heading -> body text")


class Finding(BaseModel):
    rule_id: str
    category: str
    severity: Severity
    message: str
    section: str = Field(description="Design doc section the finding is about")
    evidence: Literal["quote", "absence"] = Field(
        description="'quote' if citing text in the section; 'absence' if the section lacks what the rule requires")
    quote: str = ""
    source: Literal["deterministic", "judged"]


class RuleVerdict(BaseModel):
    rule_id: str
    verdict: Literal["pass", "fail", "not_applicable"]
    section: str
    evidence: Literal["quote", "absence"]
    quote: str = ""
    message: str


class RuleVerdicts(BaseModel):
    verdicts: list[RuleVerdict]


class Readiness(BaseModel):
    score: float
    by_category: dict[str, float]
    blockers: list[str]
    decision: Literal["go", "conditional", "no-go"]
