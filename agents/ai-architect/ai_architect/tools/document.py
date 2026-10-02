"""Assemble W1 and W2 outputs into markdown. The design doc uses the template's section
headings exactly, so W2 can load and cite it."""
import re

from ai_architect.models import (
    ADR, ComponentDesign, DesignDoc, Finding, LLMOpsPlan, PatternFit, PlatformMapping,
    Readiness, Requirements, TraceReport,
)


def _strip_headings(text: str) -> str:
    """Drop markdown headings from embedded text so they don't break the section structure."""
    return "\n".join(l for l in text.strip().splitlines() if not l.lstrip().startswith("#")).strip()


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "_None._"


def assemble_design_doc(
    title: str, brief: str, requirements: Requirements, pattern_fit: PatternFit,
    design: ComponentDesign, mapping: PlatformMapping, llmops: LLMOpsPlan, trace: TraceReport,
    mermaid: str, adrs: list[ADR], exec_summary: str,
    revision_log: list[dict] | None = None, version: int = 1,
) -> str:
    top = pattern_fit.ranked[0]
    reqs = "\n".join(f"| {r.id} | {r.text} | \"{r.source_quote}\" |" for r in requirements.items)
    ranking = "\n".join(f"| {p.id} | {p.name} | {p.score} | {', '.join(f'{k} {v:+d}' for k, v in p.contributions.items()) or '-'} |"
                        for p in pattern_fit.ranked[:4])
    comps = "\n".join(f"| {c.id} | {c.name} | {c.type} | {c.responsibility} | {', '.join(c.satisfies)} |"
                      for c in design.components)
    tools = [c for c in design.components if c.type in ("tool_gateway", "custom") or "tool" in c.id]
    sources = "\n".join(f"| {d.name} | {d.owner} | {d.freshness} | {d.sensitivity} |" for d in design.data_sources)
    tests = "\n".join(f"| {t.id} | {t.name} | {t.kind} | {', '.join(t.covers)} | {t.metric} | {t.threshold} |"
                      for t in llmops.tests)
    platform = "\n".join(f"| {cid} | {svc} |" for cid, svc in mapping.services.items())
    adr_md = "\n\n".join(
        f"### ADR-{a.number}: {a.title}\n\n- **Context:** {a.context}\n- **Options:** {'; '.join(a.options)}\n"
        f"- **Decision:** {a.decision}\n- **Consequences:** {a.consequences}\n- **Requirements:** {', '.join(a.requirement_refs)}"
        for a in adrs)
    trace_rows = "\n".join(
        f"| {r.id} | {', '.join(c.id for c in design.components if r.id in c.satisfies) or '**unmapped**'} |"
        for r in requirements.items)
    open_q = [f"Unmapped requirement {r}" for r in trace.unmapped_requirements] + \
             [f"Untested component {c}" for c in trace.untested_components] + \
             [f"No {mapping.cloud} catalog entry for component {c}" for c in mapping.unmapped]

    justification = (f"\n**Why this pattern rather than a simpler one:** {design.pattern_justification}\n"
                     if design.pattern_justification else "")
    revisions = ""
    if revision_log:
        rows = "\n".join(f"| {e['round']} | {e['rule_id']} | {e['severity']} | {e['finding']} | {e['change']} |"
                         for e in revision_log)
        revisions = (f"## Revision Log\nVersion {version}. Changes made in response to architecture review findings.\n\n"
                     f"| Round | Rule | Severity | Finding | Change made |\n|---|---|---|---|---|\n{rows}\n\n")
    heading = title if version == 1 else f"{title} (v{version})"
    return f"""# {heading}

{exec_summary}

## Problem Statement
{_strip_headings(brief)}

## Requirements
| ID | Requirement | Source (brief) |
|---|---|---|
{reqs}

## Pattern Selection
**Selected: {top.id} {top.name}** (score {top.score}). Modifiers: {', '.join(pattern_fit.modifiers) or 'none'}.

| ID | Pattern | Score | Signal contributions |
|---|---|---|---|
{ranking}

{pattern_fit.rationale}
{justification}
## Architecture
```mermaid
{mermaid}
```

| ID | Component | Type | Responsibility | Satisfies |
|---|---|---|---|---|
{comps}

## Tools and Integrations
{_bullets([f"{c.name}: {c.responsibility}" for c in tools])}

## Data Sources
| Source | Owner | Freshness | Sensitivity |
|---|---|---|---|
{sources}

## Identity and Access
{design.identity_access}

## Human Oversight
{design.human_oversight}

## Failure Modes
{_bullets(design.failure_modes)}

## Evaluation
| ID | Test | Kind | Covers | Metric | Threshold |
|---|---|---|---|---|---|
{tests}

## Observability
{_bullets(llmops.monitoring)}

Versioning: {llmops.versioning}

Governance:
{_bullets(llmops.governance)}

## Cost
{design.cost_estimate}

## Platform Mapping
Cloud: **{mapping.cloud}**

| Component | Service |
|---|---|
{platform}

## Decisions (ADRs)
{adr_md or '_None._'}

## Traceability
Requirement coverage {trace.requirement_coverage:.0%} · component test coverage {trace.component_coverage:.0%} · {'PASSED' if trace.passed else 'GAPS BELOW'}

| Requirement | Components |
|---|---|
{trace_rows}

{revisions}## Open Questions
{_bullets(open_q)}
"""


