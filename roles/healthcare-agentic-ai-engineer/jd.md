# Agentic AI Engineer, Healthcare AI

_Example input for JD2Agent. A generic posting for an AI-first healthcare decisioning team, adapted from real postings
of this type; company name, funding, pay, travel and sponsorship details removed._

## Summary

Healthcare decision-making has become slow, costly and adversarial: care delayed by prior authorization and paperwork,
claims that misfire, and clinical decisions made without the right information at the right moment. This team builds
reasoning models and agentic systems that rebuild how those decisions are made across payers, providers and life
sciences.

You will own agent systems end to end, from architecture through production, and your work ships into live clinical
and operational settings. You will design, build, and operationalize the LLM- and SLM-powered systems behind real
healthcare decisioning: the reasoning, orchestration, retrieval, memory, and control layers that let agents operate
reliably across clinical reasoning, prior authorization and claims integrity, care navigation, and operational
workflows. This is not a prompt-only role: a wrong action has real consequences for patients and clinicians.

You do not need a healthcare background; engineers are paired with clinical and domain experts.

## Work You'll Do

### Agent architecture & orchestration

1. Design and implement agentic systems capable of multi-step reasoning, planning, tool use, and workflow execution against complex, regulated operational processes.
2. Build stateful workflows using frameworks such as LangGraph and LangChain - including branching, retries, self-correction, human-in-the-loop checkpoints, and reusable orchestration patterns.
3. Engineer for long-horizon reliability - multi-step task completion, recovery from compounding errors, planning under uncertainty, and robust tool use when individual steps fail.
4. Build the reasoning behind regulated decisions - policy- and criteria-grounded outputs, structured proposer/critic/judge-style review, and auditable rationales for high-stakes decisions across the industry, from clinical review and prior authorization to claims integrity and care management.

### Retrieval, grounding & context engineering

1. Develop end-to-end Retrieval-Augmented Generation (RAG) pipelines: ingestion, chunking, embeddings, vector and hybrid retrieval, reranking, contextual compression, and grounding strategies.
2. Engineer memory and context management - conversational state, persistent memory, retrieval-aware context assembly, and token-efficient context selection.
3. Apply modern context-delivery patterns (e.g., MCP-style tool/context interfaces) so agents access the right information at the right time.

### Reliability, evaluation & safety

1. Implement observability and tracing for prompts, tool calls, retrieval quality, agent traces, failures, drift, latency, and production behavior.
2. Apply guardrails, safety controls, and failure-handling to reduce hallucinations and unsafe actions.
3. Evaluate agents at the trajectory and task level - multi-step task success, failure-mode and regression analysis, and sandboxed test environments - alongside retrieval- and generation-quality metrics, automated checks, and human review.
4. Engineer healthcare-grade safety - deployment eval gates, human-oversight and escalation models, auditability and traceability for regulated decisions, and PHI/HIPAA-aware data handling.

### Integration & production craft

1. Build integrations with internal and external tools, APIs, enterprise systems, databases, and model providers so agents operate safely within real business workflows.
2. Deliver production-quality code with strong practices in testing, CI/CD, logging, versioning, and documentation; make architecture decisions that balance quality, safety, latency, cost, and model risk.
3. Partner with modeling and post-training engineers to improve model behavior for tool use, grounding, and long-horizon reasoning - through evaluation-driven feedback and, where it helps, fine-tuned or reasoning-optimized models.
4. Translate ambiguous, high-complexity operational processes into robust system logic and reusable AI patterns; stay current with advances in agentic systems and translate research into practical engineering decisions.

## Required Qualifications

- Bachelor's degree in Computer Science, Engineering, Data Science, Computational Linguistics, or a related field.
- Demonstrated depth building and shipping production agentic systems as a primary craft; shipped systems, research, model releases and open source weigh more than years in a title.
- Hands-on experience building production agent systems with modern orchestration - LangGraph/LangChain or equivalent, including custom orchestration.
- Experience designing and optimizing end-to-end RAG systems: indexing, retrieval, reranking, grounding, and evaluation.
- Strong understanding of memory and context management, including context windows, retrieval-driven context assembly, persistent memory, and high-signal context selection.
- Deep, practical understanding of LLM behavior - strengths, limitations, hallucination risks, reasoning constraints, and latency/cost trade-offs - and the evaluation methods used to measure them.
- Experience evaluating and debugging agent behavior - task-success and trajectory analysis, not just output quality.
- Strong Python engineering skills and modern software practices: testing, CI/CD, version control, and API integration; observability, tracing, and debugging for LLM-based systems in production.
- Hands-on experience with at least one frontier model platform and/or open-weight/self-hosted models, including production tool use and agent capabilities.

## Preferred Qualifications

- Experience with multi-agent systems and agent collaboration patterns.
- Familiarity with vector databases and retrieval infrastructure.
- Exposure to model adaptation and fine-tuning techniques such as LoRA or QLoRA.
- Understanding of traditional NLP concepts: tokenization, semantic similarity, entity extraction, summarization, and transformer fundamentals.
- Experience in highly regulated, high-stakes environments; healthcare exposure (clinical, payer, or life-sciences workflows, or standards such as FHIR) is a plus, not a requirement.
- A habit of staying current with AI research, benchmarks, and emerging engineering patterns.
