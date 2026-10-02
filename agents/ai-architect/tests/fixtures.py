"""Canned model outputs for the dealer fault-diagnosis scenario, used with FakeLLM.
They double as a worked example of what each tool should return."""
import copy

REQUIREMENTS = {
    "items": [
        {"id": "FR-1", "kind": "functional",
         "text": "The assistant shall propose a likely root cause and next inspection or repair steps for a serial number and fault code.",
         "source_quote": "given a machine serial number and fault code, proposes a likely root cause and the next inspection or repair steps"},
        {"id": "FR-2", "kind": "functional",
         "text": "Every recommendation shall cite the manual section, telematics alert, or past repair it relies on.",
         "source_quote": "Every recommendation must cite the manual section, alert, or past repair it relies on"},
        {"id": "FR-3", "kind": "functional",
         "text": "The assistant shall only draft work orders; a technician shall approve each one.",
         "source_quote": "a technician approves any work order it drafts"},
        {"id": "NFR-1", "kind": "non_functional",
         "text": "Responses shall return within about 30 seconds on field tablets.",
         "source_quote": "answers should come back within about 30 seconds"},
        {"id": "NFR-2", "kind": "non_functional",
         "text": "Repair history shall be visible only to the dealer that performed the work.",
         "source_quote": "Access to repair history is restricted to the dealer that performed the work."},
        {"id": "NFR-3", "kind": "non_functional",
         "text": "Manual content shall reflect monthly updates.",
         "source_quote": "Service manuals are updated monthly"},
    ],
    "signals": [
        {"name": "steps_known_upfront", "value": False, "evidence_quote": ""},
        {"name": "open_ended_reasoning", "value": True,
         "evidence_quote": "spends 2–4 hours cross-referencing service manuals, recent telematics alerts, and the machine's repair history"},
        {"name": "knowledge_only", "value": False, "evidence_quote": ""},
        {"name": "many_tools", "value": False, "evidence_quote": ""},
        {"name": "multiple_domains", "value": False, "evidence_quote": ""},
        {"name": "distinct_request_types", "value": False, "evidence_quote": ""},
        {"name": "audit_required", "value": True, "evidence_quote": "technicians and warranty auditors need to verify it"},
        {"name": "writes_to_systems", "value": True, "evidence_quote": "The assistant must not create or close work orders on its own"},
        {"name": "rules_suffice", "value": False, "evidence_quote": ""},
        {"name": "latency_sensitive", "value": False, "evidence_quote": ""},
    ],
}

RATIONALE = {"markdown": (
    "P5 Plan-and-execute ranks first because diagnosis depends on intermediate findings and auditors need a "
    "reviewable plan. P4 single agent ranks second but loses a point for weaker reproducibility. If the "
    "diagnostic procedure were fixed in advance, P2 deterministic workflow would win.")}

