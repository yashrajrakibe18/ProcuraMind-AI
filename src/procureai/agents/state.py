"""Typed LangGraph state. Only what the workflow needs; heavy data stays in the database."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class WorkflowState(TypedDict, total=False):
    run_id: str
    project_id: str
    auto_confirm: bool
    # progress flags set by workers; the supervisor routes on them
    documents_valid: bool
    extraction_done: bool
    vendors_done: bool
    compliance_done: bool
    price_done: bool
    evidence_done: bool
    verified: bool
    # accumulated across parallel branches
    errors: Annotated[list[str], operator.add]
    notes: Annotated[list[str], operator.add]
    metrics: Annotated[dict[str, Any], lambda a, b: {**(a or {}), **(b or {})}]
    next_hops: int
