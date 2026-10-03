"""Planner tests. No model and no API key: the live traces are read from agent-evaluator/traces, and the memo uses
the evaluator's FakeLLM."""
import asyncio
import copy
import json
import os
import tempfile
import unittest

os.environ.setdefault("CUSTOMIZATION_PLANNER_RUNS", tempfile.mkdtemp(prefix="cp-runs-"))

from agent_evaluator.llm import FakeLLM, ValidationFailed  # noqa: E402
from prior_auth_reviewer.models import Proposal  # noqa: E402
from prior_auth_reviewer.reasoning import validate_proposal  # noqa: E402

from customization_planner import catalog, planner, prior_auth as pa, workflows as wf  # noqa: E402
from customization_planner.memo import draft_memo, validate_memo  # noqa: E402
from customization_planner.models import Memo  # noqa: E402

LIVE = wf.LIVE_RUNS


class ParseTests(unittest.TestCase):
    def test_findings_with_absence_and_red_flag(self):
        msg = ("Revised findings: C1 waived (N4): Foot drop; progressive.; C2 waived (N4): Same.; "
               "C3 met (N5): Exam documented.; C4 not_met (absence): No imaging history. Red flag: left foot drop")
        f, flag = pa.parse_findings(msg)
        self.assertEqual([(x.criterion_id, x.finding) for x in f],
                         [("C1", "waived"), ("C2", "waived"), ("C3", "met"), ("C4", "not_met")])
        self.assertEqual(f[0].rationale, "Foot drop; progressive.")   # a '; ' inside a rationale is kept
        self.assertEqual(f[3].sentence_ids, [])
        self.assertEqual(flag, "left foot drop")

    def test_critic_disputes(self):
        self.assertEqual(pa.disputed("Critic: C1 agree; C4 DISAGREE: too cautious"), ["C4"])


class LivePlanTests(unittest.TestCase):
    """The five recorded live runs of prior-auth-reviewer (real model output, identifiers masked)."""

    @classmethod
    def setUpClass(cls):
        cls.plan, cls.files = wf.run_plan(LIVE, plan_id="test-live", write=False)

    def test_grades_match_the_reviewer_readme(self):
        runs = self.plan.stats["runs"]
        self.assertEqual([runs[r]["passed"] for r in LIVE], [12, 12, 10, 12, 12])
        self.assertEqual([runs[r]["model_calls"] for r in LIVE], [11, 22, 22, 28, 30])
        self.assertEqual(self.plan.stats["safety_failures"], 0)

    def test_rebuilt_prompt_matches_every_traced_context(self):
        s = self.plan.stats
        self.assertEqual(s["context_rebuilt_matches_trace"], s["traces_with_a_proposal"])

    def test_failures_route_to_model_judgment_with_evidence_in_context(self):
        self.assertEqual({(r.task_id, r.route) for r in self.plan.routes},
                         {("PA-001", "model_judgment"), ("PA-006", "model_judgment")})
        self.assertTrue(all(c.evidence_in_context and c.verified == "met" and c.got == "unknown"
                            for c in self.plan.changes))

    def test_every_pair_and_example_passes_the_reviewer_validator(self):
        graded = {(r.run_id, r.task_id): t for r, t in planner.grade(LIVE, catalog.suite("prior-auth"),
                                                                       {x: catalog.run_traces(x) for x in LIVE})}
        for p in self.plan.pairs:
            policy, ctx = pa.policy_and_context(graded[(p.runs[0], p.task_id)])
            for text in (p.chosen, p.rejected):
                self.assertEqual(validate_proposal(Proposal.model_validate_json(text), policy, ctx), [])
            self.assertNotEqual(p.chosen, p.rejected)
        for e in self.plan.sft:
            policy, ctx = pa.policy_and_context(graded[(e.runs[0], e.task_id)])
            self.assertEqual(validate_proposal(Proposal.model_validate_json(e.completion), policy, ctx), [])

    def test_pairs_differ_exactly_on_the_changed_criterion(self):
        self.assertEqual(sorted((p.task_id, p.criteria) for p in self.plan.pairs),
                         [("PA-001", ["C4"]), ("PA-006", ["C4"])])
        for p in self.plan.pairs:
            chosen = {f["criterion_id"]: f["finding"] for f in json.loads(p.chosen)["findings"]}
            rejected = {f["criterion_id"]: f["finding"] for f in json.loads(p.rejected)["findings"]}
            self.assertEqual((chosen["C4"], rejected["C4"]), ("met", "unknown"))

    def test_split_has_no_leakage_and_covers_every_outcome(self):
        split = self.plan.split
        self.assertFalse(set(split["train"]) & set(split["eval"]))
        gates = {g.name: g for g in self.plan.gates}
        self.assertTrue(gates["every expected outcome held out"].passed)

    def test_verdict_not_ready_with_the_failing_gates_named(self):
        self.assertEqual(self.plan.verdict, "not_ready")
        failed = {g.name for g in self.plan.gates if not g.passed}
        self.assertIn("preference pairs (train)", failed)
        self.assertIn("Not ready to train", " ".join(self.plan.recommendation))
        self.assertIn("blocked", self.files["recipe.yaml"])

    def test_no_identifier_in_any_output(self):
        for name in ("sft.jsonl", "dpo.jsonl"):
            self.assertEqual(pa.unmasked_identifiers(self.files[name]), [], name)

    def test_lower_gates_make_it_ready(self):
        cfg = dict(catalog.routes()["readiness"], min_preference_pairs=1, min_sft_examples=1, min_distinct_tasks=1,
                   max_outcome_share=1.0)
        self.assertTrue(all(g.passed for g in planner.gates(self.plan.sft, self.plan.pairs, self.plan.split, cfg)))


