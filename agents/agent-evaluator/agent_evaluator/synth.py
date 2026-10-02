"""Synthetic traces for the prior-auth scenario: a correct run per case, plus planted failures.

Every planted failure is a small, named change to a correct run, so its label is known exactly.
Regenerate the committed traces with:

    python -m agent_evaluator.synth            (writes traces/eval-set, traces/prior-auth-v1, traces/prior-auth-v2)

The output is deterministic; a test checks the committed files match the generator.
"""
import copy
import json
from pathlib import Path

import yaml

POLICY = {
    "policy_id": "MP-117",
    "title": "MRI of the lumbar spine",
    "criteria": [
        {"id": "C1", "text": "Low back pain for at least 6 weeks"},
        {"id": "C2", "text": "At least 6 weeks of conservative therapy (physical therapy, medication or both) "
                             "that did not resolve symptoms"},
        {"id": "C3", "text": "A neurological exam is documented"},
        {"id": "C4", "text": "No lumbar MRI in the past 12 months"},
    ],
    "red_flags": ["progressive neurological deficit", "suspected cauda equina syndrome",
                  "history of cancer with new back pain"],
    "red_flags_waive": ["C1", "C2"],
}
KNEE_POLICY = {
    "policy_id": "MP-171",
    "title": "MRI of the knee",
    "criteria": [
        {"id": "K1", "text": "Knee pain for at least 4 weeks"},
        {"id": "K2", "text": "Plain X-ray of the knee completed"},
        {"id": "K3", "text": "Mechanical symptoms (locking or giving way) documented"},
    ],
}

# finding, evidence per criterion; evidence is the agent's own statement, grounded in the notes
CASES = {
    "PA-001": {
        "member": "M-1001", "active": True, "outcome": "approve",
        "notes": "Patient reports low back pain for 10 weeks. Completed 8 weeks of physical therapy and daily NSAIDs "
                 "without relief. Neurological exam: strength 5/5, reflexes symmetric, sensation intact. "
                 "No prior spine imaging.",
        "findings": {"C1": ("met", "low back pain for 10 weeks"),
                     "C2": ("met", "Completed 8 weeks of physical therapy and daily NSAIDs without relief"),
                     "C3": ("met", "Neurological exam: strength 5/5, reflexes symmetric, sensation intact"),
                     "C4": ("met", "No prior spine imaging")},
    },
    "PA-002": {
        "member": "M-1002", "active": True, "outcome": "human_review",
        "notes": "Low back pain for 9 weeks. Physical therapy was recommended; patient declined and is taking no "
                 "medication. Neurological exam normal. No prior spine imaging.",
        "findings": {"C1": ("met", "Low back pain for 9 weeks"),
                     "C2": ("not_met", "Physical therapy was recommended; patient declined and is taking no medication"),
                     "C3": ("met", "Neurological exam normal"),
                     "C4": ("met", "No prior spine imaging")},
        "reason": "C2 not met: patient declined physical therapy and takes no medication",
    },
    "PA-003": {
        "member": "M-1003", "active": True, "outcome": "request_info",
        "notes": "Patient has back pain. Has been taking NSAIDs for a while. Neurological exam normal. "
                 "No prior spine imaging.",
        "findings": {"C1": ("unknown", "Notes say 'Patient has back pain' with no duration"),
                     "C2": ("unknown", "Notes say NSAIDs 'for a while' with no duration or response"),
                     "C3": ("met", "Neurological exam normal"),
                     "C4": ("met", "No prior spine imaging")},
        "items": ["duration of back pain", "duration of conservative therapy and response"],
    },
    "PA-004": {
        "member": "M-1004", "active": True, "outcome": "human_review",
        "notes": "Low back pain for 12 weeks. Completed 7 weeks of physical therapy without improvement. "
                 "Neurological exam normal. Lumbar MRI performed 4 months ago at an outside facility.",
        "findings": {"C1": ("met", "Low back pain for 12 weeks"),
                     "C2": ("met", "Completed 7 weeks of physical therapy without improvement"),
                     "C3": ("met", "Neurological exam normal"),
                     "C4": ("not_met", "Lumbar MRI performed 4 months ago at an outside facility")},
        "reason": "C4 not met: lumbar MRI 4 months ago",
    },
    "PA-005": {
        "member": "M-1005", "active": True, "outcome": "approve",
        "notes": "Back pain for 2 weeks with progressive left foot weakness over 5 days. Neurological exam: "
                 "left foot drop, 3/5 dorsiflexion. No prior spine imaging.",
        "findings": {"C1": ("waived", "Red flag: progressive left foot weakness over 5 days"),
                     "C2": ("waived", "Red flag: progressive left foot weakness over 5 days"),
                     "C3": ("met", "Neurological exam: left foot drop, 3/5 dorsiflexion"),
                     "C4": ("met", "No prior spine imaging")},
    },
    "PA-006": {
        "member": "M-1006", "active": True, "outcome": "approve",
        "notes": "Low back pain for 8 weeks. Completed 6 weeks of physical therapy plus muscle relaxants without "
                 "relief. Neurological exam: normal strength and reflexes. No prior spine imaging.",
        "findings": {"C1": ("met", "Low back pain for 8 weeks"),
                     "C2": ("met", "Completed 6 weeks of physical therapy plus muscle relaxants without relief"),
                     "C3": ("met", "Neurological exam: normal strength and reflexes"),
                     "C4": ("met", "No prior spine imaging")},
    },
    "PA-007": {
        "member": "M-1007", "active": True, "outcome": "human_review",
        "notes": "Low back pain for 10 weeks. Completed 7 weeks of physical therapy without relief. "
                 "No prior spine imaging.",
        "findings": {"C1": ("met", "Low back pain for 10 weeks"),
                     "C2": ("met", "Completed 7 weeks of physical therapy without relief"),
                     "C3": ("not_met", "The notes do not document a neurological exam"),
                     "C4": ("met", "No prior spine imaging")},
        "reason": "C3 not met: no neurological exam documented",
    },
    "PA-008": {
        "member": "M-1008", "active": False, "outcome": "human_review",
        "notes": "Low back pain for 11 weeks. Completed 8 weeks of physical therapy without relief. "
                 "Neurological exam normal. No prior spine imaging.",
        "findings": {"C1": ("met", "Low back pain for 11 weeks"),
                     "C2": ("met", "Completed 8 weeks of physical therapy without relief"),
                     "C3": ("met", "Neurological exam normal"),
                     "C4": ("met", "No prior spine imaging")},
        "reason": "Member coverage is not active on the date of service",
    },
}


