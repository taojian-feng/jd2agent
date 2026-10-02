"""LangGraph wiring for W1 and W2. Nodes and routers come from workflows.py.

Per-run options go in config["configurable"]: {"llm": ..., "confirm": ...}.
"""
import inspect

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from ai_architect import workflows as wf


def _wrap(fn):
    if inspect.iscoroutinefunction(fn):
        async def node(state, config):
            return await fn(state, config.get("configurable", {}))
    else:
        def node(state, config):
            return fn(state, config.get("configurable", {}))
    node.__name__ = fn.__name__
    return node


def _build(state_type, nodes, edges, routes, start, checkpointer=None):
    g = StateGraph(state_type)
    for name, fn in nodes.items():
        g.add_node(name, _wrap(fn))
    g.add_edge(START, start)
    for src, dst in edges.items():
        if callable(dst):
            g.add_conditional_edges(src, dst, routes[src])
        else:
            g.add_edge(src, END if dst == wf.END else dst)
    return g.compile(checkpointer=checkpointer)


def solution_design_graph(checkpointer=None):
    return _build(wf.DesignState, wf.W1_NODES, wf.W1_EDGES, wf.W1_ROUTES, "extract_requirements",
                  checkpointer or InMemorySaver())


def architecture_review_graph(checkpointer=None):
    return _build(wf.ReviewState, wf.W2_NODES, wf.W2_EDGES, wf.W2_ROUTES, "load_design",
                  checkpointer or InMemorySaver())
