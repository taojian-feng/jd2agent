"""Runs with the standard library:  python -m unittest discover -s tests -v   (pytest also works)."""
import json
import os
import re
import tempfile
import unittest

os.environ.setdefault("AI_ARCHITECT_RUNS", tempfile.mkdtemp(prefix="ai-architect-runs-"))

from ai_architect import catalog, workflows as wf  # noqa: E402
from ai_architect.llm import FakeLLM, ValidationFailed, set_llm  # noqa: E402
from ai_architect.models import ComponentDesign, Finding, LLMOpsPlan, Requirements  # noqa: E402
from ai_architect.tools import deterministic as d  # noqa: E402
from ai_architect.tools import llm_tools as lt  # noqa: E402
from tests import fixtures as fx  # noqa: E402

BRIEF = catalog.scenario("dealer-fault-diagnosis")


class Catalogs(unittest.TestCase):
    def test_fixture_rules_match_rulebook(self):
        judged = [r["id"] for r in catalog.rules() if r["check"] == "judged"]
        self.assertEqual(sorted(judged), sorted(fx.JUDGED_RULES))

    def test_deterministic_rules_point_at_template_sections(self):
        sections = set(catalog.template_sections())
        for r in catalog.rules():
            if r["check"] == "deterministic":
                self.assertIn(r["requires_section"], sections, r["id"])


class DeterministicTools(unittest.TestCase):
    def setUp(self):
        self.reqs = Requirements.model_validate(fx.REQUIREMENTS)
        self.design = ComponentDesign.model_validate(fx.DESIGN)
        self.llmops = LLMOpsPlan.model_validate(fx.LLMOPS)

    def test_quote_matching_ignores_whitespace_case_and_dashes(self):
        self.assertTrue(d.quote_in("spends 2-4 HOURS   cross-referencing", BRIEF))
        self.assertFalse(d.quote_in("spends 5 hours", BRIEF))
        self.assertFalse(d.quote_in("", BRIEF))

    def test_pattern_fit_dealer(self):
        fit = d.assess_pattern_fit(self.reqs)
        self.assertEqual(fit.ranked[0].id, "P5")
        self.assertEqual(fit.ranked[0].contributions, {"open_ended_reasoning": 2, "audit_required": 1})
        self.assertEqual(fit.modifiers, ["M1", "M2"])

    def test_one_signal_flips_the_pattern(self):
        flipped = self.reqs.model_copy(deep=True)
        for s in flipped.signals:
            if s.name == "steps_known_upfront":
                s.value = True
            if s.name == "open_ended_reasoning":
                s.value = False
        self.assertEqual(d.assess_pattern_fit(flipped).ranked[0].id, "P2")

    def test_platform_mapping_never_invents(self):
        m = d.map_platform(self.design, "azure")
        self.assertEqual(m.services["manual_index"], "Azure AI Search")
        self.assertEqual(m.services["workorder_draft"], "Custom service on Azure Container Apps")
        self.assertEqual(m.unmapped, [])
        odd = self.design.model_copy(deep=True)
        odd.components[0].type = "quantum_cache"
        self.assertEqual(d.map_platform(odd, "aws").unmapped, ["tablet_app"])  # unknown types are reported, never invented

    def test_traceability_passes_and_catches_gaps(self):
        self.assertTrue(d.check_traceability(self.reqs, self.design, self.llmops).passed)
        bad = ComponentDesign.model_validate(fx.DESIGN_MISSING_FR3)
        t = d.check_traceability(self.reqs, bad, self.llmops)
        self.assertFalse(t.passed)
        self.assertEqual(t.unmapped_requirements, ["FR-3"])
        self.assertEqual(t.unknown_references, ["workorder_draft"])

    def test_mermaid(self):
        m = d.render_diagram(self.design)
        self.assertTrue(m.startswith("flowchart LR"))
        self.assertIn('planner -- "dealer-scoped query" --> repair_history_tool', m)

    def test_empty_template_is_no_go(self):
        doc = d.load_design(catalog.text("templates/design_doc.md"))
        findings = d.run_rule_checks(doc)
        self.assertEqual({f.rule_id for f in findings}, {"SEC-01", "DAT-01", "EVL-01", "OPS-01", "CST-01"})
        r = d.score_readiness(findings)
        self.assertEqual((r.decision, r.blockers), ("no-go", ["EVL-01", "SEC-01"]))

    def test_citation_validation(self):
        doc = d.load_design("# T\n## Observability\nWeekly review of feedback by the team.\n")
        good = Finding(rule_id="OPS-03", category="operations", severity="minor", message="m",
                       section="Observability", evidence="quote", quote="weekly review of feedback", source="judged")
        fake = good.model_copy(update={"quote": "daily review"})
        wrong_section = good.model_copy(update={"section": "Cost"})
        absence = good.model_copy(update={"evidence": "absence", "quote": "", "section": "Cost"})
        valid, invalid = d.validate_citations([good, fake, wrong_section, absence], doc)
        self.assertEqual(valid, [good, absence])
        self.assertEqual(invalid, [fake, wrong_section])

    def test_readiness_levels(self):
        f = lambda sev: Finding(rule_id="X", category="cost", severity=sev, message="", section="Cost",
                                evidence="absence", source="judged")
        self.assertEqual(d.score_readiness([]).decision, "go")
        self.assertEqual(d.score_readiness([f("minor")]).decision, "go")
        self.assertEqual(d.score_readiness([f("major")]).decision, "conditional")
        self.assertEqual(d.score_readiness([f("blocker")]).decision, "no-go")