def assemble_review(doc: DesignDoc, findings: list[Finding], rejected: list[Finding], readiness: Readiness,
                    packs: list[str] | None = None) -> str:
    order = {"blocker": 0, "major": 1, "minor": 2}
    def evidence(f: Finding) -> str:
        return f'"{f.quote}"' if f.evidence == "quote" else "(missing)"

    rows = "\n".join(
        f"| {f.severity} | {f.rule_id} | {f.section} | {f.message} | {evidence(f)} |"
        for f in sorted(findings, key=lambda f: (order[f.severity], f.rule_id)))
    cats = "\n".join(f"| {c} | {s:.0f} |" for c, s in readiness.by_category.items())
    note = (f"\n{len(rejected)} candidate finding(s) were discarded because their citation could not be verified.\n"
            if rejected else "")
    return f"""# Architecture Review: {doc.title}

**Decision: {readiness.decision.upper()}** · readiness {readiness.score:.0f}/100 · blockers: {', '.join(readiness.blockers) or 'none'}

Rulebook: general{''.join(f' + {p}' for p in packs or [])}

## Findings
| Severity | Rule | Section | Finding | Evidence |
|---|---|---|---|---|
{rows or '| - | - | - | No findings | - |'}
{note}
## Scores by Category
| Category | Score |
|---|---|
{cats}
"""


def assemble_brief(title: str, design_state: dict, history: list[dict]) -> str:
    """One-page brief built deterministically from the final design state and the review history."""
    fit, design, mapping = design_state["fit"], design_state["design"], design_state["mapping"]
    top = fit.ranked[0]
    progression = "\n".join(
        f"| v{h['version']} | {h['decision'].upper()} | {h['score']:.0f} | "
        f"{', '.join(f'{rid} ({sev})' for sev, rid in h['findings']) or 'none'} |" for h in history)
    resolved = design_state.get("revision_log") or []
    resolved_md = "\n".join(f"- **{e['rule_id']}** ({e['severity']}): {e['change']}" for e in resolved) or "- None needed."
    services = sorted(set(mapping.services.values()))
    adrs = "\n".join(f"- ADR-{a.number}: {a.title}" for a in design_state.get("adrs", []))
    summary = re.sub(r"^#+ .*\n", "", design_state["summary"].strip()).strip()
    version = design_state.get("version", 1)
    final = history[-1] if history else None
    return f"""# {title}: one-page brief

**Final review: {final['decision'].upper() if final else 'n/a'}** (readiness {final['score']:.0f}/100) after {len(history) - 1} revision round(s).
Pattern: **{top.id} {top.name}** · cloud: **{mapping.cloud}** · {len(design.components)} components · design v{version}

{summary}

## Architecture
```mermaid
{design_state['mermaid']}
```

## Review history
| Version | Decision | Readiness | Findings |
|---|---|---|---|
{progression}

## What the review made us change
{resolved_md}

## Key decisions
{adrs or '- None recorded.'}

## Services ({mapping.cloud})
{', '.join(services)}

_Full design: {'design.md' if version == 1 else f'design_v{version}.md'} · reviews: review*.md_
"""
