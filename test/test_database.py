from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import configure_mappers

from app.models import Base


def test_schema_has_expected_entities_and_external_references():
    configure_mappers()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "artigos",
        "usuarios",
        "chats",
        "conteudos",
        "integracoes_github",
        "tecnologias",
        "recomendacoes",
    }

    user_columns = {column["name"] for column in inspector.get_columns("usuarios")}
    assert "identificador_externo" in user_columns
    assert "senha" not in user_columns
    assert not {"nome", "email"} & user_columns

    chat_foreign_keys = inspector.get_foreign_keys("chats")
    assert {foreign_key["referred_table"] for foreign_key in chat_foreign_keys} == {
        "usuarios"
    }
    chat_columns = {column["name"] for column in inspector.get_columns("chats")}
    assert "m7_conversation_id" in chat_columns

    github_columns = {
        column["name"]
        for column in inspector.get_columns("integracoes_github")
    }
    assert "project_id" in github_columns
    assert "repositorio_id_externo" not in github_columns

    technology_columns = {
        column["name"]
        for column in inspector.get_columns("tecnologias")
    }
    assert "tipo" not in technology_columns

    article_indexes = {
        index["name"] for index in inspector.get_indexes("artigos")
    }
    assert "idx_artigos_publicacao" not in article_indexes