class LLMToolValidators(unittest.TestCase):
    def test_requirements_reject_invented_quotes(self):
        bad = json.loads(json.dumps(fx.REQUIREMENTS))
        bad["items"][0]["source_quote"] = "the system must integrate with SAP"
        llm = FakeLLM({"Requirements": [bad]})
        with self.assertRaises(ValidationFailed) as e:
            lt.extract_requirements(llm, BRIEF)
        self.assertIn("not verbatim", str(e.exception))
        self.assertEqual(len(llm.calls), 2)  # one retry with the problems listed
        self.assertIn("failed these checks", llm.calls[1][2])

    def test_requirements_retry_then_succeed(self):
        bad = json.loads(json.dumps(fx.REQUIREMENTS))
        bad["signals"] = bad["signals"][:3]
        llm = FakeLLM({"Requirements": [bad, fx.REQUIREMENTS]})
        self.assertEqual(len(lt.extract_requirements(llm, BRIEF).items), 6)

    def test_exec_summary_acronyms(self):
        from ai_architect.models import ExecSummary
        self.assertEqual(lt.validate_exec_summary(ExecSummary(markdown="Uses retrieval (RAG). RAG is fine.")), [])
        self.assertTrue(lt.validate_exec_summary(ExecSummary(markdown="Uses RAG.")))
        self.assertTrue(lt.validate_exec_summary(ExecSummary(markdown="word " * 401)))

    def test_adrs_need_two_options(self):
        bad = json.loads(json.dumps(fx.ADRS))
        bad["adrs"][1]["options"] = ["Filter server-side"]
        reqs = Requirements.model_validate(fx.REQUIREMENTS)
        with self.assertRaises(ValidationFailed) as e:
            lt.draft_adrs(FakeLLM({"ADRList": [bad]}), reqs, d.assess_pattern_fit(reqs),
                          ComponentDesign.model_validate(fx.DESIGN))
        self.assertIn("at least two options", str(e.exception))


