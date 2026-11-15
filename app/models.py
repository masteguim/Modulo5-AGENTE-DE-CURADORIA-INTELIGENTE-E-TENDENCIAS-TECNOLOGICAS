from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuarios"

    id_usuario: Mapped[int] = mapped_column(primary_key=True)
    identificador_externo: Mapped[str] = mapped_column(String(255), nullable=False)
    nome: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    chats: Mapped[list[Chat]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )
    integracoes_github: Mapped[list[IntegracaoGitHub]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "identificador_externo",
            name="uq_usuarios_identificador_externo",
        ),
    )


class Chat(Base):
    __tablename__ = "chats"

    id_chat: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="CASCADE"), nullable=False
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    usuario: Mapped[Usuario] = relationship(back_populates="chats")
    conteudos: Mapped[list[Conteudo]] = relationship(
        back_populates="chat", cascade="all, delete-orphan"
    )
    integracoes_github: Mapped[list[IntegracaoGitHub]] = relationship(
        back_populates="chat", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_chats_usuario_id", "usuario_id"),
        Index("ix_chats_project_id", "project_id"),
    )


class Conteudo(Base):
    __tablename__ = "conteudos"

    id_conteudo: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id_chat", ondelete="CASCADE"), nullable=False
    )
    pergunta: Mapped[str] = mapped_column(Text, nullable=False)
    resposta: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    chat: Mapped[Chat] = relationship(back_populates="conteudos")

    __table_args__ = (Index("ix_conteudos_chat_id", "chat_id"),)


class IntegracaoGitHub(Base):
    __tablename__ = "integracoes_github"

    id_github: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="CASCADE"), nullable=False
    )
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id_chat", ondelete="CASCADE"), nullable=False
    )
    repositorio_id_externo: Mapped[int | None] = mapped_column(BigInteger)
    repositorio_url: Mapped[str | None] = mapped_column(String(2048))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    usuario: Mapped[Usuario] = relationship(back_populates="integracoes_github")
    chat: Mapped[Chat] = relationship(back_populates="integracoes_github")
    tecnologias: Mapped[list[Tecnologia]] = relationship(
        back_populates="integracao_github", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_integracoes_github_usuario_id", "usuario_id"),
        Index("ix_integracoes_github_chat_id", "chat_id"),
    )


class Tecnologia(Base):
    __tablename__ = "tecnologias"

    id_tecnologia: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(
        ForeignKey("integracoes_github.id_github", ondelete="CASCADE"),
        nullable=False,
    )
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str | None] = mapped_column(String(100))

    integracao_github: Mapped[IntegracaoGitHub] = relationship(
        back_populates="tecnologias"
    )
    recomendacoes: Mapped[list[Recomendacao]] = relationship(
        back_populates="tecnologia", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("github_id", "nome", name="uq_tecnologias_github_nome"),
        Index("ix_tecnologias_github_id", "github_id"),
    )


class Recomendacao(Base):
    __tablename__ = "recomendacoes"

    id_recomendacao: Mapped[int] = mapped_column(primary_key=True)
    tecnologia_id: Mapped[int] = mapped_column(
        ForeignKey("tecnologias.id_tecnologia", ondelete="CASCADE"),
        nullable=False,
    )
    idioma: Mapped[str | None] = mapped_column(String(45))
    fonte: Mapped[str | None] = mapped_column(String(2048))
    titulo: Mapped[str] = mapped_column(String(1000), nullable=False)
    arquivo: Mapped[str | None] = mapped_column(String(2048))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tecnologia: Mapped[Tecnologia] = relationship(back_populates="recomendacoes")

    __table_args__ = (Index("ix_recomendacoes_tecnologia_id", "tecnologia_id"),)
