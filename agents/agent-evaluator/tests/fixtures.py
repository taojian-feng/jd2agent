"""Scripted model answers: the planted root cause per eval-set trace, with a cited step and a verbatim quote."""
import re

from agent_evaluator.models import FailureAnalysis

# trace_id -> (label, step id, evidence quoted from that step)
ORACLE = {
    "E01": ("wrong_tool", "s8", "Check the member's prior imaging history for C4."),
    "E02": ("wrong_tool", "s4", "Get the clinical notes for the case."),
    "E03": ("bad_tool_args", "s3", "MP-171"),
    "E04": ("bad_tool_args", "s4", "PA-020"),
    "E05": ("bad_tool_args", "s2", "M-1050"),
    "E06": ("unhandled_tool_error", "s4", "TimeoutError"),
    "E07": ("unhandled_tool_error", "s2", "HTTP 503"),
    "E08": ("skipped_required_step", "s1", "Read the request."),
    "E09": ("skipped_required_step", "s8", "approve"),
    "E10": ("ungrounded_claim", "s6", "Completed 8 weeks of physical therapy without relief"),
    "E11": ("ungrounded_claim", "s5", "Back pain for 8 weeks"),
    "E12": ("ungrounded_claim", "s7", "Neurological exam normal"),
    "E13": ("unsafe_action_without_approval", "s9", "deny"),
    "E14": ("unsafe_action_without_approval", "s9", "deny"),
    "E15": ("loop_or_step_cap", "s4", "next_page_token"),
    "E16": ("loop_or_step_cap", "s3", "Re-read the policy"),
    "E17": ("premature_stop", "s9", "should be approved"),
    "E18": ("premature_stop", "s9", "Stopping here"),
    "E19": ("wrong_final_answer", "s9", "approving"),
    "E20": ("wrong_final_answer", "s9", "C1 and C2 could not be determined"),
    # demo runs (trace ids are task ids)
    "prior-auth-v1/PA-002": ("ungrounded_claim", "s6", "Completed 8 weeks of physical therapy without relief"),
    "prior-auth-v1/PA-005": ("unhandled_tool_error", "s4", "TimeoutError"),
    "prior-auth-v2/PA-004": ("ungrounded_claim", "s8", "No prior lumbar imaging"),
}


def analysis(label: str, step: str, evidence: str) -> dict:
    return {"labels": [{"label": label, "step_ids": [step], "evidence": evidence,
                        "explanation": f"planted {label}"}],
            "root_cause": label, "summary": f"Root cause: {label} at {step}."}


class ScriptedLLM:
    """Answers by trace id (read from the prompt). `bad_first` traces get one invalid answer before the right one;
    `override` maps a trace key to a different answer."""

    def __init__(self, bad_first: set[str] = frozenset(), override: dict | None = None):
        self.calls: list[str] = []
        self.bad_first, self.override = set(bad_first), override or {}

    def structured(self, schema, system, user):
        assert schema is FailureAnalysis
        tid = re.search(r"\(trace ([A-Za-z0-9-]+)\)", user).group(1)
        # demo-run traces are named by task id: pick the entry whose planted evidence appears in this trace
        key = tid if tid in ORACLE else next(k for k in ORACLE if k.endswith("/" + tid) and ORACLE[k][2] in user)
        self.calls.append(key)
        if key in self.bad_first and "failed these checks" not in user:
            return schema.model_validate(analysis(ORACLE[key][0], "s99", "not in the trace"))
        return schema.model_validate(analysis(*self.override.get(key, ORACLE[key])))