class LangChainAdapter(unittest.TestCase):
    """Checks the provider settings without calling any API (langchain is replaced by a stand-in)."""

    def _make(self, model, env):
        import sys, types
        from unittest import mock
        from ai_architect.llm import LangChainLLM
        seen = {}

        class Model:
            def with_structured_output(self, schema, **kw):
                seen["structured_kw"] = kw
                return types.SimpleNamespace(invoke=lambda msgs: schema.model_validate(fx.SUMMARY))

        def init_chat_model(name, **kw):
            seen["init_kw"] = kw
            return Model()

        fake = types.ModuleType("langchain.chat_models")
        fake.init_chat_model = init_chat_model
        clean = {k: v for k, v in os.environ.items() if not k.startswith("AI_ARCHITECT_") or k == "AI_ARCHITECT_RUNS"}
        with mock.patch.dict(sys.modules, {"langchain": types.ModuleType("langchain"), "langchain.chat_models": fake}), \
                mock.patch.dict(os.environ, {**clean, **env}, clear=True):
            from ai_architect.models import ExecSummary
            LangChainLLM(model).structured(ExecSummary, "s", "u")
        return seen

    def test_anthropic_defaults(self):
        seen = self._make("anthropic:claude-sonnet-5-5", {})
        self.assertNotIn("temperature", seen["init_kw"])  # newer models reject non-default temperature
        self.assertEqual(seen["init_kw"]["max_tokens"], 16000)
        self.assertEqual(seen["structured_kw"], {"method": "json_schema"})

    def test_other_providers_and_overrides(self):
        self.assertEqual(self._make("bedrock_converse:x", {})["structured_kw"], {})
        seen = self._make("bedrock_converse:x", {"AI_ARCHITECT_TEMPERATURE": "0", "AI_ARCHITECT_STRUCTURED_METHOD": "json_schema"})
        self.assertEqual(seen["init_kw"]["temperature"], 0.0)
        self.assertEqual(seen["structured_kw"], {"method": "json_schema"})


class Workflows(unittest.IsolatedAsyncioTestCase):
    async def test_w1_end_to_end(self):
        llm = FakeLLM(fx.responses())
        out = await wf.solution_design(BRIEF, "aws", "Dealer Fault Diagnosis", {"llm": llm})
        self.assertTrue(out["trace"].passed)
        self.assertEqual(out["design_attempts"], 1)
        doc = out["design_doc"]
        for section in catalog.template_sections():
            self.assertIn(f"## {section}\n", doc)
        self.assertIn("Selected: P5", doc)
        self.assertTrue((wf.runs_dir() / out["run_id"] / "design.md").exists())

    async def test_w1_traceability_loop_repairs_design(self):
        llm = FakeLLM(fx.responses(first_design_bad=True))
        out = await wf.solution_design(BRIEF, "azure", "Loop", {"llm": llm})
        self.assertEqual(out["design_attempts"], 2)
        self.assertTrue(out["trace"].passed)
        self.assertEqual(out["_trace"].count("check_traceability"), 2)
        design_prompts = [u for name, _, u in llm.calls if name == "ComponentDesign"]
        self.assertIn("Fix these gaps", design_prompts[-1])

    async def test_w1_ships_with_gaps_after_max_attempts(self):
        r = fx.responses()
        r["ComponentDesign"] = [fx.DESIGN_MISSING_FR3]
        out = await wf.solution_design(BRIEF, "gcp", "Gaps", {"llm": FakeLLM(r)})
        self.assertEqual(out["design_attempts"], wf.MAX_DESIGN_ATTEMPTS)
        self.assertFalse(out["trace"].passed)
        self.assertIn("Unmapped requirement FR-3", out["design_doc"])

    async def test_w1_human_confirmation_adds_context(self):
        asked = []

        async def confirm(reqs):
            asked.append(len(reqs.items))
            return "Technicians often work offline." if len(asked) == 1 else None

        llm = FakeLLM(fx.responses())
        out = await wf.solution_design(BRIEF, "aws", "Confirm", {"llm": llm, "confirm": confirm})
        self.assertEqual(asked, [6])  # asked once (max rounds), then re-extracted with the new context
        self.assertEqual(out["_trace"][:3], ["extract_requirements", "confirm_requirements", "extract_requirements"])
        self.assertIn("Technicians often work offline.", out["brief"])

    async def test_design_then_review(self):
        w1 = await wf.solution_design(BRIEF, "aws", "Dealer", {"llm": FakeLLM(fx.responses())})
        llm = FakeLLM(fx.responses(first_verdicts_bad=True))
        w2 = await wf.architecture_review(w1["design_doc"], w1["run_id"], {"llm": llm})
        self.assertEqual(w2["rule_findings"], [])  # every required section is filled
        self.assertEqual(sorted(f.rule_id for f in w2["findings"]), ["OPS-03", "SEC-04"])
        self.assertEqual(w2["readiness"].decision, "conditional")
        self.assertEqual(sum(1 for n, _, _ in llm.calls if n == "RuleVerdicts"), 2)  # bad quote -> retried
        self.assertTrue((wf.runs_dir() / w1["run_id"] / "review.md").exists())

    async def test_planted_defect_missing_evaluation_is_no_go(self):
        w1 = await wf.solution_design(BRIEF, "aws", "Dealer", {"llm": FakeLLM(fx.responses())})
        flawed = re.sub(r"## Evaluation\n.*?(?=\n## )", "## Evaluation\nTBD\n", w1["design_doc"], flags=re.S)
        w2 = await wf.architecture_review(flawed, None, {"llm": FakeLLM(fx.responses())})
        self.assertIn("EVL-01", w2["readiness"].blockers)
        self.assertEqual(w2["readiness"].decision, "no-go")


