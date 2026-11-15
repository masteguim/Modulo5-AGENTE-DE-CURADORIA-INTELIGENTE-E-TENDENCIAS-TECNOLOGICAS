"""Create persistent article storage.

Revision ID: 0002_create_artigos_table
Revises: 0001_create_curadoria_schema
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_create_artigos_table"
down_revision: str | None = "0001_create_curadoria_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artigos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("titulo", sa.String(length=1000), nullable=False),
        sa.Column("link", sa.String(length=2048), nullable=False),
        sa.Column("fonte", sa.String(length=255), nullable=False),
        sa.Column("idioma", sa.String(length=45), nullable=False),
        sa.Column("resumo", sa.Text(), nullable=False),
        sa.Column("data_publicacao", sa.String(length=100), nullable=True),
        sa.Column(
            "coletado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("link", name="uq_artigos_link"),
    )
    op.create_index(
        "idx_artigos_publicacao",
        "artigos",
        ["data_publicacao"],
    )


def downgrade() -> None:
    op.drop_index("idx_artigos_publicacao", table_name="artigos")
    op.drop_table("artigos")
