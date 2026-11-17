"""Platform tables (organizations, conversations, agent tasks, workflows, notifications, webhooks, usage) and project org/domain."""

import sqlalchemy as sa
from alembic import op

revision = "0002_platform"
down_revision = "0001"
branch_labels = None
depends_on = None

NEW_TABLES = [
    "organizations", "memberships", "conversations", "messages", "agent_tasks",
    "workflows", "workflow_runs", "notifications", "webhooks", "usage_events",
]


def upgrade() -> None:
    from procureai.infrastructure.database.models import Base

    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())
    for name in NEW_TABLES:
        if name not in existing:
            Base.metadata.tables[name].create(bind)
    cols = {c["name"] for c in insp.get_columns("projects")}
    with op.batch_alter_table("projects") as batch:
        if "org_id" not in cols:
            batch.add_column(sa.Column("org_id", sa.String(32), nullable=True))
        if "domain" not in cols:
            batch.add_column(sa.Column("domain", sa.String(32), nullable=False, server_default="general"))
    if "ix_projects_org_id" not in {i["name"] for i in insp.get_indexes("projects")}:
        op.create_index("ix_projects_org_id", "projects", ["org_id"])


def downgrade() -> None:
    from procureai.infrastructure.database.models import Base

    bind = op.get_bind()
    for name in reversed(NEW_TABLES):
        Base.metadata.tables[name].drop(bind, checkfirst=True)
    op.drop_index("ix_projects_org_id", table_name="projects")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("domain")
        batch.drop_column("org_id")
