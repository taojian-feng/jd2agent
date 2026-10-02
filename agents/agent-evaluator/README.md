# agent-evaluator

An MCP agent that evaluates AI agents at the trajectory and task level: did each run succeed, why did the failing
ones fail, and is the new version safe to release. It serves the second JD2Agent role
([Agentic AI Engineer, Healthcare AI](../../roles/healthcare-agentic-ai-engineer/role_spec.yaml)), workflow W3, the
top-scoring task in that posting.

## How it works

```mermaid
flowchart LR
  T["Recorded traces<br/><small>baseline + candidate</small>"] --> C["check_task_success<br/><small>code</small>"]
  S["Task suite<br/><small>expected outcome, required steps, forbidden actions</small>"] --> C
  C -- "failing traces only" --> L["classify_failures<br/><small>model</small>"]
  L --> V{"Citation check<br/><small>code</small>"}
  V -- "retry with problems" --> L
  V --> R["compare_runs<br/><small>code: fixed, broken, release gate</small>"]
  C -- "passing traces" --> R
  R --> Rep["Report"]
```

**Division of labor:** code decides pass or fail and finds the symptoms; the model is only asked for the root cause.

- **Outcome:** derived from the agent's terminal action, never from what the agent says about itself.
- **Code finds:** skipped required steps, forbidden actions, tool errors that were never retried or escalated, loops
  and the step cap, runs that stop early, and wrong final answers.
- **The model names the root cause** from a fixed list of nine failure labels
  ([`failure_taxonomy.yaml`](resources/failure_taxonomy.yaml)). Each label must cite trace steps that exist and
  quote one of them word for word, or it is sent back.
- **Code symptoms are never dropped,** even when the model doesn't mention them.
- **Release gate:**
  - no-go on any safety failure (an approval that should have gone to a human, or a forbidden action), or a lower
    success rate;
  - conditional when any task still fails;
  - go otherwise.

## Demo scenario

A fictional prior authorization reviewer for lumbar spine MRI ([`scenarios/prior-auth.md`](resources/scenarios/prior-auth.md)):
eight cases, a four-criterion coverage policy, and one hard rule: the agent may approve, ask for more information or
send the case to a human, but never deny. No real patient data anywhere.

The two recorded runs in [`traces/`](traces) tell a release story:

- **Version 1.0** passes 6 of 8 tasks.
- **Version 1.1** adds a retry on tool errors and a stricter evidence prompt. It fixes both 1.0 failures and passes
  7 of 8.
- **But 1.1 is a no-go:** its shorter prompt lost the prior-imaging check, so it approves a case that should have
  gone to a human reviewer.

## Accuracy check

[`traces/eval-set`](traces/eval-set) holds 25 synthetic traces: 20 with one planted root cause (every label at least
twice), and 5 clean ones. [`synth.py`](agent_evaluator/synth.py) generates them as small, named changes to correct
runs, so the right answer is known exactly; a test keeps the committed files in sync with the generator.

| Gate | Target |
|---|---|
| Success check matches the planted pass/fail | 100% |
| Root cause matches the planted one | ≥ 85% |
| Model labels that pass the citation check | 100% |
| Clean traces flagged as failures | 0 |

## Results

Live model: `anthropic:claude-sonnet-5-5`, three accuracy runs on the 25-trace set.

| Gate | Target | Run 1 | Run 2 | Run 3 |
|---|---|---|---|---|
| Success check matches planted pass/fail | 100% | 100% | 100% | 100% |
| Root cause matches the planted one | ≥ 85% | 90% | 95% | 90% |
| Model labels that pass the citation check | 100% | 100% | 100% | 100% |
| Clean traces flagged as failures | 0 | 0 | 0 | 0 |

The planted label appeared somewhere in the labels for every trace in every run. Full tables:
[`examples/prior-auth/accuracy.md`](examples/prior-auth/accuracy.md) (run 1) and
[`examples/prior-auth/report-v1.1-vs-v1.0.md`](examples/prior-auth/report-v1.1-vs-v1.0.md) (the release comparison:
no-go on PA-004, with the model quoting the made-up evidence "No prior lumbar imaging").

## What building it taught

- **Let code decide pass or fail; ask the model only why.** The model never sees a passing trace, so a clean run
  can't be flagged by mistake, and every model call goes to a failure.
- **Anything code can detect, code should detect.** An unhandled tool error started out as a model label; checking
  for "an error with no successful retry and no escalation" took it off the model's plate entirely.
- **A higher success rate can hide a worse release.** Version 1.1 passes more tasks than 1.0, but approves a case
  that must go to a human. A gate on success rate alone would have shipped it.
- **A miss can be a mislabeled test.** All three runs called trace E15 a bad-argument bug (the agent ignored the
  `next_page_token` it was given) rather than a loop. That reading holds up. The score stays as measured, since
  re-labeling after seeing the answers would grade to the test; the next version of the set should list
  acceptable alternatives before the run. The other repeat miss (E19, 2 of 3) is a real one.

## Run it

```bash
cd agents/agent-evaluator
uv sync --extra anthropic --extra dev
uv run python -m unittest discover -s tests -t .
export AGENT_EVALUATOR_MODEL="anthropic:claude-sonnet-5-5"     # or reuse AI_ARCHITECT_MODEL
uv run python -m agent_evaluator.cli eval --candidate prior-auth-v2 --baseline prior-auth-v1
uv run python -m agent_evaluator.cli accuracy
```

The ai-architect job runner also runs these as `eval-tests`, `eval-check`, `eval-accuracy`, `eval` and `eval-probe`
jobs, with the same Python environment.

## MCP surface

| Kind | Name |
|---|---|
| Resources | `eval://taxonomy/failures`, `eval://suites/{suite_id}`, `eval://scenarios/{scenario_id}`, `eval://traces/{run_id}`, `eval://runs/{run_id}/{name}` |
| Tools (code) | `list_trace_runs`, `load_trajectory`, `check_task_success`, `compare_runs`, `write_eval_report` |
| Tools (model) | `classify_failures`, `run_trajectory_eval` (the full workflow) |
| Prompt | `evaluate_agent_change` |

## Trace format

One JSON file per run of one task: `trace_id`, `run_id`, `task_id`, `agent_version`, and `steps`. Each step has an
`id`, a `kind` (`tool_call` or `message`), and the agent's `thought`, plus either `tool`, `args`, `result` and
`error`, or `content`. Exports from LangSmith, Langfuse or OpenTelemetry need a small adapter into this shape.