class RulePacks(unittest.IsolatedAsyncioTestCase):
    def test_catalog(self):
        self.assertEqual(catalog.available_packs(), ["healthcare"])
        self.assertEqual(catalog.packs_for_scenario("prior-auth-review"), ["healthcare"])
        self.assertEqual(catalog.packs_for_scenario("dealer-fault-diagnosis"), [])
        ids = [r["id"] for r in catalog.all_rules()]
        self.assertEqual(len(ids), len(set(ids)), "rule ids are unique across packs")
        judged = [r["id"] for r in catalog.pack("healthcare")["rules"] if r["check"] == "judged"]
        self.assertEqual(judged, fx.HEALTHCARE_JUDGED)
        cats = set(catalog.load("review_rules.yaml")["categories"])
        sections = set(catalog.template_sections())
        for r in catalog.pack("healthcare")["rules"]:
            self.assertIn(r["category"], cats, r["id"])
            if r["check"] == "deterministic":
                self.assertIn(r["requires_section"], sections, r["id"])
        with self.assertRaises(KeyError):
            catalog.pack("../review")

    def test_healthcare_scenario_brief(self):
        brief = catalog.scenario("prior-auth-review")
        self.assertIn("never\ndeny", brief.replace("never deny", "never\ndeny"))
        self.assertNotIn("HC-0", brief)

    async def test_review_with_pack(self):
        w1 = await wf.solution_design(BRIEF, "aws", "Pack", {"llm": FakeLLM(fx.responses())})
        flawed = re.sub(r"## Human Oversight\n.*?(?=\n## )", "## Human Oversight\nTBD\n", w1["design_doc"],
                        flags=re.S)
        llm = FakeLLM({**fx.responses(), "RuleVerdicts": [fx.verdicts(
            extra=fx.HEALTHCARE_JUDGED, fail_extra={"HC-02": "Human Oversight", "HC-05": "Failure Modes"})]})
        w2 = await wf.architecture_review(flawed, w1["run_id"], {"llm": llm, "rule_packs": ["healthcare"]},
                                          "review_pack.md")
        ids = {f.rule_id for f in w2["findings"]}
        self.assertLessEqual({"HC-07", "HC-02", "HC-05"}, ids)
        self.assertEqual(w2["readiness"].decision, "no-go")
        self.assertIn("HC-02", w2["readiness"].blockers)
        prompt = next(u for n, _, u in llm.calls if n == "RuleVerdicts")
        self.assertIn("HC-04 (blocker)", prompt)
        self.assertIn("Rulebook: general + healthcare", w2["review"])
        self.assertEqual(wf.load_meta(w1["run_id"])["rule_packs"], ["healthcare"])

    async def test_without_pack_no_healthcare_rules(self):
        llm = FakeLLM(fx.responses())
        w1 = await wf.solution_design(BRIEF, "aws", "NoPack", {"llm": llm})
        w2 = await wf.architecture_review(w1["design_doc"], w1["run_id"], {"llm": llm})
        prompt = next(u for n, _, u in llm.calls if n == "RuleVerdicts")
        self.assertNotIn("HC-0", prompt)
        self.assertIn("Rulebook: general\n", w2["review"])

    async def test_missing_pack_verdict_is_retried(self):
        doc = d.load_design(catalog.text("templates/design_doc.md"))
        llm = FakeLLM({"RuleVerdicts": [fx.verdicts(all_pass=True), fx.verdicts(all_pass=True, extra=fx.HEALTHCARE_JUDGED)]})
        lt.judge_rules(llm, doc, None, ["healthcare"])
        self.assertEqual(len(llm.calls), 2)
        self.assertIn("give exactly one verdict for HC-01", llm.calls[1][2])


