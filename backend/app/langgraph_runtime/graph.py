from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.langgraph_runtime.nodes import (
    execute_plan_node,
    plan_node,
    reduce_node,
    response_node,
    review_node,
    route_node,
)
from app.langgraph_runtime.state import GraphState


def build_plan_execution_graph():
    graph = StateGraph(GraphState)
    graph.add_node("route_node", route_node)
    graph.add_node("plan_node", plan_node)
    graph.add_node("execute_plan_node", execute_plan_node)
    graph.add_node("review_node", review_node)
    graph.add_node("reduce_node", reduce_node)
    graph.add_node("response_node", response_node)

    graph.add_edge(START, "route_node")
    graph.add_edge("route_node", "plan_node")
    graph.add_edge("plan_node", "execute_plan_node")
    graph.add_edge("execute_plan_node", "review_node")
    graph.add_edge("review_node", "reduce_node")
    graph.add_edge("reduce_node", "response_node")
    graph.add_edge("response_node", END)
    return graph.compile()


@lru_cache(maxsize=1)
def get_plan_execution_graph():
    return build_plan_execution_graph()
