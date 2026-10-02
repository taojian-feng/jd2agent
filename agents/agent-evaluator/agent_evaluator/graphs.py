"""LangGraph wiring for W3. Nodes and edges come from workflows.py.

Per-run options go in config["configurable"]: {"llm": ..., "concurrency": ...}.
"""
import inspect

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agent_evaluator import workflows as wf


def _wrap(fn):
    if inspect.iscoroutinefunction(fn):
        async def node(state, config):
            return await fn(state, config.get("configurable", {}))
    else:
        def node(state, config):
            return fn(state, config.get("configurable", {}))
    node.__name__ = fn.__name__
    return node


def trajectory_eval_graph(checkpointer=None):
    g = StateGraph(wf.EvalState)
    for name, fn in wf.W3_NODES.items():
        g.add_node(name, _wrap(fn))
    g.add_edge(START, "load_traces")
    for src, dst in wf.W3_EDGES.items():
        g.add_edge(src, END if dst == wf.END else dst)
    return g.compile(checkpointer=checkpointer or InMemorySaver())
