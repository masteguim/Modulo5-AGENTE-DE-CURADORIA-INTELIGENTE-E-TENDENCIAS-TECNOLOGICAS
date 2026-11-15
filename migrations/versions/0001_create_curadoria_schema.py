"""Create the curation relational schema.

Revision ID: 0001_create_curadoria_schema
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_create_curadoria_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id_usuario", sa.Integer(), primary_key=True),
        sa.Column("identificador_externo", sa.String(length=255), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "identificador_externo", name="uq_usuarios_identificador_externo"
        ),
    )
    op.create_table(
        "chats",
        sa.Column("id_chat", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id_usuario"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_chats_usuario_id", "chats", ["usuario_id"])
    op.create_index("ix_chats_project_id", "chats", ["project_id"])

    op.create_table(
        "conteudos",
        sa.Column("id_conteudo", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("pergunta", sa.Text(), nullable=False),
        sa.Column("resposta", sa.Text(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id_chat"], ondelete="CASCADE"),
    )
    op.create_index("ix_conteudos_chat_id", "conteudos", ["chat_id"])

    op.create_table(
        "integracoes_github",
        sa.Column("id_github", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("repositorio_id_externo", sa.BigInteger(), nullable=True),
        sa.Column("repositorio_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id_usuario"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id_chat"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_integracoes_github_usuario_id", "integracoes_github", ["usuario_id"]
    )
    op.create_index("ix_integracoes_github_chat_id", "integracoes_github", ["chat_id"])

    op.create_table(
        "tecnologias",
        sa.Column("id_tecnologia", sa.Integer(), primary_key=True),
        sa.Column("github_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("tipo", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["github_id"], ["integracoes_github.id_github"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("github_id", "nome", name="uq_tecnologias_github_nome"),
    )
    op.create_index("ix_tecnologias_github_id", "tecnologias", ["github_id"])

    op.create_table(
        "recomendacoes",
        sa.Column("id_recomendacao", sa.Integer(), primary_key=True),
        sa.Column("tecnologia_id", sa.Integer(), nullable=False),
        sa.Column("idioma", sa.String(length=45), nullable=True),
        sa.Column("fonte", sa.String(length=2048), nullable=True),
        sa.Column("titulo", sa.String(length=1000), nullable=False),
        sa.Column("arquivo", sa.String(length=2048), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tecnologia_id"], ["tecnologias.id_tecnologia"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_recomendacoes_tecnologia_id", "recomendacoes", ["tecnologia_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_recomendacoes_tecnologia_id", table_name="recomendacoes")
    op.drop_table("recomendacoes")
    op.drop_index("ix_tecnologias_github_id", table_name="tecnologias")
    op.drop_table("tecnologias")
    op.drop_index("ix_integracoes_github_chat_id", table_name="integracoes_github")
    op.drop_index("ix_integracoes_github_usuario_id", table_name="integracoes_github")
    op.drop_table("integracoes_github")
    op.drop_index("ix_conteudos_chat_id", table_name="conteudos")
    op.drop_table("conteudos")
    op.drop_index("ix_chats_project_id", table_name="chats")
    op.drop_index("ix_chats_usuario_id", table_name="chats")
    op.drop_table("chats")
    op.drop_table("usuarios")
