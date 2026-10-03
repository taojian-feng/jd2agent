"""Runs with the standard library:  python -m unittest discover -s tests -t ."""
import asyncio
import json
import os
import re
import tempfile
import unittest

os.environ.setdefault("PRIOR_AUTH_RUNS", tempfile.mkdtemp(prefix="prior-auth-runs-"))

import yaml  # noqa: E402

from prior_auth_reviewer import context as cx  # noqa: E402
from prior_auth_reviewer import reasoning as rs  # noqa: E402
from prior_auth_reviewer import retrieval as rt  # noqa: E402
from prior_auth_reviewer import workflows as wf  # noqa: E402
from prior_auth_reviewer.client import SystemsClient, ToolFailed, connect  # noqa: E402
from prior_auth_reviewer.llm import ValidationFailed, set_llm  # noqa: E402
from prior_auth_reviewer.models import Critique, Proposal  # noqa: E402
from prior_auth_reviewer.systems import DATA, TRANSIENT_FAULTS, HealthPlanSystems, build_server, load_cases  # noqa: E402
from prior_auth_reviewer.trace import Recorder  # noqa: E402
from tests.fixtures import ScriptedLLM, proposal  # noqa: E402

NO_SLEEP = lambda s: asyncio.sleep(0)  # noqa: E731
SYSTEMS = HealthPlanSystems()
LIB = wf.library_from(SYSTEMS)
MP117 = LIB.docs["MP-117"]


def suite(**kw):
    kw.setdefault("llm", ScriptedLLM())
    kw.setdefault("store", wf.CaseStore(wf.runs_dir() / f"cases-{id(kw)}"))
    return asyncio.run(wf.run_suite("test", sleep=NO_SLEEP, **kw))


class Retrieval(unittest.TestCase):
    def test_structure_aware_chunks(self):
        ids = [c.id for c in MP117.chunks]
        self.assertEqual([i for i in ids if i.split("#")[1].startswith("C")], ["MP-117#C1", "MP-117#C2",
                                                                              "MP-117#C3", "MP-117#C4"])
        self.assertIn("MP-117#RF", ids)
        self.assertEqual(MP117.waives(), ["C1", "C2"])
        self.assertEqual(MP117.codes, ["72148", "72149", "72158"])

    def test_quality_floor(self):
        q = yaml.safe_load((DATA / "retrieval_eval.yaml").read_text())["queries"]
        m = rt.evaluate_retrieval(LIB, q)
        self.assertEqual(m["rerank"]["policy"]["recall@1"], 1.0)     # routing must be exact
        self.assertEqual(m["rerank"]["clause"]["recall@3"], 1.0)
        self.assertGreaterEqual(m["rerank"]["clause"]["mrr"], m["bm25"]["clause"]["mrr"])
        self.assertGreater(m["rerank"]["policy"]["mrr"], m["hybrid"]["policy"]["mrr"])  # the reranker earns its place

    def test_routing_prefers_lumbar_mri_over_lumbar_ct(self):
        self.assertEqual(LIB.search_policies("MRI lumbar spine without contrast 72148")[0][0], "MP-117")
        self.assertEqual(LIB.search_policies("CT lumbar spine 72131")[0][0], "MP-119")


class Context(unittest.TestCase):
    def test_masking(self):
        text, n = cx.mask("Member M-1001. DOB 1968-03-14. Ordering clinician: Avery Rivera, NP. Pain.")
        self.assertEqual(n, 3)
        self.assertNotIn("M-1001", text)
        self.assertNotIn("Avery", text)
        self.assertNotIn("1968", text)

    def test_gold_evidence_kept_noise_dropped(self):
        kept = total = 0
        for c in load_cases().values():
            ctx = cx.assemble(c["notes"], MP117)
            k, t = cx.gold_retention(ctx, c["gold"])
            kept, total = kept + k, total + t
        self.assertEqual(kept, total)
        ctx = cx.assemble(load_cases()["PA-001"]["notes"], MP117)
        self.assertNotIn("Blood pressure 128/82.", ctx.text())

    def test_omissions_are_stated(self):
        text = cx.assemble(load_cases()["PA-007"]["notes"], MP117).text()
        self.assertIn("Not shown: N1, N2 (identifier line only)", text)
        self.assertIn("Every other sentence of the note is shown above.", text)

    def test_sentence_ids_are_stable(self):
        ctx = cx.assemble(load_cases()["PA-004"]["notes"], MP117)
        allsent = dict(cx.sentences(cx.mask(load_cases()["PA-004"]["notes"])[0]))
        for sid, s in ctx.kept:
            self.assertEqual(allsent[sid], s)


