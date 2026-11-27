import json
import os
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import String, cast, create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Artigo,
    Chat,
    Conteudo,
    IntegracaoGitHub,
    Recomendacao,
    Tecnologia,
    Usuario,
)

load_dotenv()

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


def _obter_ou_criar_usuario(database: Session, subject: str) -> Usuario:
    database.execute(
        insert(Usuario)
        .values(identificador_externo=subject)
        .on_conflict_do_nothing(
            index_elements=[Usuario.identificador_externo]
        )
    )
    usuario = database.scalar(
        select(Usuario).where(
            Usuario.identificador_externo == subject
        )
    )
    if usuario is None:
        raise RuntimeError("Não foi possível registrar o usuário autenticado.")
    return usuario


def _conversa_do_usuario(
    database: Session,
    usuario: Usuario,
    chat_id: int,
) -> Chat | None:
    return database.scalar(
        select(Chat).where(
            Chat.id_chat == chat_id,
            Chat.usuario_id == usuario.id_usuario,
        )
    )


def registrar_consulta(
    subject: str,
    pergunta: str,
    resposta: str,
    project_id: UUID | None = None,
    chat_id: int | None = None,
) -> int:
    with _get_session_factory().begin() as database:
        usuario = _obter_ou_criar_usuario(database, subject)

        if chat_id is None:
            chat = Chat(
                usuario_id=usuario.id_usuario,
                titulo=pergunta[:255],
                project_id=project_id,
            )
            database.add(chat)
            database.flush()
        else:
            chat = _conversa_do_usuario(database, usuario, chat_id)
            if chat is None:
                raise LookupError("Conversa não encontrada.")
            if project_id and chat.project_id != project_id:
                raise ValueError(
                    "A conversa não pertence ao projeto informado."
                )

        database.add(
            Conteudo(
                chat_id=chat.id_chat,
                pergunta=pergunta,
                resposta=resposta,
            )
        )
        chat.atualizado_em = datetime.now(UTC)
        return chat.id_chat


def obter_contexto_conversa(
    subject: str,
    chat_id: int,
) -> dict[str, Any] | None:
    with _get_session_factory()() as database:
        usuario = database.scalar(
            select(Usuario).where(
                Usuario.identificador_externo == subject
            )
        )
        if usuario is None:
            return None

        chat = _conversa_do_usuario(database, usuario, chat_id)
        if chat is None:
            return None

        return {
            "id_chat": chat.id_chat,
            "project_id": chat.project_id,
            "m7_conversation_id": chat.m7_conversation_id,
        }


def registrar_resposta_assistente(
    subject: str,
    pergunta: str,
    resposta: str,
    m7_conversation_id: str,
    project_id: UUID | None = None,
    chat_id: int | None = None,
) -> int:
    with _get_session_factory().begin() as database:
        usuario = _obter_ou_criar_usuario(database, subject)

        if chat_id is None:
            chat = Chat(
                usuario_id=usuario.id_usuario,
                titulo=pergunta[:255],
                project_id=project_id,
                m7_conversation_id=m7_conversation_id,
            )
            database.add(chat)
            database.flush()
        else:
            chat = _conversa_do_usuario(database, usuario, chat_id)
            if chat is None:
                raise LookupError("Conversa não encontrada.")
            if project_id and chat.project_id != project_id:
                raise ValueError(
                    "A conversa não pertence ao projeto informado."
                )
            if (
                chat.m7_conversation_id
                and chat.m7_conversation_id != m7_conversation_id
            ):
                raise ValueError(
                    "A conversa externa do Módulo 7 não corresponde."
                )
            chat.m7_conversation_id = m7_conversation_id

        database.add(
            Conteudo(
                chat_id=chat.id_chat,
                pergunta=pergunta,
                resposta=resposta,
            )
        )
        chat.atualizado_em = datetime.now(UTC)
        return chat.id_chat


def listar_conversas(
    subject: str,
    project_id: UUID | None = None,
    limite: int = 50,
) -> list[dict[str, Any]]:
    statement = (
        select(Chat)
        .join(Usuario, Chat.usuario_id == Usuario.id_usuario)
        .where(Usuario.identificador_externo == subject)
        .where(Chat.conteudos.any())
        .order_by(Chat.atualizado_em.desc(), Chat.id_chat.desc())
        .limit(max(1, min(int(limite), 100)))
    )
    if project_id:
        statement = statement.where(Chat.project_id == project_id)
    else:
        statement = statement.where(Chat.project_id.is_(None))

    with _get_session_factory()() as database:
        chats = database.scalars(statement).all()
        return [
            {
                "chat_id": chat.id_chat,
                "titulo": chat.titulo,
                "project_id": (
                    str(chat.project_id) if chat.project_id else None
                ),
                "criado_em": chat.criado_em.isoformat(),
                "atualizado_em": chat.atualizado_em.isoformat(),
            }
            for chat in chats
        ]


