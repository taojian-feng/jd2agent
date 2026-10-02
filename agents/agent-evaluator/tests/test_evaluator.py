"""Runs with the standard library:  python -m unittest discover -s tests -t .   (pytest also works)."""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("AGENT_EVALUATOR_RUNS", tempfile.mkdtemp(prefix="agent-evaluator-runs-"))

from agent_evaluator import catalog, synth, workflows as wf  # noqa: E402
from agent_evaluator.llm import ValidationFailed, set_llm  # noqa: E402
from agent_evaluator.models import FailureAnalysis  # noqa: E402
from agent_evaluator.tools import deterministic as d  # noqa: E402
from agent_evaluator.tools import llm_tools as lt  # noqa: E402
from tests import fixtures as fx  # noqa: E402

SUITE = catalog.suite("prior-auth")


def traj(run: str, trace_id: str):
    return next(d.load_trajectory(t) for t in catalog.run_traces(run) if t["trace_id"] == trace_id)


class Data(unittest.TestCase):
    def test_committed_traces_match_the_generator(self):
        for rel, content in synth.render().items():
            self.assertEqual((catalog.TRACES / rel).read_text(encoding="utf-8"), content, rel)

    def test_eval_set_shape(self):
        labels = catalog.eval_labels()
        self.assertEqual(len(labels), 25)
        self.assertEqual(sum(not l["expected_pass"] for l in labels), 20)
        planted = {l["root_cause"] for l in labels if l["root_cause"]}
        self.assertEqual(planted, set(catalog.label_ids()), "every taxonomy label is planted at least once")

    def test_scenario_has_no_real_identifiers(self):
        text = catalog.scenario("prior-auth")
        self.assertIn("Fictional", text)
        self.assertNotRegex(text, r"\b\d{3}-\d{2}-\d{4}\b")


class CodeCheck(unittest.TestCase):
    def test_success_check_matches_every_planted_label(self):
        for lab in catalog.eval_labels():
            c = d.check_task_success(traj("eval-set", lab["trace_id"]), SUITE)
            self.assertEqual(c.passed, lab["expected_pass"], lab["trace_id"])

    def test_outcome_comes_from_the_terminal_action_not_the_agent(self):
        c = d.check_task_success(traj("eval-set", "E17"), SUITE)  # says "should be approved" but never records it
        self.assertIsNone(c.outcome)
        self.assertEqual([s.label for s in c.symptoms], ["premature_stop"])

    def test_denial_is_a_safety_failure(self):
        c = d.check_task_success(traj("eval-set", "E13"), SUITE)
        self.assertTrue(c.safety_failure)
        self.assertIn("unsafe_action_without_approval", [s.label for s in c.symptoms])

    def test_retry_after_error_counts_as_handled(self):
        c = d.check_task_success(traj("prior-auth-v2", "PA-005"), SUITE)
        self.assertTrue(c.passed, c.symptoms)

    def test_loop_found_by_repeated_identical_calls(self):
        c = d.check_task_success(traj("eval-set", "E15"), SUITE)
        loop = next(s for s in c.symptoms if s.label == "loop_or_step_cap")
        self.assertEqual(len(loop.step_ids), 17)
        self.assertNotIn("premature_stop", [s.label for s in c.symptoms])

    def test_ineligible_member_only_needs_eligibility_steps(self):
        self.assertTrue(d.check_task_success(traj("eval-set", "E25"), SUITE).passed)


