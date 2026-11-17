"""Supervisor-orchestrated LangGraph workflow.

validate -> document intelligence -> vendor analysis -> (technical compliance || price intelligence)
         -> procurement RAG -> verification -> finalize

The supervisor inspects typed state after each worker and picks the next node. Compliance and price analysis fan out
in parallel only once validated inputs exist. The graph is bounded by a hop counter and LangGraph's recursion limit,
and any recorded error routes straight to ``finalize``.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from procureai.agents.nodes.workers import make_nodes
from procureai.agents.state import WorkflowState
from procureai.agents.tools.step_runner import RunContext

MAX_HOPS = 12
WORKFLOW_VERSION = "1.0"


def supervisor_route(state: WorkflowState) -> str | list[str]:
    """Pure routing function (unit-testable)."""
    if state.get("errors") or state.get("next_hops", 0) > MAX_HOPS:
        return "finalize"
    if not state.get("documents_valid"):
        return "validate_documents"
    if not state.get("extraction_done"):
        return "document_intelligence"
    if not state.get("vendors_done"):
        return "vendor_analysis"
    parallel = [
        n
        for n, done in (
            ("technical_compliance", state.get("compliance_done")),
            ("price_intelligence", state.get("price_done")),
        )
        if not done
    ]
    if parallel:
        return parallel
    if not state.get("evidence_done"):
        return "procurement_rag"
    if not state.get("verified"):
        return "verification"
    return "finalize"


def build_workflow(ctx: RunContext, finalize_fn):
    nodes = make_nodes(ctx)
    graph = StateGraph(WorkflowState)

    def supervisor(state: WorkflowState) -> dict[str, Any]:
        return {"next_hops": state.get("next_hops", 0) + 1}

    graph.add_node("supervisor", supervisor)
    for name, fn in nodes.items():
        graph.add_node(name, fn)
    graph.add_node("finalize", finalize_fn)

    graph.add_edge(START, "supervisor")
    targets = {n: n for n in nodes} | {"finalize": "finalize"}
    graph.add_conditional_edges("supervisor", supervisor_route, targets)
    for name in nodes:
        graph.add_edge(name, "supervisor")
    graph.add_edge("finalize", END)
    return graph.compile()