class ReviserSeesPackRules(unittest.TestCase):
    def test_pack_rules_in_revision_prompt(self):
        self.assertIn("HC-04 (blocker)", lt._pack_rules(["healthcare"]))
        self.assertEqual(lt._pack_rules([]), "")


class DefectSets(unittest.TestCase):
    MD = "# T\n\n## Human Oversight\nA nurse reviews every denial.\n\n## Evaluation\nGated suite.\n"

    def test_edits(self):
        from ai_architect import defects
        md = defects.apply_edit(self.MD, {"section": "Human Oversight", "set": "Nobody reviews."})
        self.assertIn("## Human Oversight\nNobody reviews.\n\n## Evaluation", md)
        md = defects.apply_edit(self.MD, {"section": "Evaluation", "append": "Spot checks only."})
        self.assertTrue(md.rstrip().endswith("Gated suite.\n\nSpot checks only."))
        md = defects.apply_edit(self.MD, {"section": "Human Oversight", "replace": ["every denial", "5% of cases"]})
        self.assertIn("A nurse reviews 5% of cases.", md)
        with self.assertRaises(ValueError):
            defects.apply_edit(self.MD, {"section": "Cost", "set": "x"})
        with self.assertRaises(ValueError):
            defects.apply_edit(self.MD, {"section": "Evaluation", "replace": ["absent text", "y"]})

    def test_score(self):
        from ai_architect import defects
        spec = {"watch_rules": ["HC-01", "HC-02"], "variants": [
            {"id": "clean"}, {"id": "d1", "defect": "phi", "expect_any": ["HC-01"]},
            {"id": "d2", "defect": "denial", "expect_any": ["HC-02", "REL-01"]}]}
        res = defects.score_set(spec, {"clean": ["HC-02", "SEC-04"], "d1": ["HC-01"], "d2": ["SEC-04"]},
                                {"clean": "no-go", "d1": "no-go", "d2": "conditional"})
        self.assertEqual((res["caught"], res["planted"], res["recall"]), (1, 2, 0.5))
        self.assertEqual(res["clean_false_alarms"], ["HC-02"])
        self.assertIn("| d2 | denial | HC-02 or REL-01 | conditional | NO |", defects.report(res, 0.8))

    def test_committed_sets_build(self):
        from ai_architect import defects
        root = catalog.RESOURCES / "defect_sets"
        for d_ in sorted(root.iterdir()) if root.exists() else []:
            spec = defects.load_set(d_.name)
            v = defects.variants(spec)
            self.assertEqual(len(v), len(spec["variants"]))
            for r in spec["watch_rules"]:
                catalog.rule(r)