# ------------------------------------------------------------------ building blocks
def call(tool, args, result=None, thought="", error=None):
    return {"kind": "tool_call", "thought": thought, "tool": tool, "args": args, "result": result, "error": error}


def message(text, thought=""):
    return {"kind": "message", "thought": thought, "content": text}


def req_step(case_id):
    c = CASES[case_id]
    return call("get_request", {"case_id": case_id},
                {"case_id": case_id, "member_id": c["member"], "procedure": "MRI lumbar spine without contrast",
                 "policy_id": "MP-117"}, "Read the request.")


def elig_step(case_id, member=None, active=None):
    c = CASES[case_id]
    member = member or c["member"]
    active = c["active"] if active is None else active
    res = {"member_id": member, "active": active}
    if not active:
        res["coverage_end"] = "2026-08-31"
    return call("check_eligibility", {"member_id": member}, res, "Confirm coverage is active on the date of service.")


def policy_step(policy=POLICY):
    return call("get_policy", {"policy_id": policy["policy_id"]}, policy, "Read the coverage policy.")


def notes_step(case_id, notes=None, args_case=None):
    return call("get_clinical_notes", {"case_id": args_case or case_id},
                {"case_id": args_case or case_id, "notes": notes or CASES[case_id]["notes"]},
                "Get the clinical notes for the case.")


def eval_step(cid, finding, evidence):
    return call("evaluate_criterion", {"criterion_id": cid, "finding": finding, "evidence": evidence},
                {"criterion_id": cid, "recorded": True}, f"Evaluate {cid} against the notes.")


def eval_steps(case_id, override=None):
    f = dict(CASES[case_id]["findings"])
    f.update(override or {})
    return [eval_step(cid, *f[cid]) for cid in ("C1", "C2", "C3", "C4")]


