from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError


def test_migrations_apply_and_match_models(env, monkeypatch):
    """`alembic upgrade head` must produce exactly the schema the ORM models describe."""
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    try:
        command.check(cfg)  # raises if models and migrations diverge
    except CommandError as exc:  # pragma: no cover - failure message
        raise AssertionError(f"Models and migrations differ: {exc}") from exc
    command.downgrade(cfg, "base")
