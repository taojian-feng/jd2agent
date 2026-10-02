# ai-architect-agent

The first JD2Agent agent, built from a *Senior Principal Architect, Applied AI* role spec for a large industrial equipment manufacturer
(`roles/industrial-applied-ai-architect/`). The same approach applies to any company hiring for this kind of role.
It designs agentic AI solutions from a business brief (W1) and reviews AI architecture designs (W2), served as an MCP server.

**Design rule:** every LLM output passes a deterministic check before it leaves a tool:
verbatim-quote verification, requirement → component → test traceability, and citation checks on review findings.

## Setup (Mac terminal)

```bash
cd ~/jd2agent/agents/ai-architect
uv sync --extra aws --extra dev          # or --extra azure / gcp / anthropic
uv run python -m unittest discover -s tests -t . -v    # 22 tests, no model or API key needed
```

The tests exercise the real pipeline with scripted model answers (`tests/fixtures.py`), including the
MCP server end to end. When LangGraph is installed the server runs the workflows as LangGraph graphs;
without it, it falls back to a built-in sequential runner with identical routing. Each result reports which engine it used.

## Use a real model

Set one env var in LangChain `init_chat_model` format (use your provider's current model ID):

```bash
export AI_ARCHITECT_MODEL="bedrock_converse:<bedrock model id>"      # plus AWS_PROFILE / AWS_REGION
# export AI_ARCHITECT_MODEL="azure_openai:<deployment>"              # plus AZURE_OPENAI_* vars
# export AI_ARCHITECT_MODEL="google_vertexai:<model>"
```

## Connect to Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (use the full path from `which uv`):

```json
{
  "mcpServers": {
    "ai-architect": {
      "command": "/opt/homebrew/bin/uv",
      "args": ["--directory", "/Users/taojianfeng/jd2agent/agents/ai-architect", "run", "ai-architect"],
      "env": { "AI_ARCHITECT_MODEL": "bedrock_converse:<model id>", "AWS_PROFILE": "default" }
    }
  }
}
```

### Run the full loop from the terminal

```bash
uv run python -c "
import asyncio
from ai_architect import catalog, workflows as wf
out = asyncio.run(wf.design_review_revise(catalog.scenario('dealer-fault-diagnosis'), 'aws', 'Dealer Fault Diagnosis'))
print(out['run_id'], [(h['decision'], h['score']) for h in out['history']])
"
```

Design -> review -> revise against the findings -> re-review, up to 2 rounds or until the review says go.
Outputs in `runs/<run_id>/`: `design.md`, `review.md`, `design_v2.md`, `review_v2.md`, ..., and a one-page `brief.md`.

Then pick the **Design, then review (demo)** prompt and paste the brief from
`resources/scenarios/dealer-fault-diagnosis.md`. To debug the server: `uv run mcp dev ai_architect/server.py`.

## Job runner (hands-off runs)

Start once in a terminal that has your model credentials, and leave it open:

```bash
uv run python -m ai_architect.runner
```

It runs allow-listed jobs dropped into `jobs/inbox/` (`tests`, `design`, `loop`, `review`, `probe`, `sync`) with validated
arguments, and writes `jobs/out/<id>.log` and `<id>.status.json`. It never runs arbitrary commands, and the allow-list
only changes when you restart it. `probe` checks that the model accepts every structured-output schema (a few cents).

## What's inside

| Path | What it is |
|---|---|
| `resources/` | The knowledge: agent patterns + selection signals, Azure/AWS/GCP service map, 19-rule review rulebook, templates, scenarios |
| `ai_architect/tools/deterministic.py` | Pattern scoring, platform lookup, traceability gate, Mermaid, rule checks, citation validation, readiness |
| `ai_architect/tools/llm_tools.py` | Requirements, design, LLMOps plan, ADRs, exec summary, judged rules, each with a validator and one retry |
| `ai_architect/workflows.py` | W1 and W2 nodes and routing (traceability loop, human confirmation, re-judge on bad citations) |
| `ai_architect/graphs.py` | LangGraph wiring of the same nodes |
| `ai_architect/cli.py`, `runner.py` | Command line for design / review / loop / probe, and the local job runner |
| `ai_architect/server.py` | MCP server: 7 resources, 17 tools (incl. the full design-review-revise loop), 3 prompts |
| `examples/` | `dealer-fault-diagnosis-live/`: real model run, v1 conditional to v2 go. `dealer-fault-diagnosis-scripted/`: output from the test fixtures |

Outputs are saved under `runs/<run_id>/` and exposed as `architect://runs/<run_id>/design.md` and `review.md`.