class Integration(unittest.IsolatedAsyncioTestCase):
    async def test_retry_then_success_and_trace(self):
        systems = HealthPlanSystems({"get_clinical_notes": {"PA-001": ["timeout"]}})
        async with connect(build_server(systems)) as s:
            rec = Recorder("r", "PA-001", "t")
            notes = await SystemsClient(s, rec, sleep=NO_SLEEP).call(
                "get_clinical_notes", {"case_id": "PA-001"}, "notes", redact=wf._redact_notes)
        self.assertIn("10 weeks", notes["notes"])
        self.assertEqual([x["error"] is None for x in rec.steps], [False, True])
        self.assertNotIn("M-1001", json.dumps(rec.steps), "identifiers are masked in the trace")

    async def test_persistent_outage_fails_typed(self):
        systems = HealthPlanSystems({"get_clinical_notes": {"PA-001": ["always"]}})
        async with connect(build_server(systems)) as s:
            with self.assertRaises(ToolFailed) as e:
                await SystemsClient(s, Recorder("r", "PA-001", "t"), sleep=NO_SLEEP).call(
                    "get_clinical_notes", {"case_id": "PA-001"}, "notes")
        self.assertEqual(e.exception.attempts, 3)

    async def test_system_refuses_denial(self):
        async with connect(build_server(HealthPlanSystems())) as s:
            with self.assertRaises(ToolFailed) as e:
                await SystemsClient(s, Recorder("r", "PA-002", "t"), sleep=NO_SLEEP).call(
                    "record_determination", {"case_id": "PA-002", "decision": "deny", "rationale": "x",
                                             "approved_by": "nurse"}, "deny")
        self.assertEqual(e.exception.attempts, 1, "not retryable")


class Reasoning(unittest.TestCase):
    def ctx(self, cid="PA-001"):
        return cx.assemble(load_cases()[cid]["notes"], MP117)

    def test_validator_accepts_oracle(self):
        ctx = self.ctx()
        p = Proposal.model_validate(proposal("PA-001", ctx.text()))
        self.assertEqual(rs.validate_proposal(p, MP117, ctx), [])

    def test_validator_rejects(self):
        ctx = self.ctx()
        p = proposal("PA-001", ctx.text())
        p["findings"][0]["sentence_ids"] = ["N99"]
        p["findings"][1]["clause_id"] = "MP-118#N2"
        p["findings"][2].update(finding="waived", clause_id="MP-117#RF")
        p["findings"][3]["sentence_ids"] = []
        problems = rs.validate_proposal(Proposal.model_validate(p), MP117, ctx)
        text = " | ".join(problems)
        for expected in ("N99", "cite clause MP-117#C2", "C3 cannot be waived", "red_flag is empty",
                         "C4: a 'met' finding must cite"):
            self.assertIn(expected, text)

    def test_judge_never_denies(self):
        p = Proposal.model_validate(proposal("PA-002", self.ctx("PA-002").text()))
        d = rs.judge(True, p, None, MP117)
        self.assertEqual(d.outcome, "human_review")
        crit = Critique.model_validate({"verdicts": [{"criterion_id": c, "agree": c != "C3", "problem": "x"}
                                                     for c in ("C1", "C2", "C3", "C4")]})
        p1 = Proposal.model_validate(proposal("PA-001", self.ctx().text()))
        self.assertEqual(rs.judge(True, p1, crit, MP117).outcome, "human_review")
        self.assertEqual(rs.judge(True, p1, None, MP117).outcome, "approve")
        self.assertEqual(rs.judge(False, p1, None, MP117).outcome, "human_review")


