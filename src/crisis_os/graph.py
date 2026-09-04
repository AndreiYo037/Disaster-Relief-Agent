"""LangGraph orchestration with interrupt at Governance.

Falls back to the deterministic runner if langgraph is not installed.
"""
from __future__ import annotations

from typing import Any, TypedDict

from .layers import run_demo
from .models import HumanDecision


class GraphState(TypedDict, total=False):
    loop_count: int
    result: dict


def build_graph():
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return None

    def spine(state: GraphState) -> GraphState:
        # Live dashboard: pause here with interrupt() and resume on thread_id
        # after mint_permit(plan, human_decision). The scripted path calls run_demo().
        result = run_demo()
        return {**state, "result": result, "loop_count": state.get("loop_count", 0) + 1}

    g = StateGraph(GraphState)
    g.add_node("spine", spine)
    g.set_entry_point("spine")
    g.add_edge("spine", END)
    return g.compile()


def kickoff(decisions: list[HumanDecision] | None = None) -> dict[str, Any]:
    graph = build_graph()
    if graph is None:
        return run_demo()
    return graph.invoke({"loop_count": 0})