class RoutingTests(unittest.TestCase):
    def test_safety_and_tool_failures_go_to_code_before_training(self):
        plan, _ = wf.run_plan(["prior-auth-v1", "prior-auth-v2"], write=False)
        self.assertEqual(plan.verdict, "fix_first")
        routes = {(r.run_id, r.task_id): r.route for r in plan.routes}
        self.assertEqual(routes[("prior-auth-v2", "PA-004")], "code_guardrail")   # approved a must-review case
        self.assertEqual(routes[("prior-auth-v1", "PA-005")], "workflow")         # tool error never retried
        self.assertIn("Fix in code first", plan.recommendation[0])

    def test_unmasked_identifier_drops_the_example(self):
        traces = {r: copy.deepcopy(catalog.run_traces(r)) for r in LIVE}
        for run in LIVE:          # a date leaks into every first proposal's first rationale
            for t in traces[run]:
                for s in t["steps"]:
                    if (s.get("content") or "").startswith("Proposed findings:"):
                        s["content"] = s["content"].replace("): ", "): Seen 2026-01-02. ", 1)
        plan = planner.make_plan("x", LIVE, catalog.suite("prior-auth"), traces, catalog.routes())
        self.assertGreater(plan.stats["dropped"].get("sft: unmasked identifier", 0), 0)
        self.assertEqual(pa.unmasked_identifiers(planner.jsonl(plan.sft) + planner.jsonl(plan.pairs)), [])


class MemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan, cls.files = wf.run_plan(LIVE, plan_id="test-memo", write=False)

    def test_rejects_a_number_not_in_the_plan(self):
        m = Memo(headline="Not yet.", body="We found 37 pairs.", numbers_used=["37"])
        self.assertTrue(any("37" in p for p in validate_memo(m, self.plan)))

    def test_rejects_ready_language_when_not_ready(self):
        m = Memo(headline="You are ready to fine-tune.", body="Go.", numbers_used=[])
        self.assertTrue(any("not_ready" in p for p in validate_memo(m, self.plan)))

    def test_retry_then_accept(self):
        bad = {"headline": "Not yet.", "body": "Only 99 pairs.", "numbers_used": ["99"]}
        good = {"headline": "Not yet: the runs support 2 preference pairs, and the gate asks for 100.",
                "body": "Keep the self-correction round. 6 decisions changed, all on C4.", "numbers_used": ["2", "100", "6", "4"]}
        llm = FakeLLM({"Memo": [bad, good]})
        memo = draft_memo(llm, self.plan, self.files["plan.md"])
        self.assertEqual(memo.headline, good["headline"])
        self.assertEqual(len(llm.calls), 2)
        self.assertIn("99", llm.calls[1][2])

    def test_gives_up_after_retries(self):
        llm = FakeLLM({"Memo": [{"headline": "x", "body": "42 pairs", "numbers_used": ["42"]}]})
        with self.assertRaises(ValidationFailed):
            draft_memo(llm, self.plan, self.files["plan.md"])


class ServerTests(unittest.TestCase):
    def test_lists_tools_resources_and_prompt(self):
        from customization_planner.server import mcp
        tools = {t.name for t in asyncio.run(mcp.list_tools())}
        self.assertEqual(tools, {"list_trace_runs", "grade_runs", "route_failures", "build_datasets", "check_readiness",
                                 "write_recipe", "plan_customization", "draft_partner_memo"})
        prompts = {p.name for p in asyncio.run(mcp.list_prompts())}
        self.assertEqual(prompts, {"plan_model_customization"})

    def test_plan_tool_writes_outputs(self):
        from customization_planner.server import plan_customization
        out = plan_customization(LIVE, plan_id="test-server")
        self.assertEqual(out["verdict"], "not_ready")
        self.assertIn("## Readiness gates", wf.load_output("test-server", "plan.md"))


if __name__ == "__main__":
    unittest.main()
