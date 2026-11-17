"""Agent contracts: spec (responsibility, tools, permissions, limits), execution context and standard output."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from procureai.application.context import AppContext
from procureai.infrastructure.database.models import ProcurementProject, User
from procureai.shared.errors import PermissionDeniedError

# Permissions an agent may hold. "external_send" and "irreversible" are never granted to any agent.
PERMISSIONS = ("read", "write_results", "notify", "generate_files")


@dataclass
class Result:
    """Standard agent output. ``sections`` are rendered generically by the UI (text, bullets, table, chart, kv, draft)."""

    summary: str
    sections: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    status: str = "completed"  # completed | needs_input | awaiting_approval
    needs_input: str | None = None
    llm_calls: int = 0
    labels: dict[str, str] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "sections": self.sections,
            "evidence": self.evidence,
            "needs_input": self.needs_input,
            "labels": self.labels,
            "data": self.data,
        }


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    domain: str
    description: str
    handler: Callable[[AgentContext], Result]
    tools: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ("read",)
    input_schema: dict[str, str] = field(default_factory=dict)
    output: str = "Standard result: summary, sections, evidence, needs_input"
    requires_project: bool = True
    requires_approval: bool = False
    writes: bool = False  # needs project write access
    timeout_s: int = 120
    max_retries: int = 1
    example: str = ""
    platform: str = "core"

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "tools": list(self.tools),
            "permissions": list(self.permissions),
            "input_schema": self.input_schema,
            "output": self.output,
            "requires_approval": self.requires_approval,
            "requires_project": self.requires_project,
            "timeout_s": self.timeout_s,
            "max_retries": self.max_retries,
            "example": self.example,
            "can_send_external": False,
            "writes": self.writes,
            "platform": self.platform,
        }


@dataclass
class AgentContext:
    session: Session
    app: AppContext
    user: User
    project: ProcurementProject | None
    params: dict[str, Any]
    spec: AgentSpec
    task_id: str | None = None
    tools_used: list[str] = field(default_factory=list)
    llm_used: int = 0

    def tool(self, name: str) -> Callable[..., Any]:
        """Return a registered tool, enforcing that this agent declared it and holds the needed permission."""
        from procureai.agents.suite.tools import TOOLS

        tool = TOOLS.get(name)
        if tool is None or name not in self.spec.tools:
            raise PermissionDeniedError(f"Agent '{self.spec.id}' is not allowed to use tool '{name}'.")
        if tool.permission not in self.spec.permissions:
            raise PermissionDeniedError(f"Agent '{self.spec.id}' lacks the '{tool.permission}' permission.")
        self.tools_used.append(name)
        return lambda *a, **kw: tool.fn(self, *a, **kw)