class Workflow(unittest.TestCase):
    def test_suite_all_correct_with_faults(self):
        out = suite(faults=TRANSIENT_FAULTS)
        self.assertEqual(out["accuracy"], 1.0, [r for r in out["rows"] if not r["correct"]])
        self.assertEqual(out["unsafe_approvals"], [])
        self.assertEqual(out["llm_calls"], 22)  # 11 eligible cases x (proposer + critic)
        decisions = [r for r in out["records"] if r["type"] == "determination"]
        self.assertTrue(all(r["approved_by"] for r in decisions))

    def test_critic_catches_a_wrong_approval(self):
        llm = ScriptedLLM(override={"PA-004": {"C4": "met"}}, disagree={"PA-004": "C4"})
        out = suite(llm=llm, case_ids=["PA-004"])
        self.assertEqual(out["rows"][0]["outcome"], "human_review")
        self.assertIn("Critic disagreed on C4", out["rows"][0]["reason"])

    def test_self_correction_after_critic_objection(self):
        llm = ScriptedLLM(cautious={"PA-001": {"C4": "unknown"}})
        out = suite(llm=llm, case_ids=["PA-001"])
        self.assertEqual(out["rows"][0]["outcome"], "approve")
        self.assertEqual([c[0] for c in llm.calls], ["Proposal", "Critique", "Proposal", "Critique"])
        steps = [s.get("content", "")[:16] for s in out["traces"]["PA-001"].steps if s["kind"] == "message"]
        self.assertIn("Revised findings", steps)

    def test_disagreement_that_survives_revision_goes_to_a_nurse(self):
        llm = ScriptedLLM(override={"PA-004": {"C4": "met"}}, disagree={"PA-004": "C4"})
        out = suite(llm=llm, case_ids=["PA-004"])
        self.assertEqual(out["rows"][0]["outcome"], "human_review")
        self.assertEqual(len(llm.calls), 4, "one revision round, then stop")

    def test_without_critic_the_same_mistake_is_approved(self):
        llm = ScriptedLLM(override={"PA-004": {"C4": "met"}})
        out = suite(llm=llm, case_ids=["PA-004"], critic=False)
        self.assertEqual(out["unsafe_approvals"], ["PA-004"])

    def test_bad_citation_is_retried(self):
        llm = ScriptedLLM(bad_first={"PA-006"})
        out = suite(llm=llm, case_ids=["PA-006"])
        self.assertEqual(out["rows"][0]["outcome"], "approve")
        self.assertEqual([c for c in llm.calls if c[0] == "Proposal"], [("Proposal", "PA-006")] * 2)

    def test_notes_outage_escalates(self):
        out = suite(case_ids=["PA-001"], faults={"get_clinical_notes": {"PA-001": ["always"]}})
        self.assertEqual(out["rows"][0]["outcome"], "human_review")
        self.assertIn("Clinical notes unavailable after 3 attempts", out["rows"][0]["reason"])

    def test_declined_approval_goes_to_a_nurse(self):
        async def nobody(cid, decision):
            return None
        out = suite(case_ids=["PA-001"], approver=nobody)
        self.assertEqual(out["rows"][0]["outcome"], "human_review")

    def test_memory_resume_after_documentation(self):
        store = wf.CaseStore(wf.runs_dir() / "cases-resume")
        out = suite(case_ids=["PA-003"], store=store)
        self.assertEqual(out["rows"][0]["outcome"], "request_info")
        self.assertNotIn("notes", json.dumps(store.load("PA-003")).lower().replace("from the notes", ""))
        systems = HealthPlanSystems()
        systems.add_addendum("PA-003", "Back pain for 9 weeks. Took naproxen daily for 7 weeks without relief.")
        llm = ScriptedLLM(override={"PA-003": {"C1": "met", "C2": "met"}})
        prompts = []
        llm_inner = llm.structured
        llm.structured = lambda schema, system, user: (prompts.append(user), llm_inner(schema, system, user))[1]
        out = suite(case_ids=["PA-003"], store=store, systems=systems, memory=True, llm=llm)
        self.assertEqual(out["rows"][0]["outcome"], "approve")
        self.assertIn("Earlier review of this case (outcome request_info", prompts[0])
        self.assertEqual([h["outcome"] for h in store.load("PA-003")["history"]], ["request_info", "approve"])

    def test_traces_hold_no_identifiers(self):
        out = suite(faults=TRANSIENT_FAULTS)
        blob = json.dumps([r.to_dict() for r in out["traces"].values()])
        for c in load_cases().values():
            self.assertNotIn(c["member_id"], blob)
        for c in load_cases().values():  # birth dates
            dob = re.search(r"DOB (\d{4}-\d\d-\d\d)", c["notes"]).group(1)
            self.assertNotIn(dob, blob)
        for name in ("Avery Rivera", "Jordan Blake", "Sam Okafor"):
            self.assertNotIn(name, blob)

    def test_traces_pass_the_evaluator_code_check(self):
        import sys
        sys.path.append(str(DATA.parents[1] / "agent-evaluator"))
        try:
            from agent_evaluator import catalog
            from agent_evaluator.tools import deterministic as d
        except ImportError:
            self.skipTest("agent-evaluator not next to this agent")
        out = suite(faults=TRANSIENT_FAULTS)
        spec = catalog.suite("prior-auth")
        for cid, rec in out["traces"].items():
            c = d.check_task_success(d.load_trajectory(rec.to_dict()), spec)
            self.assertTrue(c.passed, (cid, c.symptoms))

    def test_langgraph_engine_matches(self):
        try:
            from prior_auth_reviewer import graphs  # noqa: F401
        except ImportError:
            self.skipTest("langgraph not installed")
        out = suite(case_ids=["PA-005", "PA-008"], faults=TRANSIENT_FAULTS)
        self.assertEqual([r["outcome"] for r in out["rows"]], ["approve", "human_review"])


class McpServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        set_llm(ScriptedLLM())

    async def asyncTearDown(self):
        set_llm(None)

    async def test_surface_and_review(self):
        from prior_auth_reviewer.server import mcp
        async with connect(mcp) as client:
            tools = {t.name for t in (await client.list_tools()).tools}
            self.assertEqual(tools, {"search_policies", "search_clauses", "retrieval_quality", "review_case",
                                     "resume_case"})
            r = await client.call_tool("search_clauses", {"query": "conservative therapy before lumbar MRI", "k": 1})
            self.assertIn("MP-117#C2", json.dumps(structured(r)))
            r = await client.call_tool("review_case", {"case_id": "PA-001"})
            self.assertEqual(structured(r)["result"]["outcome"], "human_review", "no approver: goes to a nurse")
            r = await client.call_tool("review_case", {"case_id": "PA-001", "auto_approve_demo": True})
            self.assertEqual(structured(r)["result"]["outcome"], "approve")
            res = await client.read_resource("case://cases/PA-001")
            self.assertIn('"outcome": "approve"', res.contents[0].text)


def structured(result):
    return getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)


if __name__ == "__main__":
    unittest.main()
