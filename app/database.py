import os
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, cast, create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.models import Artigo

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _get_engine() -> Engine:
    global _engine

    if _engine is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("Configure DATABASE_URL com a conexão do PostgreSQL.")
        if make_url(database_url).drivername != "postgresql+psycopg":
            raise RuntimeError(
                "DATABASE_URL deve usar PostgreSQL com o driver psycopg."
            )

        _engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=1800,
        )

    return _engine


def _get_session_factory() -> sessionmaker[Session]:
    global _session_factory

    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=_get_engine(),
            autoflush=False,
            expire_on_commit=False,
        )

    return _session_factory


def get_db() -> Iterator[Session]:
    database = _get_session_factory()()
    try:
        yield database
    finally:
        database.close()


def inicializar_banco() -> None:
    with _get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


def salvar_artigo(artigo: dict[str, Any]) -> bool:
    titulo = str(artigo.get("titulo", "")).strip()
    link = str(artigo.get("link", "")).strip()
    if not titulo or not link.startswith("https://"):
        return False

    statement = (
        insert(Artigo)
        .values(
            titulo=titulo,
            link=link,
            fonte=artigo.get("fonte", "Desconhecida"),
            idioma=artigo.get("idioma", "en"),
            resumo=artigo.get("resumo", ""),
            data_publicacao=artigo.get("data_publicacao"),
            coletado_em=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=[Artigo.link])
        .returning(Artigo.id)
    )

    with _get_session_factory().begin() as database:
        return database.scalar(statement) is not None


def salvar_artigos(artigos: Sequence[dict[str, Any]]) -> dict[str, int]:
    novos = sum(salvar_artigo(artigo) for artigo in artigos)
    return {
        "recebidos": len(artigos),
        "novos": novos,
        "duplicados_ou_invalidos": len(artigos) - novos,
    }


def _ordem_artigos():
    return func.coalesce(
        Artigo.data_publicacao,
        cast(Artigo.coletado_em, String),
    ).desc()


def _artigo_para_dict(artigo: Artigo) -> dict[str, Any]:
    return {
        "id": artigo.id,
        "titulo": artigo.titulo,
        "link": artigo.link,
        "fonte": artigo.fonte,
        "idioma": artigo.idioma,
        "resumo": artigo.resumo,
        "data_publicacao": artigo.data_publicacao,
        "coletado_em": artigo.coletado_em.isoformat(),
    }


def listar_artigos(limite: int = 50) -> list[dict[str, Any]]:
    limite = max(1, min(int(limite), 500))
    with _get_session_factory()() as database:
        artigos = database.scalars(
            select(Artigo).order_by(_ordem_artigos()).limit(limite)
        ).all()
    return [_artigo_para_dict(artigo) for artigo in artigos]


def contar_artigos() -> int:
    with _get_session_factory()() as database:
        total = database.scalar(select(func.count()).select_from(Artigo))
    return int(total or 0)


def buscar_artigos_por_termo(termo: str, limite: int = 50) -> list[dict[str, Any]]:
    limite = max(1, min(int(limite), 500))
    termo_busca = f"%{termo.strip()}%"
    statement = (
        select(Artigo)
        .where(Artigo.titulo.ilike(termo_busca) | Artigo.resumo.ilike(termo_busca))
        .order_by(_ordem_artigos())
        .limit(limite)
    )
    with _get_session_factory()() as database:
        artigos = database.scalars(statement).all()
    return [_artigo_para_dict(artigo) for artigo in artigos]
