"""LLM-backed tools. Each one pairs a prompt with a deterministic validator (see call_validated),
so nothing leaves a tool without passing its checks."""
import json
import re

from ai_architect import catalog
from ai_architect.llm import LLM, call_validated
from ai_architect.models import (
    ADR, ADRList, ComponentDesign, DesignDoc, ExecSummary, Finding, LLMOpsPlan, PatternFit,
    Requirements, Revision, RevisionPatch, RuleVerdicts,
)
from ai_architect.tools.deterministic import quote_in

ARCHITECT = ("You are a principal enterprise AI architect. Be concrete, prefer the simplest design that "
             "meets the requirements, and never invent facts that are not in the inputs.")


def _dump(model) -> str:
    return json.dumps(model.model_dump() if hasattr(model, "model_dump") else model, indent=1)


# ------------------------------------------------------------------ extract_requirements
def validate_requirements(reqs: Requirements, brief: str) -> list[str]:
    problems = []
    ids = [r.id for r in reqs.items]
    if not reqs.items:
        problems.append("no requirements extracted")
    if len(ids) != len(set(ids)):
        problems.append("requirement ids are not unique")
    for r in reqs.items:
        prefix = "FR-" if r.kind == "functional" else "NFR-"
        if not r.id.startswith(prefix):
            problems.append(f"{r.id}: {r.kind} requirement ids must start with {prefix}")
        if not quote_in(r.source_quote, brief):
            problems.append(f"{r.id}: source_quote is not verbatim in the brief: {r.source_quote!r}")
    known = set(catalog.patterns()["signals"])
    seen = {s.name for s in reqs.signals}
    for name in sorted(known - seen):
        problems.append(f"signal {name} is missing; give every catalog signal a value")
    for s in reqs.signals:
        if s.name not in known:
            problems.append(f"unknown signal {s.name}")
        elif s.value and not quote_in(s.evidence_quote, brief):
            problems.append(f"signal {s.name}=true needs a verbatim evidence_quote from the brief")
    return problems


def extract_requirements(llm: LLM, brief: str) -> Requirements:
    signals = "\n".join(f"- {k}: {v}" for k, v in catalog.patterns()["signals"].items())
    user = f"""Extract requirements from this business brief.

Rules:
- Functional requirements get ids FR-1, FR-2...; non-functional get NFR-1, NFR-2...
- Each requirement is a testable 'shall' statement.
- source_quote must be copied verbatim from the brief (a phrase or sentence).
- Give EVERY signal below a true/false value. For true, quote the brief as evidence; for false, use ''.
- Apply each definition literally, including any thresholds. Set true only if the quoted evidence meets
  the definition, not merely if the brief mentions the topic.

Signals:
{signals}

Brief:
<<<
{brief}
>>>"""
    return call_validated(llm, Requirements, ARCHITECT, user,
                          lambda r: validate_requirements(r, brief), "extract_requirements")


# ------------------------------------------------------------------ pattern rationale
def explain_pattern_fit(llm: LLM, requirements: Requirements, fit: PatternFit) -> PatternFit:
    """The ranking is deterministic; the LLM only explains it. Validator: rationale names the top pattern."""
    user = f"""In 3-5 sentences, explain why {fit.ranked[0].id} ({fit.ranked[0].name}) ranks first for these
requirements, why the runner-up ranks lower, and what change in requirements would flip the choice.
Do not change the ranking.

Ranking: {_dump([p.model_dump() for p in fit.ranked[:3]])}
Requirements: {_dump(requirements)}"""
    top = fit.ranked[0].id
    out = call_validated(llm, ExecSummary, ARCHITECT, user,
                         lambda s: [] if top in s.markdown else [f"rationale must name {top}"],
                         "explain_pattern_fit")
    return fit.model_copy(update={"rationale": out.markdown})