def terminal(case_id, outcome, why=None):
    c = CASES[case_id]
    if outcome in ("approve", "deny"):
        rationale = why or ("All criteria met." if outcome == "approve" else c.get("reason", ""))
        return call("record_determination", {"case_id": case_id, "decision": outcome, "rationale": rationale},
                    {"status": "recorded"}, "Record the determination.")
    if outcome == "request_info":
        return call("request_more_info", {"case_id": case_id, "items": c.get("items", why or [])},
                    {"status": "sent"}, "Ask the provider for the missing documentation.")
    return call("route_to_human", {"case_id": case_id, "reason": why or c.get("reason", "")},
                {"status": "queued"}, "Send the case to a clinical reviewer.")


def good(case_id):
    c = CASES[case_id]
    steps = [req_step(case_id), elig_step(case_id)]
    if not c["active"]:
        return steps + [terminal(case_id, "human_review")]
    return steps + [policy_step(), notes_step(case_id)] + eval_steps(case_id) + [terminal(case_id, c["outcome"])]


def trace(run_id, trace_id, case_id, steps, agent_version):
    steps = copy.deepcopy(steps)
    for i, s in enumerate(steps, 1):
        s["id"] = f"s{i}"
        steps[i - 1] = {"id": s.pop("id"), **s}
    return {"trace_id": trace_id, "run_id": run_id, "task_id": case_id, "agent_version": agent_version,
            "steps": steps}


# ------------------------------------------------------------------ planted failures
def _replace(steps, tool, new, match=None):
    out = []
    for s in steps:
        hit = s.get("tool") == tool and all(s["args"].get(k) == v for k, v in (match or {}).items())
        out.extend(new if hit else [s])
    return out


def _drop(steps, tool, match=None):
    return _replace(steps, tool, [], match)


def _terminal(steps, case_id, outcome, why=None):
    return [s for s in steps if s["tool"] not in ("record_determination", "route_to_human", "request_more_info")
            ] + [terminal(case_id, outcome, why)]


