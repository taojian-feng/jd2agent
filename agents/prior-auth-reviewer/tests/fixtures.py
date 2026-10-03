"""Scripted model: answers the proposer and critic from the expected findings per case (no API calls)."""
import re

from prior_auth_reviewer.models import Critique, Proposal
from prior_auth_reviewer.systems import load_cases

CASES = load_cases()
EXPECTED = {  # criterion -> finding; anything not listed is "met"
    "PA-002": {"C2": "not_met"}, "PA-003": {"C1": "unknown", "C2": "unknown"}, "PA-004": {"C4": "not_met"},
    "PA-005": {"C1": "waived", "C2": "waived"}, "PA-007": {"C3": "not_met"},
    "PA-011": {"C1": "waived", "C2": "waived"}, "PA-012": {"C1": "not_met", "C2": "not_met"},
}
RED_FLAG = {"PA-005": "progressive left foot weakness", "PA-011": "History of breast cancer"}


def which_case(prompt: str) -> str:
    """The case whose gold evidence phrases best match the prompt (C1's phrase breaks ties)."""
    def score(c):
        phrases = [p for ps in c["gold"].values() for p in ps]
        return (sum(p in prompt for p in phrases), bool(c["gold"]["C1"]) and c["gold"]["C1"][0] in prompt)
    best = max(CASES, key=lambda cid: score(CASES[cid]))
    if score(CASES[best])[0] == 0:
        raise AssertionError("case not recognized from the prompt")
    return best


def sentence_ids(prompt: str) -> dict[str, str]:
    return dict(re.findall(r"^(N\d+): (.+)$", prompt, re.M))


def proposal(cid: str, prompt: str, override: dict | None = None) -> dict:
    sents = sentence_ids(prompt)
    findings = []
    for crit in ("C1", "C2", "C3", "C4"):
        f = (override or {}).get(crit) or EXPECTED.get(cid, {}).get(crit, "met")
        gold = CASES[cid]["gold"][crit]
        ids = [sid for sid, text in sents.items() if gold and gold[0].lower() in text.lower()]
        if not ids and f == "met":  # e.g. resumed case: the new documentation carries the evidence
            ids = [sid for sid, text in sents.items() if "weeks" in text][:1]
        findings.append({"criterion_id": crit, "finding": f,
                         "clause_id": "MP-117#RF" if f == "waived" else f"MP-117#{crit}",
                         "sentence_ids": ids if f != "unknown" else ids[:1], "rationale": f"{crit} {f}"})
    return {"findings": findings, "red_flag": RED_FLAG.get(cid, "")}


class ScriptedLLM:
    """override: {case_id: {criterion: finding}} to plant a wrong proposal; disagree: {case_id: criterion} for the
    critic; bad_first: case ids whose first proposal cites a sentence that does not exist."""

    def __init__(self, override=None, disagree=None, bad_first=(), cautious=None):
        """cautious: {case_id: {criterion: finding}} for the first proposal only; the critic objects to it, and the
        revised proposal (after feedback) is correct."""
        self.override, self.disagree, self.bad_first = override or {}, disagree or {}, set(bad_first)
        self.cautious = cautious or {}
        self.calls: list[tuple[str, str]] = []

    def structured(self, schema, system, user):
        cid = which_case(user)
        self.calls.append((schema.__name__, cid))
        if schema is Proposal:
            first = "A second reviewer checked" not in user
            p = proposal(cid, user, self.override.get(cid) or (self.cautious.get(cid) if first else None))
            if cid in self.bad_first and "failed these checks" not in user:
                p["findings"][0]["sentence_ids"] = ["N99"]
            return Proposal.model_validate(p)
        crit = self.disagree.get(cid)
        for c, v in self.cautious.get(cid, {}).items():
            if f"{c} -> {v}" in user:
                crit = c
        return Critique.model_validate({"verdicts": [
            {"criterion_id": c, "agree": c != crit, "problem": "" if c != crit else "evidence does not support it"}
            for c in ("C1", "C2", "C3", "C4")]})
