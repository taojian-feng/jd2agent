"""Deterministic tools: no LLM, fully reproducible, unit-tested.

These are the checks that make LLM output trustworthy: pattern scoring, platform lookup,
traceability, citation verification, rule checks, and readiness scoring.
"""
import re

from ai_architect import catalog
from ai_architect.models import (
    ComponentDesign, DesignDoc, Finding, LLMOpsPlan, PatternFit, PatternScore,
    PlatformMapping, Readiness, Requirements, TraceReport,
)


# ------------------------------------------------------------------ text helpers
def normalize(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_in(quote: str, text: str) -> bool:
    """True if quote appears in text, ignoring whitespace, case, and smart punctuation."""
    q = normalize(quote)
    return bool(q) and q in normalize(text)


# ------------------------------------------------------------------ W1
def assess_pattern_fit(requirements: Requirements) -> PatternFit:
    """Rank agent patterns by summing catalog weights over the extracted signals."""
    cat = catalog.patterns()
    active = {s.name for s in requirements.signals if s.value}
    ranked = []
    for p in cat["patterns"]:
        contrib = {sig: w for sig, w in p["fit"].items() if sig in active}
        ranked.append(PatternScore(id=p["id"], name=p["name"], score=sum(contrib.values()), contributions=contrib))
    # stable tie-break: simpler pattern (lower id) first
    ranked.sort(key=lambda r: (-r.score, r.id))
    modifiers = []
    if active & {"writes_to_systems", "audit_required"}:
        modifiers.append("M1")
    if "audit_required" in active:
        modifiers.append("M2")
    return PatternFit(ranked=ranked, modifiers=modifiers)


def map_platform(design: ComponentDesign, cloud: str) -> PlatformMapping:
    """Look up each component type in the platform catalog. Never invents a service."""
    table = catalog.platforms()["components"]
    services, unmapped = {}, []
    for c in design.components:
        entry = table.get(c.type)
        if entry and cloud in entry:
            services[c.id] = entry[cloud]
        else:
            unmapped.append(c.id)
    return PlatformMapping(cloud=cloud, services=services, unmapped=unmapped)


def check_traceability(requirements: Requirements, design: ComponentDesign, llmops: LLMOpsPlan) -> TraceReport:
    """W1's done-when gate: every requirement maps to a component; every component has a test."""
    req_ids = {r.id for r in requirements.items}
    comp_ids = {c.id for c in design.components}
    satisfied = {rid for c in design.components for rid in c.satisfies}
    tested = {cid for t in llmops.tests for cid in t.covers}
    unknown = sorted((satisfied - req_ids) | (tested - comp_ids))
    unmapped = sorted(req_ids - satisfied)
    untested = sorted(comp_ids - tested)
    rc = 1.0 if not req_ids else round(1 - len(unmapped) / len(req_ids), 3)
    cc = 1.0 if not comp_ids else round(1 - len(untested) / len(comp_ids), 3)
    return TraceReport(requirement_coverage=rc, component_coverage=cc, unmapped_requirements=unmapped,
                       untested_components=untested, unknown_references=unknown,
                       passed=not (unmapped or untested or unknown))


def _mid(s: str) -> str:
    return re.sub(r"\W", "_", s)


def _mlabel(s: str) -> str:
    return s.replace('"', "'").replace("\n", " ")


def render_diagram(design: ComponentDesign) -> str:
    """Mermaid flowchart of components and flows."""
    lines = ["flowchart LR"]
    for c in design.components:
        lines.append(f'  {_mid(c.id)}["{_mlabel(c.name)}<br/><small>{_mlabel(c.type)}</small>"]')
    for f in design.flows:
        arrow = f' -- "{_mlabel(f.label)}" --> ' if f.label else " --> "
        lines.append(f"  {_mid(f.source)}{arrow}{_mid(f.target)}")
    return "\n".join(lines)


# ------------------------------------------------------------------ W2
_COMMENT = re.compile(r"<!--.*?-->", re.S)


def load_design(markdown: str) -> DesignDoc:
    """Split a markdown design doc into sections by '## ' headings (the citation anchors)."""
    title_match = re.search(r"^# (.+)$", markdown, re.M)
    title = title_match.group(1).strip() if title_match else "Untitled design"
    sections: dict[str, str] = {}
    current = None
    for line in markdown.splitlines():
        m = re.match(r"^## (.+)$", line)
        if m:
            current = m.group(1).strip()
            sections[current] = ""
        elif current is not None:
            sections[current] += line + "\n"
    return DesignDoc(title=title, sections={k: _COMMENT.sub("", v).strip() for k, v in sections.items()})


def run_rule_checks(doc: DesignDoc) -> list[Finding]:
    """Deterministic rules: the required section exists and has content."""
    findings = []
    for r in catalog.rules():
        if r["check"] != "deterministic":
            continue
        section = r["requires_section"]
        body = doc.sections.get(section, "")
        if len(body.split()) < 5:  # missing or placeholder-only
            state = "is missing" if section not in doc.sections else "is empty"
            findings.append(Finding(
                rule_id=r["id"], category=r["category"], severity=r["severity"], section=section,
                evidence="absence", source="deterministic",
                message=f"Section '{section}' {state}. Rule: {r['rule']}"))
    return findings


def validate_citations(findings: list[Finding], doc: DesignDoc) -> tuple[list[Finding], list[Finding]]:
    """Split findings into (valid, invalid). A quote must exist in the cited section;
    an absence finding must name a section in the template or the doc."""
    known_sections = set(doc.sections) | set(catalog.template_sections())
    valid, invalid = [], []
    for f in findings:
        if f.evidence == "quote":
            ok = f.section in doc.sections and quote_in(f.quote, doc.sections[f.section])
        else:
            ok = f.section in known_sections
        (valid if ok else invalid).append(f)
    return valid, invalid


PENALTY = {"blocker": 50, "major": 25, "minor": 10}


def score_readiness(findings: list[Finding]) -> Readiness:
    cats = catalog.load("review_rules.yaml")["categories"]
    by_cat = {c: 100.0 for c in cats}
    for f in findings:
        by_cat[f.category] = max(0.0, by_cat.get(f.category, 100.0) - PENALTY[f.severity])
    blockers = sorted({f.rule_id for f in findings if f.severity == "blocker"})
    if blockers:
        decision = "no-go"
    elif any(f.severity == "major" for f in findings):
        decision = "conditional"
    else:
        decision = "go"
    return Readiness(score=round(sum(by_cat.values()) / len(by_cat), 1), by_category=by_cat,
                     blockers=blockers, decision=decision)