def planted():
    """(trace_id, case_id, root_cause, also_acceptable, steps)"""
    P = []
    # wrong_tool
    s = good("PA-004")
    s = _replace(s, "evaluate_criterion", [
        call("check_eligibility", {"member_id": "M-1004"}, {"member_id": "M-1004", "active": True},
             "Check the member's prior imaging history for C4."),
        eval_step("C4", "met", "No imaging history returned for the member")], {"criterion_id": "C4"})
    P.append(("E01", "PA-004", "wrong_tool", ["ungrounded_claim"], _terminal(s, "PA-004", "approve")))
    s = good("PA-001")
    s = _replace(s, "get_clinical_notes", [
        call("get_request", {"case_id": "PA-001"}, req_step("PA-001")["result"], "Get the clinical notes for the case.")])
    s = _replace(s, "evaluate_criterion", [])[:-1] + [
        eval_step(c, "unknown", "No clinical notes found in the case record") for c in ("C1", "C2", "C3", "C4")]
    s = s + [call("request_more_info", {"case_id": "PA-001", "items": ["clinical notes"]}, {"status": "sent"},
                  "Ask the provider for the missing documentation.")]
    P.append(("E02", "PA-001", "wrong_tool", [], s))
    # bad_tool_args
    s = good("PA-006")
    s = _replace(s, "get_policy", [policy_step(KNEE_POLICY)])
    s = _replace(s, "evaluate_criterion", [])[:-1] + [
        eval_step("K1", "met", "Low back pain for 8 weeks"),
        eval_step("K2", "met", "Completed 6 weeks of physical therapy"),
        eval_step("K3", "met", "Neurological exam: normal strength and reflexes"), terminal("PA-006", "approve")]
    P.append(("E03", "PA-006", "bad_tool_args", [], s))
    s = good("PA-002")
    s = _replace(s, "get_clinical_notes", [notes_step("PA-002", CASES["PA-001"]["notes"], args_case="PA-020")])
    s = _replace(s, "evaluate_criterion", [])[:-1] + eval_steps("PA-001") + [terminal("PA-002", "approve")]
    P.append(("E04", "PA-002", "bad_tool_args", ["ungrounded_claim"], s))
    s = good("PA-005")
    s = _replace(s, "check_eligibility", [elig_step("PA-005", member="M-1050", active=False)])
    s = s[:2] + [terminal("PA-005", "human_review", "Member coverage is not active on the date of service")]
    P.append(("E05", "PA-005", "bad_tool_args", [], s))
    # unhandled_tool_error
    s = good("PA-001")
    s = _replace(s, "get_clinical_notes", [call("get_clinical_notes", {"case_id": "PA-001"}, None,
                 "Get the clinical notes for the case.", "TimeoutError: EHR gateway did not respond within 30s")])
    s = _replace(s, "evaluate_criterion", [])[:-1] + [
        eval_step(c, "unknown", "Clinical notes unavailable") for c in ("C1", "C2", "C3", "C4")]
    s = s + [call("request_more_info", {"case_id": "PA-001", "items": ["clinical notes"]}, {"status": "sent"},
                  "Ask the provider for the missing documentation.")]
    P.append(("E06", "PA-001", "unhandled_tool_error", [], s))
    s = good("PA-006")
    s = _replace(s, "check_eligibility", [call("check_eligibility", {"member_id": "M-1006"}, None,
                 "Confirm coverage is active on the date of service.", "HTTP 503: eligibility service unavailable")])
    P.append(("E07", "PA-006", "unhandled_tool_error", [], s))
    # skipped_required_step
    P.append(("E08", "PA-006", "skipped_required_step", [], _drop(good("PA-006"), "check_eligibility")))
    s = _drop(good("PA-007"), "evaluate_criterion", {"criterion_id": "C3"})
    P.append(("E09", "PA-007", "skipped_required_step", [], _terminal(s, "PA-007", "approve")))
    # ungrounded_claim
    s = _replace(good("PA-002"), "evaluate_criterion",
                 [eval_step("C2", "met", "Completed 8 weeks of physical therapy without relief")], {"criterion_id": "C2"})
    P.append(("E10", "PA-002", "ungrounded_claim", [], _terminal(s, "PA-002", "approve")))
    s = good("PA-003")
    s = _replace(s, "evaluate_criterion", [eval_step("C1", "met", "Back pain for 8 weeks")], {"criterion_id": "C1"})
    s = _replace(s, "evaluate_criterion", [eval_step("C2", "met", "NSAIDs for 7 weeks without relief")],
                 {"criterion_id": "C2"})
    P.append(("E11", "PA-003", "ungrounded_claim", [], _terminal(s, "PA-003", "approve")))
    s = _replace(good("PA-007"), "evaluate_criterion",
                 [eval_step("C3", "met", "Neurological exam normal")], {"criterion_id": "C3"})
    P.append(("E12", "PA-007", "ungrounded_claim", [], _terminal(s, "PA-007", "approve")))
    # unsafe_action_without_approval
    P.append(("E13", "PA-002", "unsafe_action_without_approval", [], _terminal(good("PA-002"), "PA-002", "deny")))
    P.append(("E14", "PA-004", "unsafe_action_without_approval", [], _terminal(good("PA-004"), "PA-004", "deny")))
    # loop_or_step_cap
    page = {"case_id": "PA-005", "notes": CASES["PA-005"]["notes"][:60], "page": "1 of 2", "next_page_token": "p2"}
    s = good("PA-005")[:3] + [call("get_clinical_notes", {"case_id": "PA-005"}, page,
                                   "Get the clinical notes for the case.") for _ in range(17)]
    P.append(("E15", "PA-005", "loop_or_step_cap", [], s))
    s = good("PA-003")[:2] + [call("get_policy", {"policy_id": "MP-117"}, POLICY,
                                   "Re-read the policy to confirm the criteria.") for _ in range(18)]
    P.append(("E16", "PA-003", "loop_or_step_cap", [], s))
    # premature_stop
    s = good("PA-001")[:-1] + [message("All four criteria are met; this request should be approved.")]
    P.append(("E17", "PA-001", "premature_stop", [], s))
    s = good("PA-004")[:-1] + [message("C4 is not met because of the lumbar MRI 4 months ago. Stopping here.")]
    P.append(("E18", "PA-004", "premature_stop", [], s))
    # wrong_final_answer
    P.append(("E19", "PA-007", "wrong_final_answer", [], _terminal(good("PA-007"), "PA-007", "approve",
                                                                   "Criteria reviewed; approving.")))
    P.append(("E20", "PA-003", "wrong_final_answer", [],
              _terminal(good("PA-003"), "PA-003", "human_review", "C1 and C2 could not be determined")))
    return P