DESIGN = {
    "pattern_id": "P5",
    "components": [
        {"id": "tablet_app", "name": "Technician tablet app", "type": "custom",
         "responsibility": "Collect serial number and fault code; show cited diagnosis", "satisfies": ["FR-1", "NFR-1"]},
        {"id": "planner", "name": "Diagnostic planner-executor", "type": "orchestration",
         "responsibility": "Plan lookups, call tools, assemble diagnosis", "satisfies": ["FR-1", "NFR-1"]},
        {"id": "model", "name": "Foundation model", "type": "foundation_model",
         "responsibility": "Planning and diagnosis reasoning", "satisfies": ["FR-1"]},
        {"id": "manual_index", "name": "Service manual index", "type": "vector_store",
         "responsibility": "Retrieve manual sections with section ids", "satisfies": ["FR-2", "NFR-3"]},
        {"id": "manual_ingest", "name": "Monthly manual ingestion", "type": "document_ingestion",
         "responsibility": "Parse and re-index manuals on each release", "satisfies": ["NFR-3"]},
        {"id": "repair_history_tool", "name": "Repair history tool", "type": "tool_gateway",
         "responsibility": "Query dealer repair records with the caller's dealer scope", "satisfies": ["FR-2", "NFR-2"]},
        {"id": "telematics_tool", "name": "Telematics alerts tool", "type": "analytics_data",
         "responsibility": "Fetch recent alerts for the serial number", "satisfies": ["FR-1", "FR-2"]},
        {"id": "workorder_draft", "name": "Work order drafter", "type": "custom",
         "responsibility": "Draft a work order for technician approval; never submits", "satisfies": ["FR-3"]},
        {"id": "citation_check", "name": "Citation validator", "type": "guardrails",
         "responsibility": "Reject any recommendation whose citation is not in retrieved sources", "satisfies": ["FR-2"]},
        {"id": "identity", "name": "Dealer identity and scopes", "type": "identity",
         "responsibility": "Authenticate technicians and carry dealer scope to tools", "satisfies": ["NFR-2"]},
        {"id": "tracing", "name": "Tracing and latency metrics", "type": "observability",
         "responsibility": "Trace every model and tool call", "satisfies": ["NFR-1"]},
    ],
    "flows": [
        {"source": "tablet_app", "target": "identity", "label": "sign in"},
        {"source": "tablet_app", "target": "planner", "label": "serial + fault code"},
        {"source": "planner", "target": "model", "label": "plan / reason"},
        {"source": "planner", "target": "manual_index", "label": "retrieve"},
        {"source": "planner", "target": "repair_history_tool", "label": "dealer-scoped query"},
        {"source": "planner", "target": "telematics_tool", "label": "recent alerts"},
        {"source": "planner", "target": "citation_check", "label": "verify"},
        {"source": "planner", "target": "workorder_draft", "label": "draft"},
        {"source": "manual_ingest", "target": "manual_index", "label": "monthly"},
    ],
    "data_sources": [
        {"name": "Service manuals", "owner": "Product support", "freshness": "monthly", "sensitivity": "internal"},
        {"name": "Telematics alerts", "owner": "Connected equipment team", "freshness": "streaming", "sensitivity": "confidential"},
        {"name": "Repair history", "owner": "Each dealer", "freshness": "daily", "sensitivity": "restricted"},
    ],
    "identity_access": ("Technicians sign in through the dealer identity provider. The planner passes the technician's "
                        "dealer scope to every tool; the repair history tool filters records by that scope server-side."),
    "human_oversight": "The technician approves every drafted work order. Low-confidence diagnoses are flagged for a senior technician.",
    "failure_modes": ["Model timeout: return retrieved sources without a diagnosis",
                      "Empty retrieval: say no documented cause was found; suggest escalation",
                      "Tool error: continue with remaining sources and mark the gap"],
    "cost_estimate": "About $0.04 per diagnosis; about $2,400 per month at an assumed 2,000 diagnoses per day.",
}

DESIGN_MISSING_FR3 = copy.deepcopy(DESIGN)
DESIGN_MISSING_FR3["components"] = [c for c in DESIGN["components"] if c["id"] != "workorder_draft"]
DESIGN_MISSING_FR3["flows"] = [f for f in DESIGN["flows"] if f["target"] != "workorder_draft"]

LLMOPS = {
    "tests": [
        {"id": "E1", "name": "Golden diagnoses", "kind": "offline_eval",
         "covers": ["planner", "model", "manual_index", "telematics_tool", "repair_history_tool"],
         "metric": "top-1 root cause accuracy vs 200 labeled past cases", "threshold": ">= 75%"},
        {"id": "E2", "name": "Citation accuracy", "kind": "offline_eval", "covers": ["citation_check", "manual_index"],
         "metric": "share of citations that support the claim", "threshold": "= 100%"},
        {"id": "U1", "name": "Dealer scope enforcement", "kind": "unit", "covers": ["repair_history_tool", "identity"],
         "metric": "cross-dealer queries return nothing", "threshold": "0 leaks"},
        {"id": "U2", "name": "Work order never submitted", "kind": "unit", "covers": ["workorder_draft"],
         "metric": "submit calls without approval", "threshold": "0"},
        {"id": "U3", "name": "Manual re-index", "kind": "unit", "covers": ["manual_ingest"],
         "metric": "new manual sections searchable after ingest", "threshold": "100%"},
        {"id": "M1", "name": "Latency", "kind": "online_monitor", "covers": ["tablet_app", "tracing", "planner"],
         "metric": "p95 end-to-end latency", "threshold": "<= 30 s"},
    ],
    "monitoring": ["p95 latency and tool error rate per dealer",
                   "Weekly review of technician thumbs-down feedback",
                   "Repeat-visit rate after an assisted diagnosis"],
    "versioning": "Prompts, model ids and tool schemas are versioned together; any change re-runs E1 and E2.",
    "governance": ["Warranty team signs off on citation policy", "Quarterly access review of dealer scopes"],
}