def obter_conversa(
    subject: str,
    chat_id: int,
) -> dict[str, Any] | None:
    with _get_session_factory()() as database:
        usuario = database.scalar(
            select(Usuario).where(
                Usuario.identificador_externo == subject
            )
        )
        if usuario is None:
            return None
        chat = _conversa_do_usuario(database, usuario, chat_id)
        if chat is None:
            return None

        conteudos = database.scalars(
            select(Conteudo)
            .where(Conteudo.chat_id == chat.id_chat)
            .order_by(Conteudo.criado_em, Conteudo.id_conteudo)
        ).all()

        def decodificar_resposta(resposta: str | None) -> Any:
            if resposta is None:
                return None
            try:
                return json.loads(resposta)
            except json.JSONDecodeError:
                return resposta

        return {
            "chat_id": chat.id_chat,
            "titulo": chat.titulo,
            "project_id": (
                str(chat.project_id) if chat.project_id else None
            ),
            "mensagens": [
                {
                    "id": conteudo.id_conteudo,
                    "pergunta": conteudo.pergunta,
                    "resposta": decodificar_resposta(conteudo.resposta),
                    "criado_em": conteudo.criado_em.isoformat(),
                }
                for conteudo in conteudos
            ],
        }


def salvar_repositorio_projeto(
    subject: str,
    project_id: UUID,
    repositorio_url: str,
    stack: Sequence[str],
    recomendacoes: dict[str, Sequence[dict[str, Any]]],
) -> dict[str, int]:
    with _get_session_factory().begin() as database:
        usuario = _obter_ou_criar_usuario(database, subject)
        integracao = database.scalar(
            select(IntegracaoGitHub).where(
                IntegracaoGitHub.project_id == project_id,
                IntegracaoGitHub.repositorio_url == repositorio_url,
            )
        )

        if integracao is None:
            chat = Chat(
                usuario_id=usuario.id_usuario,
                titulo=f"GitHub: {repositorio_url.rsplit('/', 1)[-1]}"[:255],
                project_id=project_id,
            )
            database.add(chat)
            database.flush()
            integracao = IntegracaoGitHub(
                usuario_id=usuario.id_usuario,
                chat_id=chat.id_chat,
                project_id=project_id,
                repositorio_url=repositorio_url,
            )
            database.add(integracao)
            database.flush()
        else:
            for tecnologia in list(integracao.tecnologias):
                database.delete(tecnologia)
            database.flush()

        total_recomendacoes = 0
        for nome in dict.fromkeys(stack):
            tecnologia = Tecnologia(
                github_id=integracao.id_github,
                nome=nome,
            )
            database.add(tecnologia)
            database.flush()
            for artigo in recomendacoes.get(nome, []):
                database.add(
                    Recomendacao(
                        tecnologia_id=tecnologia.id_tecnologia,
                        idioma=artigo.get("idioma"),
                        fonte=artigo.get("fonte"),
                        titulo=artigo["titulo"],
                        arquivo=artigo["link"],
                    )
                )
                total_recomendacoes += 1

        return {
            "github_id": integracao.id_github,
            "tecnologias": len(set(stack)),
            "recomendacoes": total_recomendacoes,
        }


def listar_recomendacoes_projeto(
    project_id: UUID,
) -> list[dict[str, Any]]:
    statement = (
        select(Recomendacao, Tecnologia)
        .join(Tecnologia, Recomendacao.tecnologia_id == Tecnologia.id_tecnologia)
        .join(
            IntegracaoGitHub,
            Tecnologia.github_id == IntegracaoGitHub.id_github,
        )
        .where(
            IntegracaoGitHub.project_id == project_id,
        )
        .order_by(Recomendacao.criado_em.desc())
    )

    with _get_session_factory()() as database:
        rows = database.execute(statement).all()
        return [
            {
                "tecnologia": tecnologia.nome,
                "titulo": recomendacao.titulo,
                "idioma": recomendacao.idioma,
                "fonte": recomendacao.fonte,
                "link": recomendacao.arquivo,
                "criado_em": recomendacao.criado_em.isoformat(),
            }
            for recomendacao, tecnologia in rows
        ]