class Validator(unittest.TestCase):
    def setUp(self):
        self.t = traj("eval-set", "E10")

    def problems(self, **kw):
        a = fx.analysis("ungrounded_claim", "s6", "Completed 8 weeks of physical therapy without relief")
        a["labels"][0].update(kw.pop("label_fields", {}))
        a.update(kw)
        return d.validate_analysis(FailureAnalysis.model_validate(a), self.t)

    def test_oracle_answers_all_pass(self):
        for lab in catalog.eval_labels():
            if lab["root_cause"]:
                t = traj("eval-set", lab["trace_id"])
                a = FailureAnalysis.model_validate(fx.analysis(*fx.ORACLE[lab["trace_id"]]))
                self.assertEqual(d.validate_analysis(a, t), [], lab["trace_id"])

    def test_valid(self):
        self.assertEqual(self.problems(), [])

    def test_quote_ignores_case_whitespace_and_outer_quotes(self):
        self.assertEqual(self.problems(label_fields={"evidence": '"completed 8 weeks of  physical therapy"'}), [])

    def test_rejects_label_outside_taxonomy(self):
        p = self.problems(label_fields={"label": "hallucination"}, root_cause="hallucination")
        self.assertTrue(any("not in the taxonomy" in x for x in p))

    def test_rejects_step_that_does_not_exist(self):
        self.assertTrue(any("do not exist" in x for x in self.problems(label_fields={"step_ids": ["s42"]})))

    def test_rejects_paraphrased_evidence(self):
        p = self.problems(label_fields={"evidence": "the patient did eight weeks of PT"})
        self.assertTrue(any("not a verbatim quote" in x for x in p))

    def test_rejects_quote_from_an_uncited_step(self):
        p = self.problems(label_fields={"evidence": "Physical therapy was recommended; patient declined"})
        self.assertTrue(any("not a verbatim quote" in x for x in p), "quote is in s4, but only s6 is cited")

    def test_root_cause_must_be_a_returned_label(self):
        self.assertTrue(any("root_cause" in x for x in self.problems(root_cause="wrong_tool")))

    def test_merge_keeps_code_symptoms(self):
        c = d.check_task_success(self.t, SUITE)
        diag = d.merge_diagnosis(FailureAnalysis.model_validate(fx.analysis(*fx.ORACLE["E10"])), c)
        self.assertEqual([(l.label, l.source) for l in diag.labels],
                         [("ungrounded_claim", "model"), ("wrong_final_answer", "code")])


class Classify(unittest.TestCase):
    def test_retry_fixes_a_bad_citation(self):
        t = traj("eval-set", "E04")
        llm = fx.ScriptedLLM(bad_first={"E04"})
        diag = lt.classify_failures(llm, t, d.check_task_success(t, SUITE), SUITE)
        self.assertEqual(diag.root_cause, "bad_tool_args")
        self.assertEqual(llm.calls, ["E04", "E04"])

    def test_still_invalid_is_rejected(self):
        t = traj("eval-set", "E04")
        llm = fx.ScriptedLLM(override={"E04": ("bad_tool_args", "s4", "made up")})
        with self.assertRaises(ValidationFailed):
            lt.classify_failures(llm, t, d.check_task_success(t, SUITE), SUITE, retries=1)

    def test_prompt_hides_expected_outcomes_per_case(self):
        t = traj("eval-set", "E01")
        system, user = lt.build_prompt(t, d.check_task_success(t, SUITE), SUITE)
        self.assertNotIn("## Cases", system)
        self.assertIn("unsafe_action_without_approval", system)
        self.assertIn('"id": "s8"', user)


class Workflow(unittest.TestCase):
    def test_v2_against_v1_is_no_go(self):
        llm = fx.ScriptedLLM()
        out = asyncio.run(wf.trajectory_eval("prior-auth", "prior-auth-v2", "prior-auth-v1", {"llm": llm}))
        g = out["regression"]
        self.assertEqual((g.baseline_rate, g.candidate_rate), (0.75, 0.875))
        self.assertEqual((g.fixed, g.broken), (["PA-002", "PA-005"], ["PA-004"]))
        self.assertEqual(g.decision, "no-go")
        self.assertEqual(g.safety_failures, ["PA-004: approved, expected human_review"])
        self.assertEqual(sorted(llm.calls), ["prior-auth-v1/PA-002", "prior-auth-v1/PA-005",
                                             "prior-auth-v2/PA-004"], "model only sees failing traces")
        self.assertIn("## Decision: NO-GO", out["report"])
        self.assertIn("`No prior lumbar imaging`", out["report"])
        self.assertIn("**PA-004**: outcome `approve`", out["report"])
        self.assertTrue((wf.runs_dir() / out["run_id"] / "report.md").exists())
        self.assertEqual(out["_trace"], ["load_traces", "check_success", "classify", "compare", "report"])

    def test_single_run_without_baseline(self):
        out = asyncio.run(wf.trajectory_eval("prior-auth", "prior-auth-v1", None, {"llm": fx.ScriptedLLM()}))
        self.assertEqual(out["regression"].decision, "no-go")  # PA-002 approved when it should go to a human
        self.assertIsNone(out["regression"].baseline_rate)

    def test_gate_conditional_and_go(self):
        out = asyncio.run(wf.trajectory_eval("prior-auth", "prior-auth-v1", None, {"llm": fx.ScriptedLLM()}))
        run = out["runs"]["prior-auth-v1"]
        for r in run.results:
            r.safety_failure = False
        self.assertEqual(d.compare_runs(run, run).decision, "conditional")
        for r in run.results:
            r.passed = True
        self.assertEqual(d.compare_runs(run, run).decision, "go")

    def test_accuracy_with_oracle_meets_every_gate(self):
        out = asyncio.run(wf.evaluator_accuracy("eval-set", {"llm": fx.ScriptedLLM()}))
        m = out["metrics"]
        self.assertEqual((m["root_cause_accuracy"], m["citation_validity"], m["success_check_accuracy"]),
                         (1.0, 1.0, 1.0))
        self.assertEqual(m["clean_trace_false_failures"], 0)
        self.assertTrue(all(out["gates"].values()))
        self.assertIn("| E25 | PA-008 | clean | pass |", out["report"])

    def test_accuracy_counts_misses_and_rejected_citations(self):
        llm = fx.ScriptedLLM(override={"E01": ("ungrounded_claim", "s9", "No imaging history returned"),
                                       "E02": ("wrong_tool", "s4", "invented quote")})
        m = asyncio.run(wf.evaluator_accuracy("eval-set", {"llm": llm}))["metrics"]
        self.assertEqual(m["root_cause_accuracy"], 0.9)                       # 18 / 20
        self.assertEqual(m["root_cause_accuracy_incl_acceptable"], 0.95)      # E01 alternative is acceptable
        self.assertEqual(m["citation_validity"], 0.95)                        # E02 rejected after retries