ADRS = {"adrs": [
    {"number": 1, "title": "Plan-and-execute over a single ReAct agent",
     "context": "Diagnoses must be auditable (FR-2) and depend on intermediate findings (FR-1).",
     "options": ["Deterministic workflow", "Single ReAct agent", "Plan-and-execute"],
     "decision": "Plan-and-execute, with the plan stored alongside the diagnosis",
     "consequences": "Reviewable plans; slightly higher latency to watch against NFR-1.",
     "requirement_refs": ["FR-1", "FR-2", "NFR-1"]},
    {"number": 2, "title": "Enforce dealer scope in the tool, not the prompt",
     "context": "Repair history is dealer-restricted (NFR-2).",
     "options": ["Instruct the model to filter", "Filter server-side in the tool"],
     "decision": "Server-side filtering using the caller's identity scope",
     "consequences": "No leakage through prompt injection; tool needs identity propagation.",
     "requirement_refs": ["NFR-2"]},
]}

SUMMARY = {"markdown": (
    "## Executive Summary\n\nTechnicians spend hours matching fault codes to manuals, alerts and past repairs. "
    "The assistant proposes a likely cause and next steps in about 30 seconds, and every recommendation links to "
    "its source so technicians and warranty auditors can check it. It only drafts work orders; a technician "
    "approves each one. Estimated cost is about $2,400 a month at 2,000 diagnoses a day. Main risks are gaps in "
    "manual coverage and over-trust; we measure accuracy on 200 past cases before rollout. Suggested pilot: "
    "8 weeks with two dealers.")}

JUDGED_RULES = ["SEC-02", "SEC-03", "SEC-04", "DAT-02", "REL-01", "REL-02", "REL-03", "EVL-02", "EVL-03",
                "OPS-02", "OPS-03", "CST-02", "RAI-01", "RAI-02"]


HEALTHCARE_JUDGED = ["HC-01", "HC-02", "HC-03", "HC-04", "HC-05", "HC-06"]


def verdicts(bad_quote: bool = False, all_pass: bool = False, extra: list[str] = (),
             fail_extra: dict | None = None) -> dict:
    """extra: more judged rule ids (rule packs) to answer 'pass'; fail_extra: {rule_id: section} to fail by absence."""
    out = []
    for rid in list(JUDGED_RULES) + list(extra):
        v = {"rule_id": rid, "verdict": "pass", "section": "Architecture", "evidence": "quote", "quote": "", "message": "ok"}
        if rid in (fail_extra or {}):
            v.update(verdict="fail", section=fail_extra[rid], evidence="absence", message=f"{rid} not met.")
        if all_pass or rid in extra:
            out.append(v)
            continue
        if rid == "SEC-04":
            v.update(verdict="fail", section="Identity and Access", evidence="absence",
                     message="Prompt-injection risk from retrieved manuals and repair notes is not addressed.")
        if rid == "OPS-03":
            v.update(verdict="fail", section="Observability", evidence="quote",
                     quote="Weekly review of technician thumbs-down feedback" if not bad_quote
                     else "Daily review by the quality team",
                     message="Quality monitoring has no named owner.")
        out.append(v)
    return {"verdicts": out}


from ai_architect.models import EMPTY_PATCH  # noqa: E402

REVISION_PATCH = {
    **EMPTY_PATCH,
    "changes": [
        {"rule_id": "SEC-04", "section": "Identity and Access",
         "change": "Retrieved content is treated as untrusted data, delimited, and tool calls are allow-listed."},
        {"rule_id": "OPS-03", "section": "Observability", "change": "Named the service quality lead as owner."},
    ],
    "identity_access": DESIGN["identity_access"] + (
        " Retrieved manual text, alerts and repair notes are treated as untrusted data: they are delimited in the "
        "prompt, tool calls are allow-listed, and instructions found inside retrieved content are ignored."),
    "pattern_justification": ("A fixed workflow cannot choose which evidence to fetch next for an unfamiliar fault; "
                              "plan-and-execute keeps that flexibility with a reviewable plan."),
    "monitoring": [LLMOPS["monitoring"][0],
                   "Weekly review of technician thumbs-down feedback, owned by the service quality lead",
                   LLMOPS["monitoring"][2]],
}


def responses(first_design_bad: bool = False, first_verdicts_bad: bool = False) -> dict:
    return {
        "Requirements": [REQUIREMENTS],
        "ExecSummary": [RATIONALE, SUMMARY],
        # design_components retries once inside a call, so a bad first attempt needs two bad answers
        "ComponentDesign": ([DESIGN_MISSING_FR3, DESIGN_MISSING_FR3, DESIGN] if first_design_bad else [DESIGN]),
        "LLMOpsPlan": [LLMOPS],
        "ADRList": [ADRS],
        "RuleVerdicts": ([verdicts(bad_quote=True), verdicts()] if first_verdicts_bad else [verdicts()]),
        "RevisionPatch": [REVISION_PATCH],
    }