# ------------------------------------------------------------------ design_components
def validate_design(design: ComponentDesign, reqs: Requirements, pattern_id: str) -> list[str]:
    problems = []
    req_ids = {r.id for r in reqs.items}
    comp_ids = [c.id for c in design.components]
    types = set(catalog.platforms()["components"]) | {"custom"}
    if design.pattern_id != pattern_id:
        problems.append(f"pattern_id must be {pattern_id}")
    if len(comp_ids) != len(set(comp_ids)):
        problems.append("component ids are not unique")
    for c in design.components:
        if c.type not in types:
            problems.append(f"{c.id}: type {c.type!r} is not in the platform catalog; use one of {sorted(types)}")
        for rid in c.satisfies:
            if rid not in req_ids:
                problems.append(f"{c.id}: satisfies unknown requirement {rid}")
    for f in design.flows:
        for end in (f.source, f.target):
            if end not in comp_ids:
                problems.append(f"flow {f.source}->{f.target}: unknown component {end}")
    unmapped = req_ids - {rid for c in design.components for rid in c.satisfies}
    if unmapped:
        problems.append(f"requirements not satisfied by any component: {sorted(unmapped)}")
    if not design.data_sources:
        problems.append("list the data sources")
    return problems


def design_components(llm: LLM, reqs: Requirements, fit: PatternFit, gaps: list[str] | None = None) -> ComponentDesign:
    top = fit.ranked[0]
    mods = [m for m in catalog.patterns()["modifiers"] if m["id"] in fit.modifiers]
    user = f"""Design the components for this solution using pattern {top.id} ({top.name}).
Apply these modifiers: {_dump(mods)}

Rules:
- Component type must be one of: {sorted(catalog.platforms()['components'])} or 'custom'.
- Every requirement id must appear in at least one component's 'satisfies'.
- flows connect component ids. Include identity/access, human oversight, failure modes and a cost estimate
  (cost per request and monthly at an assumed volume; state the assumption).
{('- Fix these gaps from the last attempt: ' + '; '.join(gaps)) if gaps else ''}

Requirements: {_dump(reqs)}"""
    return call_validated(llm, ComponentDesign, ARCHITECT, user,
                          lambda d: validate_design(d, reqs, top.id), "design_components",
                          strict=False)  # coverage gaps are caught by check_traceability


# ------------------------------------------------------------------ plan_llmops
def validate_llmops(plan: LLMOpsPlan, design: ComponentDesign) -> list[str]:
    comp_ids = {c.id for c in design.components}
    covered = {cid for t in plan.tests for cid in t.covers}
    problems = [f"test {t.id} covers unknown component {cid}" for t in plan.tests for cid in t.covers
                if cid not in comp_ids]
    problems += [f"component {cid} has no test or metric" for cid in sorted(comp_ids - covered)]
    if not any(t.kind == "offline_eval" for t in plan.tests):
        problems.append("include at least one offline_eval with a dataset and threshold")
    return problems


def plan_llmops(llm: LLM, design: ComponentDesign) -> LLMOpsPlan:
    user = f"""Write the LLMOps plan for this design: offline evals (dataset + metric + threshold), unit tests
for deterministic parts, online monitors, versioning of prompts/models/tools, and governance controls.
Every component id must be covered by at least one test or monitor.
Keep it focused: at most 12 tests and monitors in total, so group related checks and let one test cover
several components. Prioritize the requirements with the highest risk.

Design: {_dump(design)}"""
    return call_validated(llm, LLMOpsPlan, ARCHITECT, user, lambda p: validate_llmops(p, design), "plan_llmops",
                          strict=False)


# ------------------------------------------------------------------ draft_adrs
def validate_adrs(adrs: ADRList, reqs: Requirements) -> list[str]:
    req_ids = {r.id for r in reqs.items}
    problems = [] if adrs.adrs else ["write at least one ADR"]
    for a in adrs.adrs:
        if len(a.options) < 2:
            problems.append(f"ADR-{a.number}: list at least two options, including the simpler alternative")
        if not a.requirement_refs:
            problems.append(f"ADR-{a.number}: cite the requirement ids that drive it")
        problems += [f"ADR-{a.number}: unknown requirement {r}" for r in a.requirement_refs if r not in req_ids]
    return problems


def draft_adrs(llm: LLM, reqs: Requirements, fit: PatternFit, design: ComponentDesign) -> list[ADR]:
    user = f"""Write 2-4 architecture decision records for the most consequential choices in this design
(pattern choice first). Each lists at least two options, including the simpler alternative, and cites the
requirement ids that drive it.

Pattern ranking: {_dump([p.model_dump() for p in fit.ranked[:3]])}
Design: {_dump(design)}
Requirements: {_dump(reqs)}"""
    return call_validated(llm, ADRList, ARCHITECT, user, lambda a: validate_adrs(a, reqs), "draft_adrs").adrs


