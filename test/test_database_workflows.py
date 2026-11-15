import json
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import sessionmaker

from app import database
from app.models import Base


@pytest.fixture
def sqlite_database(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(
        database,
        "_get_session_factory",
        lambda: factory,
    )
    monkeypatch.setattr(database, "insert", sqlite_insert)
    yield
    engine.dispose()


def test_query_and_assistant_history_is_user_scoped(sqlite_database):
    project_id = UUID("7a1d0f4e-2b6c-4c1e-9f3a-5d8e7c6b4a01")
    chat_id = database.registrar_consulta(
        subject="user-1",
        pergunta="React",
        resposta=json.dumps([{"titulo": "React news"}]),
        project_id=project_id,
    )

    contexto = database.obter_contexto_conversa("user-1", chat_id)
    assert contexto is not None
    assert contexto["project_id"] == project_id

    database.registrar_resposta_assistente(
        subject="user-1",
        pergunta="Continue",
        resposta=json.dumps({"content": "Resposta", "sources": []}),
        m7_conversation_id="m7-conversation-1",
        project_id=project_id,
        chat_id=chat_id,
    )

    conversa = database.obter_conversa("user-1", chat_id)
    assert conversa is not None
    assert conversa["mensagens"][0]["resposta"] == [
        {"titulo": "React news"}
    ]
    assert conversa["mensagens"][1]["resposta"] == {
        "content": "Resposta",
        "sources": [],
    }
    assert database.obter_conversa("user-2", chat_id) is None
    assert database.listar_conversas("user-1") == []
    assert len(database.listar_conversas("user-1", project_id)) == 1


def test_project_repositories_and_recommendations_are_shared(sqlite_database):
    project_id = UUID("7a1d0f4e-2b6c-4c1e-9f3a-5d8e7c6b4a01")
    database.salvar_repositorio_projeto(
        subject="user-1",
        project_id=project_id,
        repositorio_url="https://github.com/org/repo",
        stack=["Python"],
        recomendacoes={
            "Python": [
                {
                    "titulo": "Python article",
                    "link": "https://example.com/python",
                    "fonte": "Blog",
                    "idioma": "en",
                }
            ]
        },
    )

    database.salvar_repositorio_projeto(
        subject="user-2",
        project_id=project_id,
        repositorio_url="https://github.com/org/repo",
        stack=["Go"],
        recomendacoes={
            "Go": [
                {
                    "titulo": "Go article",
                    "link": "https://example.com/go",
                    "fonte": "Blog",
                    "idioma": "en",
                }
            ]
        },
    )

    repositorios = database.listar_repositorios_projeto(project_id)
    recomendacoes = database.listar_recomendacoes_projeto(project_id)

    assert len(repositorios) == 1
    assert repositorios[0]["stack_detectada"] == ["Go"]
    assert len(recomendacoes) == 1
    assert recomendacoes[0]["tecnologia"] == "Go"
    assert recomendacoes[0]["titulo"] == "Go article"