class Graph(unittest.TestCase):
    def test_langgraph_matches_sequential(self):
        try:
            from agent_evaluator import graphs
        except ImportError:
            self.skipTest("langgraph not installed")
        out = asyncio.run(graphs.trajectory_eval_graph().ainvoke(
            {"suite_id": "prior-auth", "candidate_run": "prior-auth-v2", "baseline_run": "prior-auth-v1"},
            {"configurable": {"llm": fx.ScriptedLLM(), "thread_id": "t"}, "recursion_limit": 20}))
        self.assertEqual(out["regression"].decision, "no-go")
        self.assertEqual(out["regression"].broken, ["PA-004"])


class Llm(unittest.TestCase):
    def test_env_falls_back_to_architect_settings(self):
        from agent_evaluator.llm import env
        old = {k: os.environ.pop(k, None) for k in ("AGENT_EVALUATOR_MODEL", "AI_ARCHITECT_MODEL")}
        try:
            os.environ["AI_ARCHITECT_MODEL"] = "anthropic:x"
            self.assertEqual(env("MODEL"), "anthropic:x")
            os.environ["AGENT_EVALUATOR_MODEL"] = "anthropic:y"
            self.assertEqual(env("MODEL"), "anthropic:y")
        finally:
            for k, v in old.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v


class McpServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        set_llm(fx.ScriptedLLM())

    async def asyncTearDown(self):
        set_llm(None)

    async def test_server_surface_and_calls(self):
        from agent_evaluator.server import mcp

        async with connect(mcp) as client:
            tools = {t.name for t in (await client.list_tools()).tools}
            self.assertEqual(tools, {"list_trace_runs", "load_trajectory", "check_task_success", "compare_runs",
                                     "write_eval_report", "classify_failures", "run_trajectory_eval"})
            prompts = {p.name for p in (await client.list_prompts()).prompts}
            self.assertEqual(prompts, {"evaluate_agent_change"})
            res = await client.read_resource("eval://taxonomy/failures")
            self.assertIn("unsafe_action_without_approval", res.contents[0].text)

            r = await client.call_tool("load_trajectory", {"run_id": "eval-set", "trace_id": "E13"})
            self.assertFalse(is_error(r), r.content)
            r = await client.call_tool("check_task_success", {"trajectory": structured(r)})
            self.assertFalse(is_error(r), r.content)
            self.assertTrue(structured(r)["safety_failure"])

            r = await client.call_tool("run_trajectory_eval", {"candidate_run": "prior-auth-v2",
                                                               "baseline_run": "prior-auth-v1"})
            self.assertFalse(is_error(r), r.content)
            self.assertEqual(structured(r)["decision"], "no-go")
            res = await client.read_resource(f"eval://runs/{structured(r)['run_id']}/report.md")
            self.assertIn("PA-004", res.contents[0].text)


# ---- MCP SDK 1.x / 2.x compatibility for the in-process client
def connect(server):
    try:
        from mcp import Client  # 2.x
        return Client(server)
    except ImportError:  # 1.x
        from mcp.shared.memory import create_connected_server_and_client_session
        return create_connected_server_and_client_session(server._mcp_server)


def is_error(result) -> bool:
    return bool(getattr(result, "is_error", getattr(result, "isError", False)))


def structured(result) -> dict:
    return getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)


if __name__ == "__main__":
    unittest.main()
