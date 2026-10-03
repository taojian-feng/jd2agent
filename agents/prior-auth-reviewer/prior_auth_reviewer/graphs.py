"""LangGraph wiring of the case workflow. Nodes and routing come from workflows.py.

Per-run resources go in config["configurable"] (client, recorder, library, llm, approver, memory).
"""
import inspect

from langgraph.graph import END, START, StateGraph

from prior_auth_reviewer import workflows as wf


def _wrap(fn):
    if inspect.iscoroutinefunction(fn):
        async def node(state, config):
            return await fn(state, config.get("configurable", {}))
    else:
        def node(state, config):
            return fn(state, config.get("configurable", {}))
    node.__name__ = fn.__name__
    return node


def case_graph(with_critic: bool = True):
    g = StateGraph(wf.CaseState)
    edge_map = wf.edges(with_critic)
    for name, fn in wf.NODES.items():
        if name == "critique" and not with_critic:
            continue
        g.add_node(name, _wrap(fn))
    g.add_edge(START, "intake")
    for src, dst in edge_map.items():
        if src == "critique" and not with_critic:
            continue
        if callable(dst):
            targets = [t for t in wf.ROUTES[src] if with_critic or t != "critique"]
            g.add_conditional_edges(src, dst, targets)
        else:
            g.add_edge(src, END if dst == wf.END else dst)
    return g.compile()
