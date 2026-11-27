"""Remove unused columns from the application schema.

Revision ID: 0004_remove_unused_columns
Revises: 0003_integrate_user_workflows
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_remove_unused_columns"
down_revision: str | None = "0003_integrate_user_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_artigos_publicacao", table_name="artigos")
    op.drop_column("usuarios", "nome")
    op.drop_column("usuarios", "email")
    op.drop_column("integracoes_github", "repositorio_id_externo")
    op.drop_column("tecnologias", "tipo")


def downgrade() -> None:
    op.create_index(
        "idx_artigos_publicacao",
        "artigos",
        ["data_publicacao"],
    )
    op.add_column(
        "tecnologias",
        sa.Column("tipo", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "integracoes_github",
        sa.Column("repositorio_id_externo", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "usuarios",
        sa.Column("email", sa.String(length=320), nullable=True),
    )
    op.add_column(
        "usuarios",
        sa.Column("nome", sa.String(length=255), nullable=True),
    )
