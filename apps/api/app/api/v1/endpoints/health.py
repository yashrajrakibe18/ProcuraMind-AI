from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import Ctx
from procureai.infrastructure.database.session import get_engine

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness")
def health() -> dict:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness: verifies essential dependencies (no secrets exposed)")
def ready(ctx: Ctx):
    checks: dict[str, bool] = {}
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False
    checks["document_storage"] = ctx.storage.writable()
    checks["vector_store"] = ctx.store.heartbeat()
    ok = all(checks.values())
    return JSONResponse(
        {
            "status": "ready" if ok else "degraded",
            "checks": checks,
            "llm": {"provider": ctx.llm.name, "configured": ctx.llm.available()},
        },
        status_code=200 if ok else 503,
    )