# ------------------------------------------------------------------ write_exec_summary
ACRONYM_OK = {"AI", "IT", "US", "ID"}


def validate_exec_summary(s: ExecSummary) -> list[str]:
    text = s.markdown
    problems = []
    words = len(text.split())
    if words > 400:
        problems.append(f"summary is {words} words; keep it under 400")
    for base in dict.fromkeys(re.findall(r"\b([A-Z]{2,6})s?\b", text)):
        if base in ACRONYM_OK:
            continue
        first = re.search(rf"\b{base}s?\b", text).start()
        if text[max(0, first - 1):first] != "(":
            problems.append(f"expand {base} on first use, e.g. 'full name ({base})'")
    return problems


def write_exec_summary(llm: LLM, design: ComponentDesign, brief: str) -> str:
    user = f"""Write a one-page executive summary of about 300 words (hard limit 400) for a business leader: the problem,
what the solution does, how people stay in control, cost, key risks, and a suggested pilot timeline.
No jargon; expand every acronym on first use as 'full name (ACRONYM)'. Start with a '## Executive Summary' line.

Brief: {brief}
Design: {_dump(design)}"""
    return call_validated(llm, ExecSummary, ARCHITECT, user, validate_exec_summary, "write_exec_summary",
                          retries=2).markdown


# ------------------------------------------------------------------ judge_rules (W2)
def validate_verdicts(v: RuleVerdicts, doc: DesignDoc, rule_ids: list[str]) -> list[str]:
    problems = []
    got = [x.rule_id for x in v.verdicts]
    for rid in rule_ids:
        if got.count(rid) != 1:
            problems.append(f"give exactly one verdict for {rid}")
    for x in v.verdicts:
        if x.rule_id not in rule_ids:
            problems.append(f"{x.rule_id} was not requested")
        if x.verdict == "fail" and x.evidence == "quote":
            if x.section not in doc.sections or not quote_in(x.quote, doc.sections[x.section]):
                problems.append(f"{x.rule_id}: quote is not verbatim in section {x.section!r}")
    return problems


def judge_rules(llm: LLM, doc: DesignDoc, rule_ids: list[str] | None = None,
                packs: list[str] | tuple[str, ...] = ()) -> list[Finding]:
    rules = [r for r in catalog.rules(packs) if r["check"] == "judged" and (rule_ids is None or r["id"] in rule_ids)]
    ids = [r["id"] for r in rules]
    rule_text = "\n".join(f"- {r['id']} ({r['severity']}): {r['rule']}" for r in rules)
    sections = "\n\n".join(f"## {k}\n{v}" for k, v in doc.sections.items())
    user = f"""Review this AI solution design against each rule. For every rule give pass, fail, or not_applicable.
For a fail: name the section it concerns; if you rely on text, set evidence='quote' and copy the text verbatim
from that section; if the problem is that something is missing, set evidence='absence'. Be strict but fair:
fail only when the design really falls short.

Rules:
{rule_text}

Design: {doc.title}
{sections}"""
    verdicts = call_validated(llm, RuleVerdicts, ARCHITECT, user,
                              lambda v: validate_verdicts(v, doc, ids), "judge_rules")
    by_id = {r["id"]: r for r in rules}
    return [Finding(rule_id=x.rule_id, category=by_id[x.rule_id]["category"], severity=by_id[x.rule_id]["severity"],
                    message=x.message, section=x.section, evidence=x.evidence, quote=x.quote, source="judged")
            for x in verdicts.verdicts if x.verdict == "fail"]


# ------------------------------------------------------------------ revise_design (W2 -> W1 loop)
PATCH_FIELDS_DESIGN = ("identity_access", "human_oversight", "failure_modes", "cost_estimate",
                       "pattern_justification")
PATCH_FIELDS_LLMOPS = ("monitoring", "governance", "versioning")


