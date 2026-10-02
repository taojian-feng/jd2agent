"""LLM-backed tool: classify_failures. Its output passes a code check before it leaves the tool."""
from agent_evaluator import catalog
from agent_evaluator.llm import LLM, call_validated
from agent_evaluator.models import Diagnosis, FailureAnalysis, SuccessCheck, Trajectory
from agent_evaluator.tools import deterministic as d

SYSTEM = """You are an evaluator of AI agent trajectories. A run has already been checked by code and it failed.
Code tells you WHAT is wrong (the symptoms). Your job is to find WHY: the root cause, and any other failures,
each tied to the trace steps that show it.

Failure taxonomy (use only these label ids):
{taxonomy}

Root cause rule: {root_rule}

Rules:
- Every label cites step ids from the trace (e.g. "s4"). For a step that is missing, cite the step where it should
  have happened or the step that went ahead without it.
- evidence is a short phrase copied character for character from one of the cited steps (a value in its thought,
  args, result, error or content). Do not paraphrase or add quotes of your own.
- Look for the earliest step where the agent went wrong: compare each step's thought with the tool it called, the
  arguments with the ids in earlier results, and every evidence or rationale with what the tool results actually
  say. Symptoms such as wrong_final_answer or skipped_required_step are usually consequences.
- Return the root cause plus the other failures that contributed; do not repeat a label.

What the agent under evaluation is supposed to do:
{scenario}"""

USER = """Task {task_id} (trace {trace_id}). Expected outcome: {expected}. Outcome reached: {outcome}.
Steps used: {steps_used} of {max_steps}.

Symptoms found by code:
{symptoms}

Trace steps (one JSON object per step):
{steps}"""


def _scenario_brief(scenario_id: str) -> str:
    text = catalog.scenario(scenario_id)
    return text.split("\n## Cases")[0].strip()  # never show the expected outcomes per case


def build_prompt(trajectory: Trajectory, check: SuccessCheck, suite: dict) -> tuple[str, str]:
    """The exact (system, user) prompt pair sent to the model."""
    tax = catalog.taxonomy()
    system = SYSTEM.format(
        taxonomy="\n".join(f"- {l['id']}: {l['definition']}" for l in tax["labels"]),
        root_rule=" ".join(tax["root_cause_rule"].split()),
        scenario=_scenario_brief(suite["scenario"]))
    symptoms = "\n".join(f"- {s.label} {s.step_ids or '(missing step)'}: {s.detail}" for s in check.symptoms)
    user = USER.format(task_id=trajectory.task_id, trace_id=trajectory.trace_id, expected=check.expected_outcome,
                       outcome=check.outcome or "none (no terminal action)", steps_used=check.steps_used,
                       max_steps=check.max_steps, symptoms=symptoms or "- none",
                       steps="\n".join(d.step_line(s) for s in trajectory.steps))
    return system, user


def classify_failures(llm: LLM, trajectory: Trajectory, check: SuccessCheck, suite: dict,
                      retries: int = 2) -> Diagnosis:
    """Label each failure from the taxonomy and pick the root cause. Strict: labels outside the taxonomy, step ids
    that do not exist, or evidence that is not a verbatim quote from a cited step are rejected (retried, then raised)."""
    system, user = build_prompt(trajectory, check, suite)
    analysis = call_validated(llm, FailureAnalysis, system, user,
                              lambda a: d.validate_analysis(a, trajectory), "classify_failures", retries=retries)
    return d.merge_diagnosis(analysis, check)
