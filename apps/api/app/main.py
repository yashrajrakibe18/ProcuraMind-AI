"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.errors import register_error_handlers
from app.middleware.request_context import RequestContextMiddleware
from procureai.application.context import get_context
from procureai.config.logging import configure_logging
from procureai.config.settings import get_settings
from procureai.infrastructure.database.session import init_db

logger = logging.getLogger(__name__)


async def _scheduler_loop(ctx) -> None:
    """Optional in-process scheduler (SCHEDULER_ENABLED=true). Single-process only; use an external cron for multi-replica."""
    from procureai.agents.suite.orchestrator import run_due_workflows

    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(run_due_workflows, ctx)
        except Exception:  # never let the loop die
            logger.exception("scheduler tick failed")


WEB_DIR = Path(__file__).resolve().parents[2] / "web_next"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.ensure_directories()
        if settings.auto_create_tables:
            init_db()
        ctx = get_context()
        logger.info("ProcuraMind API started", extra={"env": settings.app_env, "llm_provider": settings.llm_provider})
        task = asyncio.create_task(_scheduler_loop(ctx)) if settings.scheduler_enabled else None
        yield
        if task:
            task.cancel()

    app = FastAPI(
        title=f"{settings.app_name} API",
        version="1.0.0",
        lifespan=lifespan,
        description="Agentic AI procurement intelligence and decision-support API. "
        "Decision support only: humans retain approval responsibility.",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Location"],
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.include_router(health.router)  # unversioned /health and /ready for container probes
    if WEB_DIR.is_dir():
        app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")

        @app.get("/", include_in_schema=False)
        def root():
            return RedirectResponse("/app/")

    return app


app = create_app()