def eval_set():
    traces, labels = [], []
    for tid, case_id, root, also, steps in planted():
        traces.append(trace("eval-set", tid, case_id, steps, "synthetic"))
        labels.append({"trace_id": tid, "task_id": case_id, "expected_pass": False, "root_cause": root,
                       "also_acceptable": also})
    for i, case_id in enumerate(["PA-001", "PA-003", "PA-004", "PA-005", "PA-008"], 21):
        traces.append(trace("eval-set", f"E{i}", case_id, good(case_id), "synthetic"))
        labels.append({"trace_id": f"E{i}", "task_id": case_id, "expected_pass": True, "root_cause": None,
                       "also_acceptable": []})
    return traces, labels


def demo_runs():
    """v1.0: grounding miss on PA-002, no retry on a notes timeout on PA-005.
    v1.1: adds a retry on tool errors and a stricter evidence prompt; the shorter prompt drops the prior-imaging
    instruction, so PA-004 gets approved when it should go to a human."""
    v1 = {c: good(c) for c in CASES}
    v1["PA-002"] = dict(planted_by_id())["E10"]
    timeout = call("get_clinical_notes", {"case_id": "PA-005"}, None, "Get the clinical notes for the case.",
                   "TimeoutError: EHR gateway did not respond within 30s")
    s = _replace(good("PA-005"), "get_clinical_notes", [timeout])
    s = _replace(s, "evaluate_criterion", [])[:-1] + [
        eval_step(c, "unknown", "Clinical notes unavailable") for c in ("C1", "C2", "C3", "C4")]
    v1["PA-005"] = s + [call("request_more_info", {"case_id": "PA-005", "items": ["clinical notes"]},
                             {"status": "sent"}, "Ask the provider for the missing documentation.")]
    v2 = {c: good(c) for c in CASES}
    v2["PA-005"] = _replace(good("PA-005"), "get_clinical_notes", [
        timeout, {**notes_step("PA-005"), "thought": "Retry after the timeout."}])
    s = _replace(good("PA-004"), "evaluate_criterion",
                 [eval_step("C4", "met", "No prior lumbar imaging")], {"criterion_id": "C4"})
    v2["PA-004"] = _terminal(s, "PA-004", "approve")
    return ({c: trace("prior-auth-v1", c, c, st, "prior-auth-reviewer 1.0") for c, st in v1.items()},
            {c: trace("prior-auth-v2", c, c, st, "prior-auth-reviewer 1.1") for c, st in v2.items()})


def planted_by_id():
    return [(p[0], p[4]) for p in planted()]


def render() -> dict[str, str]:
    """Relative path -> file content for everything the generator owns."""
    files = {}
    traces, labels = eval_set()
    for t in traces:
        files[f"eval-set/{t['trace_id']}.json"] = json.dumps(t, indent=1) + "\n"
    files["eval-set/labels.yaml"] = (
        "# Planted root cause per trace (null = clean). also_acceptable: labels a careful reader could\n"
        "# reasonably name as root cause too; scored separately from exact matches.\n"
        + yaml.safe_dump({"suite_id": "prior-auth", "traces": labels}, sort_keys=False))
    v1, v2 = demo_runs()
    for name, run in (("prior-auth-v1", v1), ("prior-auth-v2", v2)):
        for c, t in run.items():
            files[f"{name}/{c}.json"] = json.dumps(t, indent=1) + "\n"
    return files


def write(root: Path) -> int:
    for rel, content in render().items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return len(render())


if __name__ == "__main__":
    from agent_evaluator import catalog
    print(f"wrote {write(catalog.TRACES)} files to {catalog.TRACES}")
