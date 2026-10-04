"""Partner memo: the model drafts the answer to "should we fine-tune?"; code checks every number against the plan."""
import json
import re

from agent_evaluator.llm import LLM, call_validated

from customization_planner.models import Memo, Plan

SYSTEM = """You are a solutions architect writing to a partner's engineering lead. Plain language, short sentences.
Use only the numbers in the plan you are given. The person in the role decides; you recommend."""

NUMBER = re.compile(r"\d+(?:\.\d+)?%?")


def allowed_numbers(plan: Plan) -> set[str]:
    blob = json.dumps({"stats": plan.stats, "gates": [g.model_dump() for g in plan.gates], "split": plan.split,
                       "recommendation": plan.recommendation, "changes": [c.model_dump() for c in plan.changes]})
    nums = set(NUMBER.findall(blob))
    return nums | {n.rstrip("%") for n in nums} | {re.sub(r"\D", "", t) for t in plan.split["train"] + plan.split["eval"]}


def validate_memo(memo: Memo, plan: Plan) -> list[str]:
    problems = []
    text = f"{memo.headline}\n{memo.body}"
    ok = allowed_numbers(plan)
    found = NUMBER.findall(text)
    for n in found:
        if n not in ok and n.rstrip("%") not in ok:
            problems.append(f"the number {n} is not in the plan; use only the plan's numbers")
    missing = [n for n in found if n not in memo.numbers_used]
    if missing:
        problems.append(f"list every number you used in numbers_used; missing {sorted(set(missing))}")
    if len(memo.body.split()) > 250:
        problems.append("body is over 250 words")
    if plan.verdict != "ready" and re.search(r"\b(ready to (fine-?tune|train)|go ahead and (fine-?tune|train))\b",
                                             text, re.I):
        problems.append(f"the plan's verdict is {plan.verdict}; do not say it is ready to train")
    return problems


def draft_memo(llm: LLM, plan: Plan, plan_md: str) -> Memo:
    user = f"""The partner asked: should we fine-tune the model behind this agent?
Write the answer from this plan (computed by code from their recorded runs):

{plan_md}"""
    return call_validated(llm, Memo, SYSTEM, user, lambda m: validate_memo(m, plan), "draft_memo", retries=2)
