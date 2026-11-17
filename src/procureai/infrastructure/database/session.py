"""Engine/session management. A lazily-created singleton keyed to current settings."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from procureai.config.settings import get_settings
from procureai.infrastructure.database.models import Base

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def _build_engine(url: str) -> Engine:
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk_pragma(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return engine


def get_engine() -> Engine:
    global _engine, _factory
    if _engine is None:
        settings = get_settings()
        settings.ensure_directories()
        _engine = _build_engine(settings.database_url)
        _factory = sessionmaker(bind=_engine, expire_on_commit=False, class_=Session)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _factory is not None
    return _factory


def init_db() -> None:
    """Create tables. Production deployments should use Alembic migrations (see docs/setup.md)."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    _upgrade_columns(engine)


def _upgrade_columns(engine: Engine) -> None:
    """Dev convenience: add columns introduced after a database was first created (Alembic is the production path)."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "projects" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("projects")}
    with engine.begin() as conn:
        if "org_id" not in have:
            conn.execute(text("ALTER TABLE projects ADD COLUMN org_id VARCHAR(32)"))
        if "domain" not in have:
            conn.execute(text("ALTER TABLE projects ADD COLUMN domain VARCHAR(32) DEFAULT 'general' NOT NULL"))


def reset_database_state() -> None:
    """Dispose the engine so a fresh one is built from current settings (used by tests)."""
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _factory = None


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def db_session_dependency() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
