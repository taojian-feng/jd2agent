"""Mock health plan systems (claims, eligibility, policy store, health record gateway), served over MCP.

The reviewer agent reaches them only through MCP tool calls, the way it would reach real enterprise systems.
Faults can be injected per tool and case (timeouts, 503s) to exercise retries and escalation.
The claims system itself refuses denials: the no-deny rule is enforced at the system boundary, not only in the
agent's prompt.
"""
import os
from pathlib import Path

import yaml

try:  # MCP Python SDK 2.x
    from mcp.server.mcpserver import MCPServer as FastMCP
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # 1.x
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.exceptions import ToolError

# Systems raise ToolError: the MCP SDK passes its message to the client. Any other exception is reported by the
# SDK as a bare "Error executing tool" (2.x), and the client could not tell a timeout from a refusal.

DATA = Path(os.environ.get("PRIOR_AUTH_DATA", Path(__file__).resolve().parents[1] / "data"))
ERRORS = {"timeout": "TimeoutError: EHR gateway did not respond within 30s",
          "503": "HTTP 503: service unavailable"}
PROCEDURE = {"72148": "MRI lumbar spine without contrast"}

TRANSIENT_FAULTS = {  # one failure each; a retry succeeds
    "get_clinical_notes": {"PA-005": ["timeout"], "PA-010": ["503"]},
    "check_eligibility": {"PA-002": ["timeout"]},
}


def load_cases() -> dict[str, dict]:
    return {c["case_id"]: c for c in yaml.safe_load((DATA / "cases.yaml").read_text(encoding="utf-8"))["cases"]}


def load_policy_texts() -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted((DATA / "policies").glob("*.md"))}


class HealthPlanSystems:
    def __init__(self, faults: dict | None = None):
        self.cases = load_cases()
        self.policies = load_policy_texts()
        self.faults = {tool: {k: list(v) for k, v in by_case.items()} for tool, by_case in (faults or {}).items()}
        self.records: list[dict] = []
        self.addenda: dict[str, list[str]] = {}

    def _fault(self, tool: str, key: str) -> None:
        queue = self.faults.get(tool, {}).get(key)
        if queue:
            kind = queue[0] if queue[0] == "always" else queue.pop(0)
            raise ToolError(ERRORS.get(kind, ERRORS["timeout"] if kind == "always" else kind))

    def _case(self, case_id: str) -> dict:
        if case_id not in self.cases:
            raise ToolError(f"case {case_id} not found")
        return self.cases[case_id]

    # ---- claims system
    def get_request(self, case_id: str) -> dict:
        c = self._case(case_id)
        return {"case_id": case_id, "member_id": c["member_id"], "procedure_code": "72148",
                "procedure": PROCEDURE["72148"], "setting": "outpatient"}

    def check_eligibility(self, member_id: str, case_id: str = "") -> dict:
        self._fault("check_eligibility", case_id)
        c = next((c for c in self.cases.values() if c["member_id"] == member_id), None)
        if c is None:
            raise ToolError(f"member {member_id} not found")
        out = {"member_id": member_id, "active": bool(c["active"])}
        if not c["active"]:
            out["coverage_end"] = "2026-08-31"
        return out

    def evaluate_criterion(self, case_id: str, criterion_id: str, finding: str, evidence: str) -> dict:
        self._case(case_id)
        if finding not in ("met", "not_met", "unknown", "waived"):
            raise ToolError(f"finding must be met, not_met, unknown or waived, not {finding!r}")
        self.records.append({"case_id": case_id, "type": "criterion", "criterion_id": criterion_id, "finding": finding})
        return {"criterion_id": criterion_id, "recorded": True}

    def record_determination(self, case_id: str, decision: str, rationale: str, approved_by: str) -> dict:
        self._case(case_id)
        if decision != "approve":
            raise ToolError("the claims system accepts only 'approve' from the agent; route adverse cases "
                                  "to a clinical reviewer")
        if not approved_by:
            raise ToolError("an approval needs the identity of the person who confirmed it")
        self.records.append({"case_id": case_id, "type": "determination", "decision": decision,
                             "approved_by": approved_by})
        return {"status": "recorded"}

    def request_more_info(self, case_id: str, items: list[str]) -> dict:
        self._case(case_id)
        self.records.append({"case_id": case_id, "type": "request_info", "items": items})
        return {"status": "sent"}

    def route_to_human(self, case_id: str, reason: str) -> dict:
        self._case(case_id)
        self.records.append({"case_id": case_id, "type": "human_review", "reason": reason})
        return {"status": "queued"}

    # ---- policy store
    def list_policies(self) -> list[dict]:
        return [{"policy_id": pid, "title": t.splitlines()[0].split(": ", 1)[1]} for pid, t in self.policies.items()]

    def get_policy(self, policy_id: str) -> dict:
        if policy_id not in self.policies:
            raise ToolError(f"policy {policy_id} not found")
        return {"policy_id": policy_id, "markdown": self.policies[policy_id]}

    # ---- health record gateway
    def get_clinical_notes(self, case_id: str) -> dict:
        self._fault("get_clinical_notes", case_id)
        c = self._case(case_id)
        notes = " ".join(c["notes"].split())
        for a in self.addenda.get(case_id, []):
            notes += " " + a
        return {"case_id": case_id, "notes": notes}

    def add_addendum(self, case_id: str, text: str) -> None:
        """The provider uploads more documentation (used to resume a paused case)."""
        self.addenda.setdefault(case_id, []).append(" ".join(text.split()))


def build_server(systems: HealthPlanSystems) -> FastMCP:
    mcp = FastMCP("mock-health-plan-systems", instructions="Fictional claims, eligibility, policy and EHR systems.")
    for name in ("get_request", "check_eligibility", "evaluate_criterion", "record_determination",
                 "request_more_info", "route_to_human", "list_policies", "get_policy", "get_clinical_notes"):
        fn = getattr(systems, name)
        mcp.tool(name=name, description=(fn.__doc__ or name).strip())(fn)
    return mcp
