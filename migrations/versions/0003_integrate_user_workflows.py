"""Persist M7 conversations and project GitHub integrations.

Revision ID: 0003_integrate_user_workflows
Revises: 0002_create_artigos_table
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_integrate_user_workflows"
down_revision: str | None = "0002_create_artigos_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chats",
        sa.Column("m7_conversation_id", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_chats_m7_conversation_id",
        "chats",
        ["m7_conversation_id"],
    )
    op.add_column(
        "integracoes_github",
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_integracoes_github_project_id",
        "integracoes_github",
        ["project_id"],
    )
    op.create_unique_constraint(
        "uq_integracoes_github_project_url",
        "integracoes_github",
        ["project_id", "repositorio_url"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_integracoes_github_project_url",
        "integracoes_github",
        type_="unique",
    )
    op.drop_index(
        "ix_integracoes_github_project_id",
        table_name="integracoes_github",
    )
    op.drop_column("integracoes_github", "project_id")
    op.drop_constraint(
        "uq_chats_m7_conversation_id",
        "chats",
        type_="unique",
    )
    op.drop_column("chats", "m7_conversation_id")