def listar_repositorios_projeto(
    project_id: UUID,
) -> list[dict[str, Any]]:
    statement = (
        select(IntegracaoGitHub)
        .join(Chat, IntegracaoGitHub.chat_id == Chat.id_chat)
        .where(
            IntegracaoGitHub.project_id == project_id,
        )
        .order_by(IntegracaoGitHub.criado_em.desc())
    )

    with _get_session_factory()() as database:
        integrations = database.scalars(statement).all()
        return [
            {
                "repositorio": integracao.repositorio_url,
                "stack_detectada": [
                    tecnologia.nome
                    for tecnologia in integracao.tecnologias
                ],
                "adicionado_em": integracao.criado_em.isoformat(),
            }
            for integracao in integrations
        ]

def salvar_repositorio_usuario(
    subject: str,
    repositorio_url: str,
    stack,
    recomendacoes,
):
    with _get_session_factory().begin() as database:
        usuario = _obter_ou_criar_usuario(database, subject)

        integracao = database.scalar(
            select(IntegracaoGitHub).where(
                IntegracaoGitHub.usuario_id == usuario.id_usuario,
                IntegracaoGitHub.project_id.is_(None),
                IntegracaoGitHub.repositorio_url == repositorio_url,
            )
        )

        if integracao is None:
            chat = Chat(
                usuario_id=usuario.id_usuario,
                titulo=f"GitHub: {repositorio_url.rsplit('/', 1)[-1]}"[:255],
                project_id=None,
            )
            database.add(chat)
            database.flush()

            integracao = IntegracaoGitHub(
                usuario_id=usuario.id_usuario,
                chat_id=chat.id_chat,
                project_id=None,
                repositorio_url=repositorio_url,
            )
            database.add(integracao)
            database.flush()
        else:
            for tecnologia in list(integracao.tecnologias):
                database.delete(tecnologia)
            database.flush()

        total = 0

        for nome in dict.fromkeys(stack):
            tecnologia = Tecnologia(
                github_id=integracao.id_github,
                nome=nome,
            )
            database.add(tecnologia)
            database.flush()

            for artigo in recomendacoes.get(nome, []):
                database.add(
                    Recomendacao(
                        tecnologia_id=tecnologia.id_tecnologia,
                        idioma=artigo.get("idioma"),
                        fonte=artigo.get("fonte"),
                        titulo=artigo["titulo"],
                        arquivo=artigo["link"],
                    )
                )
                total += 1

        return {
            "github_id": integracao.id_github,
            "tecnologias": len(set(stack)),
            "recomendacoes": total,
        }


def listar_repositorios_usuario(subject: str):
    with _get_session_factory()() as database:
        integracoes = database.scalars(
            select(IntegracaoGitHub)
            .join(
                Usuario,
                IntegracaoGitHub.usuario_id == Usuario.id_usuario,
            )
            .where(
                Usuario.identificador_externo == subject,
                IntegracaoGitHub.project_id.is_(None),
            )
            .order_by(IntegracaoGitHub.criado_em.desc())
        ).all()

        return [
            {
                "repositorio": integracao.repositorio_url,
                "stack_detectada": [
                    tecnologia.nome
                    for tecnologia in integracao.tecnologias
                ],
                "adicionado_em": integracao.criado_em.isoformat(),
            }
            for integracao in integracoes
        ]


def listar_recomendacoes_usuario(subject: str):
    statement = (
        select(Recomendacao, Tecnologia)
        .join(
            Tecnologia,
            Recomendacao.tecnologia_id == Tecnologia.id_tecnologia,
        )
        .join(
            IntegracaoGitHub,
            Tecnologia.github_id == IntegracaoGitHub.id_github,
        )
        .join(
            Usuario,
            IntegracaoGitHub.usuario_id == Usuario.id_usuario,
        )
        .where(
            Usuario.identificador_externo == subject,
            IntegracaoGitHub.project_id.is_(None),
        )
        .order_by(Recomendacao.criado_em.desc())
    )

    with _get_session_factory()() as database:
        registros = database.execute(statement).all()

        return [
            {
                "tecnologia": tecnologia.nome,
                "titulo": recomendacao.titulo,
                "idioma": recomendacao.idioma,
                "fonte": recomendacao.fonte,
                "link": recomendacao.arquivo,
                "criado_em": recomendacao.criado_em.isoformat(),
            }
            for recomendacao, tecnologia in registros
        ]