class ReviseLoop(unittest.IsolatedAsyncioTestCase):
    async def test_conditional_review_is_fixed_and_reaches_go(self):
        r = fx.responses()
        r["RuleVerdicts"] = [fx.verdicts(), fx.verdicts(all_pass=True)]  # first review conditional, then clean
        out = await wf.design_review_revise(BRIEF, "aws", "Loop demo", {"llm": FakeLLM(r)})
        self.assertEqual([h["decision"] for h in out["history"]], ["conditional", "go"])
        self.assertEqual(out["history"][0]["findings"], [("major", "SEC-04"), ("minor", "OPS-03")])
        s = out["design"]
        self.assertEqual(s["version"], 2)
        self.assertTrue(s["trace"].passed)
        self.assertEqual([e["rule_id"] for e in s["revision_log"]], ["SEC-04", "OPS-03"])
        self.assertIn("## Revision Log", s["design_doc"])
        self.assertIn("Why this pattern rather than a simpler one", s["design_doc"])
        run = wf.runs_dir() / out["run_id"]
        for name in ("design.md", "review.md", "design_v2.md", "review_v2.md", "brief.md"):
            self.assertTrue((run / name).exists(), name)
        self.assertIn("| v1 | CONDITIONAL", out["brief"])
        self.assertIn("| v2 | GO", out["brief"])
        self.assertIn("**SEC-04** (major)", out["brief"])
        self.assertLess(len(out["brief"].split()), 900)

    async def test_loop_stops_after_max_rounds(self):
        out = await wf.design_review_revise(BRIEF, "aws", "Stubborn", {"llm": FakeLLM(fx.responses())})
        self.assertEqual([h["decision"] for h in out["history"]], ["conditional"] * 3)
        self.assertEqual(out["design"]["version"], 1 + wf.MAX_REVISION_ROUNDS)

    async def test_go_on_first_review_needs_no_revision(self):
        r = fx.responses()
        r["RuleVerdicts"] = [fx.verdicts(all_pass=True)]
        out = await wf.design_review_revise(BRIEF, "aws", "Clean", {"llm": FakeLLM(r)})
        self.assertEqual(len(out["history"]), 1)
        self.assertNotIn("## Revision Log", out["design"]["design_doc"])

    def test_revision_must_address_every_major(self):
        from ai_architect.models import RevisionPatch
        reqs = Requirements.model_validate(fx.REQUIREMENTS)
        sec04 = Finding(rule_id="SEC-04", category="security", severity="major", message="m",
                        section="Identity and Access", evidence="absence", source="judged")
        patch = RevisionPatch.model_validate({**fx.REVISION_PATCH, "changes": fx.REVISION_PATCH["changes"][1:]})
        problems = lt.validate_revision(patch, reqs, "P5", [sec04], ComponentDesign.model_validate(fx.DESIGN),
                                        LLMOpsPlan.model_validate(fx.LLMOPS))
        self.assertIn("no change listed that resolves SEC-04", problems)

    def test_apply_patch_changes_only_what_it_names(self):
        from ai_architect.models import RevisionPatch
        design, llmops = ComponentDesign.model_validate(fx.DESIGN), LLMOpsPlan.model_validate(fx.LLMOPS)
        redactor = {"id": "redactor", "name": "Trace redaction", "type": "custom",
                    "responsibility": "Redact restricted fields before traces are stored", "satisfies": ["NFR-2"]}
        from ai_architect.models import EMPTY_PATCH
        patch = RevisionPatch.model_validate({
            **EMPTY_PATCH, "governance": ["Traces redacted; 1-year retention"],
            "update_components": [{**fx.DESIGN["components"][1], "responsibility": "Plans with a step cap"}],
            "add_components": [redactor],
            "add_tests": [{"id": "U9", "name": "Redaction", "kind": "unit", "covers": ["redactor"],
                           "metric": "restricted fields in traces", "threshold": "0"}]})
        d2, o2, problems = lt.apply_patch(design, llmops, patch)
        self.assertEqual(problems, [])
        self.assertEqual(d2.components[1].responsibility, "Plans with a step cap")
        self.assertEqual(d2.components[-1].id, "redactor")
        self.assertEqual(d2.identity_access, design.identity_access)          # untouched
        self.assertEqual(o2.governance, ["Traces redacted; 1-year retention"])
        self.assertEqual(o2.monitoring, llmops.monitoring)                     # untouched
        self.assertEqual(len(o2.tests), len(llmops.tests) + 1)
        self.assertEqual(len(design.components), 11)                           # original not mutated
        bad = RevisionPatch.model_validate({**EMPTY_PATCH, "update_components": [redactor]})
        self.assertIn("update_components: redactor does not exist", lt.apply_patch(design, llmops, bad)[2][0])

    def test_truncated_output_is_retried_not_crashed(self):
        from ai_architect.llm import call_validated
        from ai_architect.models import ExecSummary

        class Flaky:
            calls = 0

            def structured(self, schema, system, user):
                Flaky.calls += 1
                if Flaky.calls == 1:
                    raise ValueError("Field required: monitoring")
                return schema.model_validate(fx.SUMMARY)

        out = call_validated(Flaky(), ExecSummary, "s", "u", lambda o: [], "t")
        self.assertEqual(Flaky.calls, 2)
        self.assertTrue(out.markdown.startswith("## Executive Summary"))


class McpServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        set_llm(FakeLLM(fx.responses()))

    async def asyncTearDown(self):
        set_llm(None)

    async def test_server_surface_and_calls(self):
        from ai_architect.server import mcp

        async with connect(mcp) as client:
            tools = {t.name for t in (await client.list_tools()).tools}
            self.assertLessEqual({"assess_pattern_fit", "map_platform", "check_traceability", "extract_requirements",
                                  "judge_rules", "run_solution_design", "run_architecture_review",
                                  "list_rule_packs"}, tools)
            res = await client.read_resource("architect://rules/healthcare")
            self.assertIn("HC-02", res.contents[0].text)
            res = await client.read_resource("architect://rules/review")
            self.assertIn("SEC-01", res.contents[0].text)
            prompts = {p.name for p in (await client.list_prompts()).prompts}
            self.assertEqual(prompts, {"design_agentic_solution", "review_ai_architecture", "design_then_review"})
            res = await client.read_resource("architect://scenarios/dealer-fault-diagnosis")
            self.assertIn("fault code", res.contents[0].text)

            r = await client.call_tool("map_platform", {"design": fx.DESIGN, "cloud": "gcp"})
            self.assertFalse(is_error(r))
            self.assertEqual(structured(r)["services"]["manual_index"], "Vertex AI Vector Search")

            r = await client.call_tool("run_solution_design", {"brief": BRIEF, "cloud": "aws", "title": "MCP demo"})
            self.assertFalse(is_error(r), r.content)
            run_id = structured(r)["run_id"]
            self.assertTrue(structured(r)["traceability_passed"])

            r = await client.call_tool("run_architecture_review", {"run_id": run_id})
            self.assertFalse(is_error(r), r.content)
            self.assertEqual(structured(r)["decision"], "conditional")

            res = await client.read_resource(f"architect://runs/{run_id}/review.md")
            self.assertIn("Decision: CONDITIONAL", res.contents[0].text)

            set_llm(FakeLLM(fx.responses()))  # fresh scripted answers for a new workflow run
            r = await client.call_tool("run_design_review_revise", {"brief": BRIEF, "cloud": "aws", "max_rounds": 1})
            self.assertFalse(is_error(r), r.content)
            self.assertEqual(structured(r)["rounds"], 1)
            self.assertIn("one-page brief", structured(r)["brief"])


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
