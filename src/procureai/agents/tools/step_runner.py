"""Executes one workflow step with a timeout, bounded retries and persisted step events.

Only transient failures (external services, timeouts) are retried. Deterministic application errors fail fast.
Each attempt is recorded as an ``AgentStep`` so the UI can show real progress and failure reasons.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from procureai.application.context import AppContext
from procureai.infrastructure.database.models import AgentStep
from procureai.shared.enums import StepStatus
from procureai.shared.errors import AppError, ExternalServiceError
from procureai.shared.types import utcnow

logger = logging.getLogger(__name__)
_seq_lock = Lock()
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="procureai-step")


@dataclass
class RunContext:
    app: AppContext
    session_factory: sessionmaker[Session]
    run_id: str
    project_id: str
    actor_id: str | None = None


@dataclass
class StepOutcome:
    ok: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def _transient(exc: BaseException) -> bool:
    return isinstance(exc, (ExternalServiceError, FutureTimeout, TimeoutError))


def _safe_message(exc: BaseException) -> str:
    if isinstance(exc, AppError):
        return exc.message
    if isinstance(exc, (FutureTimeout, TimeoutError)):
        return "The step timed out."
    return "An unexpected error occurred. See server logs for the run id."


def run_step(ctx: RunContext, name: str, fn: Callable[[Session], dict[str, Any] | None]) -> StepOutcome:
    settings = ctx.app.settings
    attempts = 1 + max(0, settings.workflow_step_max_retries)
    last_error = ""
    for attempt in range(1, attempts + 1):
        with _seq_lock, ctx.session_factory() as s:
            seq = (s.scalar(select(func.max(AgentStep.sequence)).where(AgentStep.run_id == ctx.run_id)) or 0) + 1
            step = AgentStep(
                run_id=ctx.run_id, sequence=seq, name=name, attempt=attempt, status=StepStatus.RUNNING.value
            )
            s.add(step)
            s.commit()
            step_id = step.id
        started = time.monotonic()

        def work() -> dict[str, Any] | None:
            with ctx.session_factory() as ws:
                try:
                    result = fn(ws)
                    ws.commit()
                    return result
                except Exception:
                    ws.rollback()
                    raise

        error: BaseException | None = None
        meta: dict[str, Any] = {}
        future = _pool.submit(work)
        try:
            meta = future.result(timeout=settings.workflow_step_timeout_seconds) or {}
        except BaseException as exc:  # noqa: BLE001 - recorded, classified and (if transient) retried
            error = exc
            if isinstance(exc, FutureTimeout):
                future.cancel()
            if not isinstance(exc, AppError):
                logger.exception("Workflow step failed", extra={"step": name, "attempt": attempt})
        duration = int((time.monotonic() - started) * 1000)
        with ctx.session_factory() as s:
            step = s.get(AgentStep, step_id)
            step.finished_at, step.duration_ms = utcnow(), duration
            if error is None:
                step.status, step.step_metadata = StepStatus.SUCCEEDED.value, meta
            else:
                last_error = _safe_message(error)
                step.status, step.error = StepStatus.FAILED.value, last_error
                step.step_metadata = {"will_retry": _transient(error) and attempt < attempts}
            s.commit()
        if error is None:
            return StepOutcome(True, meta)
        if not _transient(error) or attempt == attempts:
            break
        time.sleep(min(0.2 * attempt, 1.0))
    return StepOutcome(False, error=f"{name}: {last_error}")