def apply_patch(design: ComponentDesign, llmops: LLMOpsPlan, patch: RevisionPatch) -> tuple[ComponentDesign, LLMOpsPlan, list[str]]:
    """Deterministically merge a patch. Returns (design, llmops, problems)."""
    problems = []
    d = design.model_copy(deep=True)
    o = llmops.model_copy(deep=True)
    for f in PATCH_FIELDS_DESIGN:
        if getattr(patch, f):  # empty = unchanged
            setattr(d, f, getattr(patch, f))
    for f in PATCH_FIELDS_LLMOPS:
        if getattr(patch, f):
            setattr(o, f, getattr(patch, f))
    by_id = {c.id: i for i, c in enumerate(d.components)}
    for c in patch.update_components:
        if c.id in by_id:
            d.components[by_id[c.id]] = c
        else:
            problems.append(f"update_components: {c.id} does not exist; use add_components for new ones")
    for c in patch.add_components:
        if c.id in by_id:
            problems.append(f"add_components: {c.id} already exists; use update_components")
        else:
            d.components.append(c)
            by_id[c.id] = len(d.components) - 1
    test_ids = {t.id for t in o.tests}
    for t in patch.add_tests:
        if t.id in test_ids:
            problems.append(f"add_tests: test id {t.id} already exists")
        else:
            o.tests.append(t)
    return d, o, problems


def validate_revision(patch: RevisionPatch, reqs: Requirements, pattern_id: str, findings: list[Finding],
                      design: ComponentDesign, llmops: LLMOpsPlan) -> list[str]:
    d, o, problems = apply_patch(design, llmops, patch)
    problems += validate_design(d, reqs, pattern_id) + validate_llmops(o, d)
    must_fix = {f.rule_id for f in findings if f.severity in ("blocker", "major")}
    addressed = {c.rule_id for c in patch.changes}
    problems += [f"no change listed that resolves {rid}" for rid in sorted(must_fix - addressed)]
    known = {f.rule_id for f in findings}
    problems += [f"change refers to {rid}, which is not one of the findings" for rid in sorted(addressed - known)]
    return problems


def _pack_rules(packs) -> str:
    """Domain rules shown to the reviser every round, so a fix doesn't leave the next domain gap open."""
    rules = [r for p in packs for r in catalog.pack(p)["rules"]]
    if not rules:
        return ""
    listing = "\n".join(f"- {r['id']} ({r['severity']}): {' '.join(r['rule'].split())}" for r in rules)
    return ("\nThe review also applies these domain rules. While patching, check the whole design against each one "
            "and close any gap you see now, even if it was not reported; list such fixes under the finding they "
            f"relate to.\n{listing}\n")


def revise_design(llm: LLM, reqs: Requirements, fit: PatternFit, design: ComponentDesign,
                  llmops: LLMOpsPlan, findings: list[Finding], packs: list[str] | tuple[str, ...] = ()) -> Revision:
    rules = {r["id"]: " ".join(r["rule"].split()) for r in catalog.all_rules()}
    listing = "\n".join(
        f"- {f.rule_id} ({f.severity}) in '{f.section}': {f.message}\n  Rule: {rules.get(f.rule_id, '')}"
        + (f'\n  Cited text: "{f.quote}"' if f.evidence == "quote" else "")
        for f in findings)
    user = f"""An architecture review of this design found the problems below. Return a PATCH that resolves every
blocker and major finding, and the minor ones where the fix is small.

Patch rules:
- Return only what changes. Leave a text field "" or a list [] to keep it as it is.
- Text and list fields you return replace the old value completely, so include the unchanged parts you keep.
- Keep pattern {fit.ranked[0].id} and existing component ids. To change a component, put the full component in
  update_components; new components go in add_components with new ids (and add_tests to cover them).
- Put each fix where a reviewer will look: identity_access, human_oversight, failure_modes, cost_estimate,
  pattern_justification (why this pattern over a simpler one), monitoring, governance, versioning.
- Resolve contradictions explicitly (e.g. if logs hold restricted data, state retention, redaction and access).
- List one change per finding you resolved, naming the rule id and the section where the fix appears.

Findings:
{listing}
{_pack_rules(packs)}
Current design: {_dump(design)}
Current LLMOps plan: {_dump(llmops)}
Requirement ids: {[r.id for r in reqs.items]}"""
    patch = call_validated(llm, RevisionPatch, ARCHITECT, user,
                           lambda p: validate_revision(p, reqs, fit.ranked[0].id, findings, design, llmops),
                           "revise_design", strict=False)  # the re-review is the real check
    d, o, _ = apply_patch(design, llmops, patch)
    return Revision(design=d, llmops=o, changes=patch.changes)
